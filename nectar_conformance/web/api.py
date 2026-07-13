"""The read-only JSON API.

Site/conformance/rollout endpoints read the stored reports; version/changes endpoints are
computed live from the packaged check data (cheap, no PuppetDB). All routes are read-only.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from nectar_conformance import __version__
from nectar_conformance.errors import VersionError
from nectar_conformance.rollout import (
    ADOPTED,
    DUE_SOON,
    OVERDUE,
    PENDING,
    actionable,
    rollout_status,
    site_rollout,
)
from nectar_conformance.rules.loader import load_changelog
from nectar_conformance.service import (
    change_timeline,
    diff_versions,
    get_check,
    list_changes,
    list_checks,
    pending_changes,
    resolve_rules,
)
from nectar_conformance.web.serialise import rule_to_dict, site_summary
from nectar_conformance.web.settings import WebSettings
from nectar_conformance.web.store import ReportStore


def _zero_site_rollout() -> dict:
    # A report-bearing site absent from the pivot has no dated changes in flight.
    # Fresh dict per site so callers can never share (and mutate) one instance.
    return {
        OVERDUE: [],
        PENDING: [],
        ADOPTED: [],
        "counts": {OVERDUE: 0, PENDING: 0, DUE_SOON: 0, ADOPTED: 0},
        "next_due": None,
    }


def _age_seconds(generated_at: str | None) -> int | None:
    if not generated_at:
        return None
    try:
        stamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return int((datetime.now(timezone.utc) - stamp).total_seconds())


def build_router(settings: WebSettings, store: ReportStore) -> APIRouter:
    router = APIRouter(prefix="/api")
    config = settings.config
    tier = settings.tier

    @router.get("/health")
    def health() -> dict:
        status = store.status()
        errors = status.get("errors") or {}
        return {
            # "degraded" means the last refresh recorded failures. Always HTTP 200:
            # the k8s probes hit this route, and the web pod is healthy even when
            # PuppetDB is not.
            "status": "degraded" if errors else "ok",
            "version": __version__,
            "tier": tier,
            "reports_generated_at": status.get("generated_at"),
            "last_attempt_at": status.get("last_attempt_at"),
            "age_seconds": _age_seconds(status.get("generated_at")),
            "failed_sites": sorted(errors),
            "sites": len(store.site_ids()),
        }

    @router.get("/sites")
    def sites(within: int = Query(30, ge=0, le=365)) -> dict:
        status = store.status()
        reports = store.all_reports()
        errors = status.get("errors") or {}
        # Per-site rollout exposure, recomputed from the changelog's absolute due
        # dates at request time (countdowns baked into stored reports go stale).
        # Only rollouts still in flight: a done change would sit in every site's
        # adopted list forever (until squashed away) without saying anything.
        today = date.today()
        pivot = site_rollout(
            actionable(
                rollout_status(
                    list_changes(config, tier=tier, as_of=today),
                    reports,
                    today,
                )
            ),
            today,
            due_soon_days=within,
        )
        # A site that failed its last evaluation still serves its last good report;
        # attach the error so the UI can flag that report as stale.
        items = [
            site_summary(
                s,
                r,
                error=errors.get(s),
                rollout=pivot.get(s, _zero_site_rollout()),
            )
            for s, r in reports.items()
        ]
        # Sites that failed and have no report at all get an error-only row.
        have = {item["site"] for item in items}
        for site, message in errors.items():
            if site not in have:
                items.append(
                    {
                        "site": site,
                        "summary": None,
                        "generated_at": None,
                        "conformance_version": None,
                        "error": message,
                        "rollout": None,
                    }
                )
        return {
            "tier": tier,
            "generated_at": status.get("generated_at"),
            "as_of": today.isoformat(),
            "within": within,
            "sites": sorted(items, key=lambda item: item["site"]),
        }

    @router.get("/sites/{site}")
    def site_detail(site: str) -> dict:
        report = store.get_report(site)
        if report is None:
            raise HTTPException(
                status_code=404, detail=f"no report for site '{site}'"
            )
        return report

    @router.get("/checks/{check_id}")
    def check_detail(check_id: str) -> dict:
        definition = get_check(config, check_id)
        if definition is None:
            raise HTTPException(
                status_code=404, detail=f"unknown check '{check_id}'"
            )
        # The currently enforced/pending rule for this tier (header context), if any.
        rule = next(
            (
                r
                for r in resolve_rules(config, tier=tier, as_of=date.today())
                if r.id == check_id
            ),
            None,
        )
        sites = []
        for site, report in sorted(store.all_reports().items()):
            result = next(
                (
                    rr
                    for rr in report.get("results", [])
                    if rr.get("rule_id") == check_id
                ),
                None,
            )
            if result is None:
                # The check is not in this site's report (not applicable to its ruleset).
                sites.append({"site": site, "status": "absent", "checks": []})
            else:
                sites.append(
                    {
                        "site": site,
                        "status": result.get("status"),
                        "checks": result.get("checks", []),
                    }
                )
        return {
            "check_id": check_id,
            "title": definition.title,
            "spec_section": definition.spec_section,
            "description": definition.description,
            "tier": tier,
            "requirement": rule_to_dict(rule) if rule is not None else None,
            "sites": sites,
        }

    @router.get("/versions")
    def versions() -> dict:
        changelog = load_changelog(config.checks_dir)
        return {
            "versions": [
                {"name": name, "date": changelog.tags[name]}
                for name in sorted(changelog.tags)
            ]
        }

    @router.get("/versions/diff")
    def version_diff(
        from_: str = Query(..., alias="from"), to: str = Query(...)
    ) -> dict:
        try:
            return diff_versions(config, from_, to)
        except VersionError as exc:
            raise HTTPException(status_code=404, detail=str(exc))

    @router.get("/versions/{tag}/requirements")
    def requirements(tag: str) -> dict:
        try:
            rules = list_checks(config, tag)
        except VersionError as exc:
            raise HTTPException(status_code=404, detail=str(exc))
        return {
            "version": tag,
            "requirements": [rule_to_dict(r) for r in rules],
        }

    @router.get("/changes")
    def changes() -> dict:
        # One tier per deployment: hide the other tier's directives.
        return {"tier": tier, "changes": change_timeline(config, tier=tier)}

    @router.get("/changes/pending")
    def changes_pending() -> dict:
        today = date.today()
        rules = pending_changes(config, tier=tier, as_of=today)
        return {
            "tier": tier,
            "as_of": today.isoformat(),
            "pending": [rule_to_dict(r) for r in rules],
        }

    @router.get("/changes/rollout")
    def changes_rollout() -> dict:
        today = date.today()
        changes_list = list_changes(config, tier=tier, as_of=today)
        rollout = rollout_status(changes_list, store.all_reports(), today)
        return {
            "tier": tier,
            "as_of": today.isoformat(),
            # Only changes that still need action: not yet due, or someone is behind.
            "rollout": actionable(rollout),
        }

    return router
