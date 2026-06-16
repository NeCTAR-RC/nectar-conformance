"""The engine entry point: evaluate(model, rules, version) -> Report.

Pure function of its inputs (no I/O), so the CLI, tests and a future web dashboard all
drive it the same way. Three evaluation modes:

* ``count`` query     -> one site-level result (host counts).
* ``all_equal`` op    -> collect a per-node value across selected nodes -> one result.
* otherwise           -> one result per selected node.
"""

from __future__ import annotations

from datetime import datetime, timezone

from nectar_conformance.model import SiteModel
from nectar_conformance.plugins.registry import get_plugin
from nectar_conformance.results.model import (
    Advisory,
    CheckResult,
    Provenance,
    Remediation,
    Report,
    RuleResult,
    Severity,
    Status,
)
from nectar_conformance.rules.model import PLUGIN, Rule
from nectar_conformance.engine import operators
from nectar_conformance.engine.queries import MISSING, node_value, site_count
from nectar_conformance.engine.selectors import resolve as resolve_selector

_PRESENCE_OPS = ("present", "absent")


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _advisory(rule: Rule) -> Advisory:
    assert (
        rule.pending_due is not None
    )  # has_pending guarantees the pending fields are set
    return Advisory(
        upcoming_value=rule.pending_value,
        due=rule.pending_due,
        days=rule.pending_days,
        tier=rule.tier,
    )


def _apply_with_pending(
    rule: Rule, op: str, value
) -> tuple[bool, Advisory | None]:
    """Apply the operator, accepting the enforced value OR a pending value.

    While a dated change is pending the previously enforced value is still acceptable, so
    a site that has not yet adopted the upcoming value still passes (and gets an advisory).
    A site already on the upcoming value passes with no advisory. A site on neither value
    fails, even before the due date.
    """
    ok = operators.apply(op, value, rule.expected)
    if not rule.has_pending:
        return ok, None
    ok_pending = operators.apply(op, value, rule.pending_value)
    advisory = None if ok_pending else _advisory(rule)
    return (ok or ok_pending), advisory


def _expected_clause(rule: Rule, op: str) -> str:
    clause = f"expected {op} {rule.expected!r}"
    if rule.has_pending:
        clause += f" (upcoming {rule.pending_value!r} due {rule.pending_due})"
    return clause


def _render_remediation(rule: Rule, target) -> Remediation | None:
    tmpl = rule.remediation
    if tmpl is None:
        return None
    parts = []
    if tmpl.guidance:
        parts.append(tmpl.guidance.strip())
    if tmpl.hiera_key:
        where = f" in {tmpl.hint_file}" if tmpl.hint_file else ""
        if target is not None:
            parts.append(f"Set {tmpl.hiera_key}: {target!r}{where}.")
        else:
            parts.append(f"Set {tmpl.hiera_key}{where}.")
    return Remediation(
        guidance=" ".join(parts).strip(),
        hiera_key=tmpl.hiera_key,
        target_value=target,
        location=tmpl.hint_file,
    )


def _rule_result(rule: Rule, results: list[CheckResult]) -> RuleResult:
    return RuleResult(
        rule_id=rule.id,
        title=rule.title,
        spec_section=rule.spec_section,
        severity=Severity(rule.severity),
        results=tuple(results),
    )


def _skip(rule: Rule, message: str) -> CheckResult:
    return CheckResult(
        rule_id=rule.id,
        title=rule.title,
        spec_section=rule.spec_section,
        severity=Severity(rule.severity),
        status=Status.SKIP,
        message=message,
    )


def _result(
    rule,
    status,
    message,
    *,
    node=None,
    observed=None,
    provenance=None,
    advisory=None,
) -> CheckResult:
    # Render the "how to fix" on a hard failure, and also on a pending change so the
    # operator can act before the deadline. A pending fix points at the upcoming value.
    if status is Status.FAIL:
        remediation = _render_remediation(rule, rule.expected)
    elif advisory is not None:
        remediation = _render_remediation(rule, rule.pending_value)
    else:
        remediation = None
    return CheckResult(
        rule_id=rule.id,
        title=rule.title,
        spec_section=rule.spec_section,
        severity=Severity(rule.severity),
        status=status,
        message=message,
        node=node,
        observed=observed,
        expected=rule.expected,
        remediation=remediation,
        provenance=provenance,
        advisory=advisory,
    )


def _eval_count(model: SiteModel, rule: Rule) -> RuleResult:
    observed, locator = site_count(model, rule.query)
    prov = Provenance(model.source, None, locator, model.collected_at)
    try:
        ok, advisory = _apply_with_pending(rule, rule.assertion_op, observed)
    except Exception as exc:  # noqa: BLE001 - any operator failure -> UNKNOWN
        return _rule_result(
            rule,
            [
                _result(
                    rule,
                    Status.UNKNOWN,
                    f"could not evaluate count: {exc}",
                    observed=observed,
                    provenance=prov,
                )
            ],
        )
    if not ok and observed == 0 and rule.optional:
        # An optional service (e.g. swift) is not deployed at this site, so its
        # host-count requirement does not apply (consistent with per-node checks that
        # SKIP when no node matches). Required services are not marked optional, so a
        # count of 0 falls through to FAIL below. Under-provisioning (1..N-1) fails too.
        return _rule_result(
            rule,
            [
                _skip(
                    rule,
                    f"no nodes run this optional service ({locator}); check not applicable",
                )
            ],
        )
    status = Status.PASS if ok else Status.FAIL
    msg = f"{observed} node(s) match; {_expected_clause(rule, rule.assertion_op)}"
    return _rule_result(
        rule,
        [
            _result(
                rule,
                status,
                msg,
                observed=observed,
                provenance=prov,
                advisory=advisory,
            )
        ],
    )


def _eval_all_equal(model: SiteModel, rule: Rule) -> RuleResult:
    nodes = resolve_selector(model, rule.selector)
    if not nodes:
        return _rule_result(rule, [_skip(rule, "no nodes match the selector")])
    values = []
    for n in nodes:
        val, _ = node_value(n, rule.query)
        values.append(None if val is MISSING else val)
    prov = Provenance(model.source, None, "collect", model.collected_at)
    ok = operators.apply("all_equal", values, rule.expected)
    status = Status.PASS if ok else Status.FAIL
    distinct = sorted({str(v) for v in values})
    msg = f"values across {len(nodes)} node(s): {distinct}"
    return _rule_result(
        rule, [_result(rule, status, msg, observed=values, provenance=prov)]
    )


def _eval_per_node(model: SiteModel, rule: Rule) -> RuleResult:
    nodes = resolve_selector(model, rule.selector)
    if not nodes:
        return _rule_result(rule, [_skip(rule, "no nodes match the selector")])

    op = rule.assertion_op
    results: list[CheckResult] = []
    for n in sorted(nodes, key=lambda nm: nm.certname):
        observed, locator = node_value(n, rule.query)
        prov = Provenance(
            model.source, n.certname, locator, model.collected_at
        )

        if observed is MISSING and op not in _PRESENCE_OPS:
            results.append(
                _result(
                    rule,
                    Status.UNKNOWN,
                    f"{locator} not present on node",
                    node=n.certname,
                    observed=None,
                    provenance=prov,
                )
            )
            continue

        op_input = (
            (observed is not MISSING) if op in _PRESENCE_OPS else observed
        )
        try:
            ok, advisory = _apply_with_pending(rule, op, op_input)
        except Exception as exc:  # noqa: BLE001 - any operator failure -> UNKNOWN
            results.append(
                _result(
                    rule,
                    Status.UNKNOWN,
                    f"could not evaluate: {exc}",
                    node=n.certname,
                    observed=op_input,
                    provenance=prov,
                )
            )
            continue

        shown = None if observed is MISSING else observed
        status = Status.PASS if ok else Status.FAIL
        if op in _PRESENCE_OPS:
            msg = f"{locator} {'present' if op_input else 'absent'}; expected {op}"
        else:
            msg = f"observed {shown!r}; {_expected_clause(rule, op)}"
        results.append(
            _result(
                rule,
                status,
                msg,
                node=n.certname,
                observed=shown,
                provenance=prov,
                advisory=advisory,
            )
        )
    return _rule_result(rule, results)


def _eval_plugin(model: SiteModel, rule: Rule) -> RuleResult:
    spec = rule.check.plugin or {}
    plugin = get_plugin(spec.get("name", ""))
    if plugin is None:
        return _rule_result(
            rule,
            [
                _result(
                    rule,
                    Status.UNKNOWN,
                    f"check plugin '{spec.get('name')}' is not registered",
                )
            ],
        )
    results = plugin.run(model, rule, spec.get("params", {}))
    return _rule_result(rule, list(results))


def evaluate(
    model: SiteModel,
    rules: list[Rule],
    conformance_version: str,
    *,
    as_of: str | None = None,
) -> Report:
    """Evaluate rules against a site model.

    ``as_of`` (an ISO timestamp) stamps ``generated_at`` so a what-if run pinned to a
    date is self-describing; it defaults to the wall clock. The temporal pass/advisory
    decision is already baked into each rule by the fold, so the engine itself does no
    date arithmetic and stays a pure function of (model, rules, as_of).
    """
    rule_results = []
    for rule in rules:
        if rule.kind == PLUGIN:
            rule_results.append(_eval_plugin(model, rule))
        elif rule.query is not None and rule.query.type == "count":
            rule_results.append(_eval_count(model, rule))
        elif rule.assertion_op == "all_equal":
            rule_results.append(_eval_all_equal(model, rule))
        else:
            rule_results.append(_eval_per_node(model, rule))
    return Report(
        site=model.site_id,
        conformance_version=conformance_version,
        source=model.source,
        generated_at=as_of or _now_iso(),
        rule_results=tuple(rule_results),
    )
