"""``version diff`` - show how the check set differs between two versions."""

from __future__ import annotations

from cliff.command import Command

from nectar_conformance import config as config_mod
from nectar_conformance.errors import ConformanceError
from nectar_conformance.service import diff_versions


class DiffVersions(Command):
    """Show checks added and removed between two conformance versions."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("version_a", help="the 'from' conformance version")
        parser.add_argument("version_b", help="the 'to' conformance version")
        parser.add_argument("--config", help="path to a config file")
        parser.add_argument("--checks-dir", help="load checks from this dir")
        return parser

    def take_action(self, parsed_args):
        overrides = (
            {"checks_dir": parsed_args.checks_dir}
            if parsed_args.checks_dir
            else None
        )
        cfg = config_mod.load(parsed_args.config, overrides)
        try:
            diff = diff_versions(
                cfg, parsed_args.version_a, parsed_args.version_b
            )
        except ConformanceError as exc:
            self.app.stderr.write(f"error: {exc}\n")
            return 3
        out = self.app.stdout
        out.write(f"{diff['from']} -> {diff['to']}\n")
        out.write(f"  changed ({len(diff['changed'])}):\n")
        for change in diff["changed"]:
            out.write(
                f"    ~ {change['check_id']}: {change['from']} -> {change['to']}\n"
            )
        out.write(f"  added ({len(diff['added'])}):\n")
        for cid in diff["added"]:
            out.write(f"    + {cid}\n")
        out.write(f"  removed ({len(diff['removed'])}):\n")
        for cid in diff["removed"]:
            out.write(f"    - {cid}\n")
        return 0
