"""``nectar-conformance-refresh`` -- evaluate every site and publish JSON reports.

This is the only PuppetDB-touching piece of the web stack. The k8s CronJob runs it one-shot;
``--interval`` makes it loop for docker compose and local dev. It writes one report per site
plus a ``status.json`` into ``--reports-dir`` (the shared PVC mount), atomically so the web
reader never sees a half-written file. A site that fails to evaluate is recorded in
``status.json`` and skipped; its last good report (if any) is left in place.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from nectar_conformance import config as config_mod
from nectar_conformance.errors import ConformanceError
from nectar_conformance.results.serialise import report_to_json
from nectar_conformance.service import discover_sites, run_check

log = logging.getLogger("nectar_conformance.refresh")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _resolve_sites(config, *, tier: str, explicit: list[str]) -> list[str]:
    if explicit:
        return sorted(set(explicit))
    return [entry["site"] for entry in discover_sites(config, tier=tier)]


def refresh_once(
    config,
    *,
    tier: str,
    sites: list[str],
    version: str | None,
    source: str | None,
    source_kwargs: dict | None,
    reports_dir: Path,
    as_of: str | None = None,
) -> dict:
    """Evaluate ``sites`` and publish their reports + a status file. Returns the status."""
    reports_subdir = reports_dir / "reports"
    reports_subdir.mkdir(parents=True, exist_ok=True)

    site_status: dict[str, dict] = {}
    errors: dict[str, str] = {}
    for site in sites:
        try:
            report = run_check(
                config,
                site=site,
                version=version,
                source=source,
                source_kwargs=source_kwargs,
                as_of=as_of,
                tier=tier,
            )
        except ConformanceError as exc:
            errors[site] = str(exc)
            log.warning("site %s failed to evaluate: %s", site, exc)
            continue
        _atomic_write(reports_subdir / f"{site}.json", report_to_json(report))
        site_status[site] = {
            "generated_at": report.generated_at,
            "summary": report.summary,
        }
        log.info("published report for %s", site)

    # Drop reports for sites no longer present (errored sites keep their last good report).
    current = set(sites)
    for stale in reports_subdir.glob("*.json"):
        if stale.stem not in current:
            stale.unlink()

    status = {
        "tier": tier,
        "generated_at": _now_iso(),
        "version": version,
        "source": source or config.source,
        "sites": site_status,
        "errors": errors,
    }
    _atomic_write(
        reports_dir / "status.json", json.dumps(status, indent=2) + "\n"
    )
    log.info(
        "refresh complete: %d ok, %d failed", len(site_status), len(errors)
    )
    return status


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nectar-conformance-refresh",
        description="Evaluate every site and publish JSON reports for the dashboard.",
    )
    parser.add_argument("--config", help="path to a config file")
    parser.add_argument(
        "--reports-dir",
        help="directory to publish reports into (default: $NECTAR_CONFORMANCE_REPORTS_DIR "
        "or /var/lib/nectar-conformance)",
    )
    parser.add_argument(
        "--tier",
        choices=["test", "prod"],
        help="tier to evaluate all sites as (default: $NECTAR_CONFORMANCE_TIER or prod)",
    )
    parser.add_argument(
        "--site",
        action="append",
        default=[],
        help="evaluate this site instead of discovering from PuppetDB (repeatable)",
    )
    parser.add_argument(
        "--conformance-version",
        help="pin the evaluation date to this version tag (default: live/today)",
    )
    parser.add_argument(
        "--as-of", help="evaluate as if today were this date (YYYY-MM-DD)"
    )
    parser.add_argument(
        "--source", choices=["puppetdb", "static"], help="data source"
    )
    parser.add_argument(
        "--puppetdb-url", help="override the PuppetDB base URL"
    )
    parser.add_argument(
        "--checks-dir", help="load check definitions/changelog from this dir"
    )
    parser.add_argument(
        "--site-repo", help="path to the site puppet repo (static source)"
    )
    parser.add_argument(
        "--catalog-dir", help="dir of compiled catalog JSON (static source)"
    )
    parser.add_argument(
        "--facts-dir", help="dir of per-node facts JSON (static source)"
    )
    parser.add_argument(
        "--interval",
        type=int,
        help="loop forever, sleeping this many seconds between passes (default: one-shot)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    args = _build_parser().parse_args(argv)

    from nectar_conformance.config import ENV_PREFIX

    overrides: dict = {}
    if args.puppetdb_url:
        overrides.setdefault("puppetdb", {})["base_url"] = args.puppetdb_url
    if args.source:
        overrides["source"] = args.source
    if args.checks_dir:
        overrides["checks_dir"] = args.checks_dir

    config = config_mod.load(args.config, overrides)
    tier = args.tier or os.environ.get(ENV_PREFIX + "TIER") or "prod"
    reports_dir = Path(
        args.reports_dir
        or os.environ.get(ENV_PREFIX + "REPORTS_DIR")
        or "/var/lib/nectar-conformance"
    )
    source_kwargs = {
        "site_repo": args.site_repo,
        "catalog_dir": args.catalog_dir,
        "facts_dir": args.facts_dir,
    }

    source = args.source or config.source
    if not args.site and source != "puppetdb":
        log.error(
            "site discovery requires the puppetdb source; pass --site for the %s source",
            source,
        )
        return 2

    def run_pass() -> None:
        sites = _resolve_sites(config, tier=tier, explicit=args.site)
        if not sites:
            log.warning("no sites to evaluate")
        refresh_once(
            config,
            tier=tier,
            sites=sites,
            version=args.conformance_version,
            source=args.source,
            source_kwargs=source_kwargs,
            reports_dir=reports_dir,
            as_of=args.as_of,
        )

    if args.interval:  # pragma: no cover - unbounded loop, not unit-tested
        log.info("refresh loop every %ds (ctrl-c to stop)", args.interval)
        while True:
            try:
                run_pass()
            except ConformanceError as exc:
                log.error("refresh pass failed: %s", exc)
            time.sleep(args.interval)

    try:
        run_pass()
    except ConformanceError as exc:
        log.error("refresh failed: %s", exc)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
