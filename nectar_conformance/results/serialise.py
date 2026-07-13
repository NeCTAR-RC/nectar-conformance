"""Serialise a Report to the canonical JSON contract consumed by the web dashboard."""

from __future__ import annotations

import json

from nectar_conformance.results.model import CheckResult, Report, RuleResult


def _remediation_to_dict(rem) -> dict:
    return {
        "guidance": rem.guidance,
        "hiera_key": rem.hiera_key,
        "target_value": rem.target_value,
        "location": rem.location,
    }


def _check_to_dict(check: CheckResult) -> dict:
    data: dict = {
        "status": check.status.value,
        "node": check.node,
        "observed": check.observed,
        "expected": check.expected,
        "message": check.message,
    }
    if check.remediation is not None:
        data["remediation"] = _remediation_to_dict(check.remediation)
    if check.advisory is not None:
        a = check.advisory
        data["advisory"] = {
            "upcoming_value": a.upcoming_value,
            "due": a.due,
            "days": a.days,
            "tier": a.tier,
        }
    if check.provenance is not None:
        p = check.provenance
        data["provenance"] = {
            "source": p.source,
            "certname": p.certname,
            "locator": p.locator,
            "collected_at": p.collected_at,
        }
    return data


def _rule_to_dict(rule_result: RuleResult) -> dict:
    return {
        "rule_id": rule_result.rule_id,
        "title": rule_result.title,
        "spec_section": rule_result.spec_section,
        "status": rule_result.status.value,
        "checks": [_check_to_dict(c) for c in rule_result.results],
    }


def report_to_dict(report: Report) -> dict:
    return {
        "schema_version": report.schema_version,
        "site": report.site,
        "conformance_version": report.conformance_version,
        "source": report.source,
        "generated_at": report.generated_at,
        "summary": report.summary,
        "results": [_rule_to_dict(rr) for rr in report.rule_results],
    }


def report_to_json(report: Report, indent: int = 2) -> str:
    return json.dumps(report_to_dict(report), indent=indent, sort_keys=False)
