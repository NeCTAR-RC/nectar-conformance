"""``check list`` and ``check show`` - inspect checks without touching PuppetDB."""

from __future__ import annotations

from cliff.command import Command

from nectar_conformance import config as config_mod
from nectar_conformance.errors import ConformanceError
from nectar_conformance.service import get_check, list_checks


def _resolve_version(parsed_args, cfg):
    return parsed_args.conformance_version or cfg.default_conformance_version


class CheckList(Command):
    """List the checks that apply at a conformance version."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument(
            "--conformance-version", help="conformance version, e.g. 2026.1"
        )
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
        version = _resolve_version(parsed_args, cfg)
        if not version:
            self.app.stderr.write(
                "error: no conformance version (use --conformance-version)\n"
            )
            return 2
        try:
            rules = list_checks(cfg, version)
        except ConformanceError as exc:
            self.app.stderr.write(f"error: {exc}\n")
            return 3
        out = self.app.stdout
        out.write(f"Checks for conformance {version}:\n")
        for rule in rules:
            expected = (
                ""
                if rule.expected is None
                else f"  expected={rule.expected!r}"
            )
            section = rule.spec_section or "-"
            out.write(f"  {rule.id:30} ({section}){expected}\n")
        return 0


class CheckShow(Command):
    """Show the full definition of one check."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument(
            "check_id", help="check id, e.g. glance.api.image_tag"
        )
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
        check = get_check(cfg, parsed_args.check_id)
        if check is None:
            self.app.stderr.write(
                f"error: no such check '{parsed_args.check_id}'\n"
            )
            return 3
        out = self.app.stdout
        out.write(f"{check.id}\n")
        out.write(f"  title:        {check.title}\n")
        out.write(f"  spec_section: {check.spec_section}\n")
        out.write(f"  kind:         {check.kind}\n")
        out.write(
            f"  selector:     {check.selector.type} {check.selector.params}\n"
        )
        if check.query is not None:
            out.write(
                f"  query:        {check.query.type} {check.query.params}\n"
            )
        if check.assertion_op is not None:
            out.write(f"  assertion:    {check.assertion_op}\n")
        if check.remediation is not None:
            out.write(f"  remediation:  {check.remediation.guidance}\n")
            if check.remediation.hiera_key:
                out.write(
                    f"                hiera_key={check.remediation.hiera_key}\n"
                )
        return 0
