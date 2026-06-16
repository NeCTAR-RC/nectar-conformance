"""``version`` subcommands: list/lint versions and squash the changelog to a baseline."""

from __future__ import annotations

from cliff.command import Command

from nectar_conformance import config as config_mod
from nectar_conformance.errors import ConformanceError
from nectar_conformance.service import (
    available_versions,
    lint_versions,
    squash_changelog,
)


class VersionList(Command):
    """List available conformance versions."""

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
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
            versions = available_versions(cfg)
            violations = lint_versions(cfg)
        except ConformanceError as exc:
            self.app.stderr.write(f"error: {exc}\n")
            return 3
        out = self.app.stdout
        out.write("Available conformance versions:\n")
        default = cfg.default_conformance_version
        for version in versions:
            marker = "  (default)" if version == default else ""
            out.write(f"  {version}{marker}\n")
        if violations:
            out.write("\nChangelog problems:\n")
            for v in violations:
                out.write(f"  ! {v}\n")
            return 1
        return 0


class VersionSquash(Command):
    """Squash the changelog to a fresh baseline named as a new conformance version.

    Folds the changelog at the squash date into baseline directives carrying the latest
    enforced values (per tier), carries scheduled rollouts forward, and archives the full
    pre-squash log so no history is lost. Point --checks-dir at a nectar-conformance-checks
    checkout (the squash rewrites files in place).
    """

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument(
            "--name",
            required=True,
            help="name for the new conformance version (e.g. 2027.0)",
        )
        parser.add_argument(
            "--as-of",
            help="squash date (YYYY-MM-DD), on or before today; the new version is pinned "
            "to it (default: today, i.e. when the squash happens)",
        )
        parser.add_argument("--config", help="path to a config file")
        parser.add_argument(
            "--checks-dir",
            help="nectar-conformance-checks checkout to read and rewrite",
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
            result = squash_changelog(
                cfg, name=parsed_args.name, as_of=parsed_args.as_of
            )
        except ConformanceError as exc:
            self.app.stderr.write(f"error: {exc}\n")
            return 3
        out = self.app.stdout
        out.write(
            f"Squashed to baseline {result.name} (as of {result.as_of}).\n"
        )
        out.write(
            f"  entries: {result.entries_before} -> {result.entries_after} "
            f"({result.baselines} baseline, {result.carried} carried forward)\n"
        )
        out.write(
            f"  archived {result.archived} entries to {result.archive_path}\n"
        )
        out.write(f"  wrote {result.changelog_path}\n")
        out.write(
            "\nNext: review the diff and add a release note. A no-flag `check run` still "
            f"evaluates live; pass --conformance-version {result.name} to pin a report.\n"
        )
        return 0
