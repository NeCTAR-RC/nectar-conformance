"""``check run`` - evaluate a site against a conformance version."""

from __future__ import annotations

from cliff.command import Command

from nectar_conformance import config as config_mod
from nectar_conformance.errors import ConformanceError
from nectar_conformance.report import human, json_report
from nectar_conformance.results.model import Report
from nectar_conformance.service import run_check

# Process exit codes.
EXIT_OK = 0
EXIT_NONCONFORMANT = 1
EXIT_OPERATIONAL = 3


def exit_code(report: Report) -> int:
    return EXIT_NONCONFORMANT if report.has_failures else EXIT_OK


class CheckRun(Command):
    """Run conformance checks for a site and report the results."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument(
            "--site", required=True, help="site (puppet environment) to check"
        )
        parser.add_argument(
            "--environment",
            help="puppet environment to query instead of the site name; use to check a "
            "proposed branch environment before it goes live (report is still labelled --site)",
        )
        parser.add_argument(
            "--conformance-version",
            help="conformance version tag to pin the evaluation date to (e.g. 2026.1); "
            "omit for a live run against today",
        )
        parser.add_argument(
            "--as-of",
            help="evaluate as if today were this date (YYYY-MM-DD), for scheduled and "
            "what-if runs; overrides the version tag's pinned date",
        )
        parser.add_argument(
            "--site-tier",
            choices=["test", "prod"],
            help="treat the site as this tier for dated changes (overrides config; "
            "default prod)",
        )
        parser.add_argument(
            "--source", choices=["puppetdb", "static"], help="data source"
        )
        parser.add_argument(
            "--format", choices=["human", "json"], default="human"
        )
        parser.add_argument(
            "--due-within",
            type=int,
            default=30,
            metavar="DAYS",
            help="human report only: flag passing checks whose pending change is due "
            "within this many days as at risk (default: 30; never affects the exit "
            "code)",
        )
        parser.add_argument("--config", help="path to a config file")
        parser.add_argument(
            "--puppetdb-url", help="override the PuppetDB base URL"
        )
        parser.add_argument(
            "--checks-dir",
            help="load check definitions/manifests from this dir",
        )
        parser.add_argument(
            "--site-repo", help="path to the site puppet repo (static source)"
        )
        parser.add_argument(
            "--catalog-dir",
            help="dir of compiled catalog JSON (static source)",
        )
        parser.add_argument(
            "--facts-dir", help="dir of per-node facts JSON (static source)"
        )
        return parser

    def take_action(self, parsed_args):
        overrides: dict = {}
        if parsed_args.puppetdb_url:
            overrides.setdefault("puppetdb", {})["base_url"] = (
                parsed_args.puppetdb_url
            )
        if parsed_args.source:
            overrides["source"] = parsed_args.source
        if parsed_args.checks_dir:
            overrides["checks_dir"] = parsed_args.checks_dir

        try:
            cfg = config_mod.load(parsed_args.config, overrides)
            if parsed_args.environment:
                # Query this environment but keep the site label/identity.
                cfg.site_environment[parsed_args.site] = (
                    parsed_args.environment
                )
            if parsed_args.site_tier:
                # Override the site's tier for this run (mirrors --environment).
                cfg.site_tier[parsed_args.site] = parsed_args.site_tier
            source_kwargs = {
                "site_repo": parsed_args.site_repo,
                "catalog_dir": parsed_args.catalog_dir,
                "facts_dir": parsed_args.facts_dir,
            }
            report = run_check(
                cfg,
                site=parsed_args.site,
                version=parsed_args.conformance_version,
                source=parsed_args.source,
                source_kwargs=source_kwargs,
                as_of=parsed_args.as_of,
            )
        except ConformanceError as exc:
            self.app.stderr.write(f"error: {exc}\n")
            return EXIT_OPERATIONAL

        if parsed_args.format == "json":
            json_report.render(report, self.app.stdout)
        else:
            human.render(
                report, self.app.stdout, due_within=parsed_args.due_within
            )
        return exit_code(report)
