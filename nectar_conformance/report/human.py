"""Human-readable report rendering with Rich.

Grouped by spec section; per-check status, observed vs expected, affected hosts, and a
``Fix:`` line for failures; a summary score footer. Rich degrades to plain text when
the stream is not a TTY.
"""

from __future__ import annotations

from typing import TextIO

from rich.console import Console

from nectar_conformance.results.model import Report, RuleResult, Status

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


def render(report: Report, stream: TextIO) -> None:
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

    for section in sorted(sections):
        console.print(f"\n[bold]{section}[/bold]")
        for rr in sections[section]:
            label, _ = _GLYPH[rr.status]
            sev = (
                f" [{rr.severity.value}]"
                if rr.status in (Status.FAIL, Status.UNKNOWN)
                else ""
            )
            console.print(f"  {label}  {rr.rule_id}{sev}  {_detail(rr)}")
            hosts = _affected(rr)
            if hosts:
                console.print(f"        hosts: {', '.join(hosts)}")
            adv = rr.advisory
            if adv is not None:
                when = (
                    f"in {adv.days} day(s)" if adv.days is not None else "soon"
                )
                console.print(
                    f"        [yellow]Due:[/yellow] {adv.upcoming_value!r} for {adv.tier} "
                    f"sites by {adv.due} ({when})"
                )
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
    console.print(f"Result: [bold]{s['result'].upper()}[/bold]")
