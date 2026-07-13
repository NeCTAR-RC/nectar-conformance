"""Human-readable report rendering with Rich.

Grouped by spec section; per-check status, observed vs expected, affected hosts, and a
``Fix:`` line for failures; a summary score footer. Rich degrades to plain text when
the stream is not a TTY.
"""

from __future__ import annotations

from datetime import date
from typing import TextIO

from rich.console import Console

from nectar_conformance.results.model import (
    Advisory,
    Report,
    RuleResult,
    Status,
)

_GLYPH = {
    Status.PASS: ("[green]PASS[/green]", "✓"),
    Status.FAIL: ("[red]FAIL[/red]", "✗"),
    Status.SKIP: ("[dim]SKIP[/dim]", "-"),
    Status.UNKNOWN: ("[yellow]UNKN[/yellow]", "?"),
}


def _affected(rule_result: RuleResult) -> list[str]:
    return [
        c.node
        for c in rule_result.results
        if c.status is Status.FAIL and c.node
    ]


def _detail(rule_result: RuleResult) -> str:
    # Prefer a failing result's message, else the first result's message.
    failing = [c for c in rule_result.results if c.status is Status.FAIL]
    chosen = (
        failing[0]
        if failing
        else (rule_result.results[0] if rule_result.results else None)
    )
    return chosen.message if chosen else ""


def _remediation(rule_result: RuleResult) -> str:
    # Remediation is attached to failing results and to pending (advisory) results, so
    # the operator sees how to fix both an overdue check and an upcoming one.
    for c in rule_result.results:
        if c.remediation is not None:
            return c.remediation.guidance
    return ""


def _days_left(adv: Advisory, report: Report) -> int | None:
    # The baked countdown was computed at this run's fold instant, so it is fresh here
    # (unlike stored web reports); fall back to the absolute due date vs the report date.
    if adv.days is not None:
        return adv.days
    try:
        generated = date.fromisoformat(report.generated_at[:10])
        return (date.fromisoformat(adv.due) - generated).days
    except (TypeError, ValueError):
        return None


def _at_risk(
    report: Report, due_within: int
) -> list[tuple[RuleResult, Advisory, int]]:
    """Rules passing today whose pending change falls due within ``due_within`` days.

    PASS-only: a FAIL rule can also carry an advisory (node on neither value), but it
    already fails and must not be double-reported.
    """
    out = []
    for rr in report.rule_results:
        adv = rr.advisory
        if rr.status is not Status.PASS or adv is None:
            continue
        days = _days_left(adv, report)
        if days is not None and days <= due_within:
            out.append((rr, adv, days))
    out.sort(key=lambda item: (item[2], item[0].rule_id))
    return out


def render(report: Report, stream: TextIO, *, due_within: int = 30) -> None:
    console = Console(file=stream, highlight=False)
    console.print(
        f"[bold]Nectar Conformance Report[/bold]\n"
        f"Site: {report.site}   Conformance: {report.conformance_version}   "
        f"Source: {report.source}   {report.generated_at}"
    )

    # Group rule results by spec section, preserving a stable section order.
    sections: dict[str, list[RuleResult]] = {}
    for rr in report.rule_results:
        sections.setdefault(rr.spec_section or "general", []).append(rr)

    at_risk = _at_risk(report, due_within)
    at_risk_ids = {rr.rule_id for rr, _, _ in at_risk}

    for section in sorted(sections):
        console.print(f"\n[bold]{section}[/bold]")
        for rr in sections[section]:
            label, _ = _GLYPH[rr.status]
            console.print(f"  {label}  {rr.rule_id}  {_detail(rr)}")
            hosts = _affected(rr)
            if hosts:
                console.print(f"        hosts: {', '.join(hosts)}")
            adv = rr.advisory
            if adv is not None:
                days = _days_left(adv, report)
                when = f"in {days} day(s)" if days is not None else "soon"
                line = (
                    f"{adv.upcoming_value!r} for {adv.tier} "
                    f"sites by {adv.due} ({when})"
                )
                if rr.rule_id in at_risk_ids:
                    console.print(
                        f"        [bold red]Due: {line} - will FAIL[/bold red]"
                    )
                else:
                    console.print(f"        [yellow]Due:[/yellow] {line}")
            fix = _remediation(rr)
            if fix:
                console.print(f"        [cyan]Fix:[/cyan] {fix}")

    s = report.summary
    console.print(
        f"\nSummary: {s['total']} checks  "
        f"{s['pass']} pass  {s['fail']} fail  {s['skip']} skip  {s['unknown']} unknown   "
        f"score {int(round(s['score'] * 100))}%"
    )
    if s.get("advisory"):
        console.print(
            f"Upcoming: {s['advisory']} change(s) pending (see Due lines)"
        )
    if at_risk:
        console.print(
            f"[bold red]At risk:[/bold red] {len(at_risk)} passing check(s) "
            f"will fail within {due_within} days"
        )
        for rr, adv, days in at_risk:
            console.print(
                f"  {rr.rule_id}  {adv.upcoming_value!r} due {adv.due} "
                f"(in {days} day(s))"
            )
    console.print(f"Result: [bold]{s['result'].upper()}[/bold]")
