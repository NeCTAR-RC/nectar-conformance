"""Load and validate check definitions and the conformance changelog.

The definitions (``definitions/*.yaml``) and the changelog (``changelog.yaml``) live
in their own repository (``nectar-conformance-checks``), not in this package, so Core
Services can edit the conformance schedule without releasing a new tool. A directory
holding them must be supplied via ``--checks-dir``, the ``checks_dir`` config key, or
``NECTAR_CONFORMANCE_CHECKS_DIR``: deployments mount a synced checkout and local runs
point at one.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import yaml

from nectar_conformance.errors import RuleError
from nectar_conformance.rules.model import Changelog, CheckDef
from nectar_conformance.rules.schema import (
    validate_changelog,
    validate_definition,
)

_NO_CHECKS_DIR = (
    "no checks directory configured: the check definitions and conformance "
    "changelog live in the nectar-conformance-checks repository. Point at a checkout "
    "with --checks-dir, the checks_dir config key, or NECTAR_CONFORMANCE_CHECKS_DIR."
)


def _require(source_dir: str | None) -> Path:
    """Resolve a configured checks directory or raise a clear, actionable error."""
    if not source_dir:
        raise RuleError(_NO_CHECKS_DIR)
    base = Path(source_dir)
    if not base.is_dir():
        raise RuleError(f"checks directory does not exist: {base}")
    return base


def _iter_yaml(
    subdir: str, source_dir: str | None
) -> Iterator[tuple[str, str]]:
    base = _require(source_dir) / subdir
    for f in sorted(base.glob("*.yaml")):
        yield f.name, f.read_text()


def read_changelog_text(source_dir: str | None) -> str:
    """Return the raw changelog YAML text (used verbatim when archiving a squash)."""
    path = _require(source_dir) / "changelog.yaml"
    if not path.exists():
        raise RuleError(f"conformance changelog not found: {path}")
    return path.read_text()


def writable_checks_dir(source_dir: str | None) -> Path:
    """Resolve the checks directory as a writable filesystem path (for ``squash``)."""
    return _require(source_dir)


def load_definitions(source_dir: str | None = None) -> dict[str, CheckDef]:
    defs: dict[str, CheckDef] = {}
    for name, text in _iter_yaml("definitions", source_dir):
        data = yaml.safe_load(text)
        if not isinstance(data, dict):
            raise RuleError(f"check definition '{name}' is not a YAML mapping")
        validate_definition(data)
        check = CheckDef.from_dict(data)
        if check.id in defs:
            raise RuleError(
                f"duplicate check definition id '{check.id}' (in {name})"
            )
        defs[check.id] = check
    return defs


def load_changelog(source_dir: str | None = None) -> Changelog:
    data = yaml.safe_load(read_changelog_text(source_dir))
    if not isinstance(data, dict):
        raise RuleError("conformance changelog is not a YAML mapping")
    validate_changelog(data)
    return Changelog.from_dict(data)
