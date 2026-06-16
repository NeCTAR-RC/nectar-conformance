"""``changelog lint`` - structurally validate a checks directory.

The checks data lives in its own repository (``nectar-conformance-checks``); this is the
CI gate that repository runs to catch a malformed changelog or definition before merge.
It loads the definitions and changelog, runs :func:`changelog_lint`, and reports any
structural violations (unknown check ids, ``effective`` after ``due``, test due later
than prod, colliding entries).
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
        return parser

    def take_action(self, parsed_args):
        overrides = (
            {"checks_dir": parsed_args.checks_dir}
            if parsed_args.checks_dir
            else None
        )
        cfg = config_mod.load(parsed_args.config, overrides)
        try:
            violations = lint_versions(cfg)
        except ConformanceError as exc:
            self.app.stderr.write(f"error: {exc}\n")
            return 3
        if violations:
            self.app.stderr.write("changelog lint found problems:\n")
            for v in violations:
                self.app.stderr.write(f"  - {v}\n")
            return 1
        self.app.stdout.write("changelog lint: ok\n")
        return 0
