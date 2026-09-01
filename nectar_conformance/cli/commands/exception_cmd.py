"""``exception list`` - show the authored conformance exceptions and their state."""

from __future__ import annotations

from cliff.command import Command

from nectar_conformance import config as config_mod
from nectar_conformance.errors import ConformanceError
from nectar_conformance.service import list_exceptions


class ExceptionList(Command):
    """List conformance exceptions (site/check/host waivers) and their state."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument("--site", help="only exceptions for this site")
        parser.add_argument(
            "--as-of",
            help="judge active/pending/expired at this date (YYYY-MM-DD, default: today)",
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
        try:
            exceptions = list_exceptions(
                cfg, site=parsed_args.site, as_of=parsed_args.as_of
            )
        except ConformanceError as exc:
            self.app.stderr.write(f"error: {exc}\n")
            return 3
        out = self.app.stdout
        if not exceptions:
            out.write("No conformance exceptions.\n")
            return 0
        for e in exceptions:
            window = []
            if e["effective"]:
                window.append(f"from {e['effective']}")
            if e["expiry"]:
                window.append(f"until {e['expiry']}")
            when = f"  ({', '.join(window)})" if window else ""
            out.write(
                f"{e['check_id']}  site={e['site']}  [{e['state']}]{when}\n"
            )
            out.write(f"  hosts:  {', '.join(e['hosts'])}\n")
            out.write(f"  reason: {e['reason']}\n")
            if e["note"]:
                out.write(f"  note:   {e['note']}\n")
        return 0
