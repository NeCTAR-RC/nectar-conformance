"""``changelog lint`` - structurally validate a checks directory.

The checks data lives in its own repository (``nectar-conformance-checks``); this is the
CI gate that repository runs to catch a malformed changelog, definition, or exceptions
file before merge. It loads the checks dir, runs :func:`changelog_lint` and
:func:`exceptions_lint`, and reports structural violations (unknown check ids,
``effective`` after ``due``, test due later than prod, colliding entries). Warnings
(e.g. an expired exception) are printed but do not fail the lint.
"""

from __future__ import annotations

from cliff.command import Command

from nectar_conformance import config as config_mod
from nectar_conformance.errors import ConformanceError
from nectar_conformance.service import lint_versions


class ChangelogLint(Command):
    """Validate the conformance changelog and definitions are structurally sound."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("--config", help="path to a config file")
        parser.add_argument("--checks-dir", help="checks dir to lint")
        parser.add_argument(
            "--as-of",
            help="judge exception expiry at this date (YYYY-MM-DD, default: today)",
        )
        return parser

    def take_action(self, parsed_args):
        overrides = (
            {"checks_dir": parsed_args.checks_dir}
            if parsed_args.checks_dir
            else None
        )
        cfg = config_mod.load(parsed_args.config, overrides)
        try:
            violations, warnings = lint_versions(cfg, as_of=parsed_args.as_of)
        except ConformanceError as exc:
            self.app.stderr.write(f"error: {exc}\n")
            return 3
        for w in warnings:
            self.app.stderr.write(f"warning: {w}\n")
        if violations:
            self.app.stderr.write("changelog lint found problems:\n")
            for v in violations:
                self.app.stderr.write(f"  - {v}\n")
            return 1
        self.app.stdout.write("changelog lint: ok\n")
        return 0
