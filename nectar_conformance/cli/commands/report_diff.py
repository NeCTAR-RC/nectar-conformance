"""``report diff`` - compare two conformance report JSON files (before vs after)."""

from __future__ import annotations

import json

from cliff.command import Command

from nectar_conformance.results.compare import compare_reports


class ReportDiff(Command):
    """Diff two 'check run --format json' reports to see what a change fixes or breaks."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("old", help="baseline report JSON (current/live)")
        parser.add_argument("new", help="proposed report JSON (the change)")
        return parser

    def take_action(self, parsed_args):
        try:
            with open(parsed_args.old) as fh:
                old = json.load(fh)
            with open(parsed_args.new) as fh:
                new = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            self.app.stderr.write(f"error: could not read report: {exc}\n")
            return 3

        diff = compare_reports(old, new)
        out = self.app.stdout

        def section(label, rows):
            out.write(f"{label} ({len(rows)}):\n")
            for r in rows:
                arrow = f"{r['old']} -> {r['new']}"
                out.write(f"  {r['rule_id']} [{r['severity']}]  {arrow}\n")

        section("Fixed", diff["fixed"])
        section("Regressed", diff["regressed"])
        section("Still failing", diff["still_failing"])
        if diff["added"] or diff["removed"]:
            section("Added checks", diff["added"])
            section("Removed checks", diff["removed"])

        out.write(
            f"\nSummary: {len(diff['fixed'])} fixed, {len(diff['regressed'])} regressed, "
            f"{len(diff['still_failing'])} still failing\n"
        )
        # Non-zero exit if the change introduces any new failure, so CI can gate on it.
        return 1 if diff["regressed"] else 0
