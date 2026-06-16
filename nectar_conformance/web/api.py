"""The read-only JSON API.

Site/conformance/rollout endpoints read the stored reports; version/changes endpoints are
computed live from the packaged check data (cheap, no PuppetDB). All routes are read-only.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException, Query

from nectar_conformance.errors import VersionError
from nectar_conformance.rollout import rollout_status
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
        return {
            "status": "ok",
            "tier": tier,
            "reports_generated_at": status.get("generated_at"),
            "age_seconds": _age_seconds(status.get("generated_at")),
            "sites": len(store.site_ids()),
        }

    @router.get("/sites")
    def sites() -> dict:
        status = store.status()
        reports = store.all_reports()
        items = [site_summary(s, r) for s, r in reports.items()]
        # Surface sites that failed to evaluate (no report written this run).
        errors = status.get("errors") or {}
        have = {item["site"] for item in items}
        for site, message in errors.items():
            if site not in have:
                items.append(
                    {
                        "site": site,
                        "summary": None,
                        "generated_at": None,
                        "conformance_version": None,
                        "worst_severity": None,
                        "error": message,
                    }
                )
        return {
            "tier": tier,
            "generated_at": status.get("generated_at"),
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
                sites.append(
                    {
                        "site": site,
                        "status": "absent",
                        "severity": None,
                        "checks": [],
                    }
                )
            else:
                sites.append(
                    {
                        "site": site,
                        "status": result.get("status"),
                        "severity": result.get("severity"),
                        "checks": result.get("checks", []),
                    }
                )
        return {
            "check_id": check_id,
            "title": definition.title,
            "spec_section": definition.spec_section,
            "severity": definition.severity,
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
        # Only surface changes that still need action: not yet due, or someone is behind.
        actionable = [
            c
            for c in rollout
            if not c["due_passed"]
            or c["counts"]["overdue"]
            or c["counts"]["pending"]
        ]
        return {
            "tier": tier,
            "as_of": today.isoformat(),
            "rollout": actionable,
        }

    return router
