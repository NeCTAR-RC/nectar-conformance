"""Orchestration: tie config + data source + changelog + engine together.

Used by the CLI and directly usable by a future web backend.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone

import yaml

from nectar_conformance.config import DEFAULT_PUPPETDB_URLS, Config
from nectar_conformance.datasources.base import get_datasource
from nectar_conformance.engine.runner import evaluate
from nectar_conformance.errors import RuleError, VersionError
from nectar_conformance.results.model import Report
from nectar_conformance.rules.changelog import (
    changelog_lint,
    fold,
    resolve_tag,
    squash,
)
from nectar_conformance.rules.loader import (
    load_changelog,
    load_definitions,
    read_changelog_text,
    writable_checks_dir,
)
from nectar_conformance.rules.model import (
    ChangeEntry,
    Changelog,
    CheckDef,
    Rule,
)

# Tier used when listing/diffing a conformance version, where no specific site is in
# play. At a tag's pinned date there are normally only baseline (tier "all") entries,
# so this rarely matters; "prod" gives the enforced production view when it does.
_NEUTRAL_TIER = "prod"


def _resource_types(rules: list[Rule]) -> set:
    types = set()
    for rule in rules:
        q = rule.query
        if q is not None and q.type == "resource_param":
            types.add(q.params["resource_type"])
    return types


def _resolve_instant(
    changelog, version: str | None, as_of: str | None
) -> date:
    """The date the changelog is folded at: --as-of wins, then a version tag, then today."""
    if as_of:
        try:
            return date.fromisoformat(as_of)
        except ValueError as exc:
            raise VersionError(f"invalid --as-of date '{as_of}': {exc}")
    if version:
        return resolve_tag(
            changelog, version
        )  # raises VersionError on an unknown tag
    return datetime.now(timezone.utc).date()


def resolve_rules(config: Config, *, tier: str, as_of: date) -> list[Rule]:
    definitions = load_definitions(config.checks_dir)
    changelog = load_changelog(config.checks_dir)
    return fold(changelog, definitions, tier=tier, as_of=as_of)


def run_check(
    config: Config,
    site: str,
    version: str | None,
    source: str | None = None,
    source_kwargs: dict | None = None,
    *,
    as_of: str | None = None,
    tier: str | None = None,
) -> Report:
    version = version or config.default_conformance_version
    changelog = load_changelog(config.checks_dir)
    definitions = load_definitions(config.checks_dir)
    instant = _resolve_instant(changelog, version, as_of)
    # An explicit tier (e.g. a single-tier web deployment) overrides the per-site default.
    tier = tier or config.site_tier_for(site)
    rules = fold(changelog, definitions, tier=tier, as_of=instant)
    src = source or config.source
    datasource = get_datasource(
        src,
        config,
        resource_types=_resource_types(rules),
        **(source_kwargs or {}),
    )
    model = datasource.load_site(site)
    label = version or "(live)"
    generated_at = f"{as_of}T00:00:00Z" if as_of else None
    return evaluate(model, rules, label, as_of=generated_at)


def available_versions(config: Config) -> list[str]:
    return sorted(load_changelog(config.checks_dir).tags)


def list_checks(config: Config, version: str) -> list[Rule]:
    changelog = load_changelog(config.checks_dir)
    instant = _resolve_instant(changelog, version, None)
    return resolve_rules(config, tier=_NEUTRAL_TIER, as_of=instant)


def get_check(config: Config, check_id: str) -> CheckDef | None:
    return load_definitions(config.checks_dir).get(check_id)


def _expected_at(
    changelog: Changelog,
    definitions: dict[str, CheckDef],
    instant: date,
) -> dict[str, object]:
    """Map each enforced check id to its expected value at ``instant`` (neutral tier)."""
    return {
        rule.id: rule.expected
        for rule in fold(
            changelog, definitions, tier=_NEUTRAL_TIER, as_of=instant
        )
    }


def diff_versions(config: Config, version_a: str, version_b: str) -> dict:
    """Diff two conformance versions: check ids added/removed and expected values changed.

    Resolves both tags to their pinned dates and folds the (current) changelog at each, so the
    value diff is exact for versions reproducible from the live log. Diffing across a squash
    boundary, where the older version lives only in an archived snapshot, is a known gap.
    """
    changelog = load_changelog(config.checks_dir)
    definitions = load_definitions(config.checks_dir)
    expected_a = _expected_at(
        changelog, definitions, resolve_tag(changelog, version_a)
    )
    expected_b = _expected_at(
        changelog, definitions, resolve_tag(changelog, version_b)
    )
    a, b = set(expected_a), set(expected_b)
    changed = [
        {
            "check_id": cid,
            "from": expected_a[cid],
            "to": expected_b[cid],
        }
        for cid in sorted(a & b)
        if expected_a[cid] != expected_b[cid]
    ]
    return {
        "from": version_a,
        "to": version_b,
        "added": sorted(b - a),
        "removed": sorted(a - b),
        "common": sorted(a & b),
        "changed": changed,
    }


def lint_versions(config: Config) -> list[str]:
    return changelog_lint(
        load_changelog(config.checks_dir), load_definitions(config.checks_dir)
    )


# -- Web dashboard helpers -----------------------------------------------------
# Site enumeration and changelog views used by the web backend (and the refresh
# command). They stay here, beside run_check, so they are exercised by tox and a
# web layer never has to reach into the data source or changelog internals.


def discover_sites(config: Config, *, tier: str | None = None) -> list[dict]:
    """The sites this deployment evaluates, as ``[{"site": ..., "environment": ...}]``.

    If ``config.sites`` lists sites for ``tier``, use exactly those (an explicit per-tier
    allowlist). Otherwise enumerate every environment from PuppetDB (each deployment points
    at one endpoint, i.e. one tier). Sorted by site id.
    """
    configured = config.sites_for(tier or "prod")
    if configured:
        return [
            {"site": s, "environment": config.environment_for(s)}
            for s in sorted(configured)
        ]

    from nectar_conformance.datasources.puppetdb import PuppetDBDataSource

    base_url = config.puppetdb.base_url or DEFAULT_PUPPETDB_URLS.get(
        tier or "prod"
    )
    environments = PuppetDBDataSource(config).list_environments(base_url)
    # site_environment maps site -> environment; invert so a configured override surfaces
    # the site label the rest of the tool uses. Default: site id == environment.
    env_to_site = {env: site for site, env in config.site_environment.items()}
    sites = [
        {"site": env_to_site.get(env, env), "environment": env}
        for env in environments
    ]
    return sorted(sites, key=lambda s: s["site"])


def pending_changes(config: Config, *, tier: str, as_of: date) -> list[Rule]:
    """Rules with an announced-but-not-yet-due change for ``tier`` at ``as_of``."""
    return [
        rule
        for rule in resolve_rules(config, tier=tier, as_of=as_of)
        if rule.has_pending
    ]


def _change_entry_to_dict(entry: ChangeEntry) -> dict:
    """A changelog entry as a complete dict for the dashboard timeline/history."""
    return {
        "check_id": entry.check_id,
        "value": entry.value,
        "effective": entry.effective,
        "due": entry.due,
        "tier": entry.tier,
        "severity": entry.severity,
        "note": entry.note,
    }


def _tier_visible(entry_tier: str, tier: str | None) -> bool:
    """Whether a directive's tier is visible to ``tier`` (None -> every tier)."""
    return tier is None or entry_tier == "all" or entry_tier == tier


def change_timeline(config: Config, *, tier: str | None = None) -> list[dict]:
    """Changelog directives as serialisable dicts, ordered for a history view.

    With ``tier`` set (a single-tier deployment), only that tier's directives and the
    tier-neutral ``all`` ones are returned; the other tier's directives are hidden.
    """
    changelog = load_changelog(config.checks_dir)
    entries = [
        _change_entry_to_dict(e)
        for e in changelog.entries
        if _tier_visible(e.tier, tier)
    ]
    return sorted(
        entries, key=lambda d: (d["effective"], d["due"] or "", d["check_id"])
    )


def change_history(
    config: Config, check_id: str, *, tier: str | None = None
) -> list[dict]:
    """The directives for one check (tier-filtered), ordered by effective then due date."""
    changelog = load_changelog(config.checks_dir)
    entries = [
        _change_entry_to_dict(e)
        for e in changelog.entries
        if e.check_id == check_id and _tier_visible(e.tier, tier)
    ]
    return sorted(entries, key=lambda d: (d["effective"], d["due"] or ""))


def list_changes(config: Config, *, tier: str, as_of: date) -> list[dict]:
    """Dated changes (entries with a ``due``) announced for ``tier`` by ``as_of``.

    Each carries the assertion ``op`` and ``target`` value needed to compute per-site
    adoption (see :mod:`nectar_conformance.rollout`).
    """
    changelog = load_changelog(config.checks_dir)
    definitions = load_definitions(config.checks_dir)
    out: list[dict] = []
    for e in changelog.entries:
        if e.due is None:
            continue
        if not _tier_visible(e.tier, tier):
            continue
        if date.fromisoformat(e.effective) > as_of:
            continue  # announced for the future; not active yet
        check = definitions.get(e.check_id)
        if check is None:
            continue
        out.append(
            {
                "check_id": e.check_id,
                "title": check.title,
                "op": check.assertion_op,
                "target": e.value,
                "effective": e.effective,
                "due": e.due,
                "tier": e.tier,
                "severity": e.severity or check.severity,
                "note": e.note,
            }
        )
    return out


@dataclass
class SquashResult:
    """Summary of a :func:`squash_changelog` run (counts + where files were written)."""

    name: str
    as_of: str
    archive_path: str
    changelog_path: str
    entries_before: int
    entries_after: int
    archived: int
    baselines: int
    carried: int


def _entry_to_mapping(entry: ChangeEntry) -> dict:
    """A changelog entry as an ordered, None-free mapping for serialisation."""
    out: dict = {"check_id": entry.check_id}
    if entry.value is not None:
        out["value"] = entry.value
    out["effective"] = entry.effective
    if entry.due is not None:
        out["due"] = entry.due
    if entry.tier != "all":  # "all" is the default, kept implicit as elsewhere
        out["tier"] = entry.tier
    if entry.severity is not None:
        out["severity"] = entry.severity
    if entry.note is not None:
        out["note"] = entry.note
    return out


def _render_changelog_yaml(changelog: Changelog, name: str, as_of: str) -> str:
    """Render a squashed changelog as YAML: a generated header, tags, then flow-style entries."""
    lines = [
        "---",
        f"# Conformance changelog, squashed to baseline {name} on {as_of} by",
        "# `nectar-conformance version squash`. Pre-baseline history is preserved verbatim in",
        f"# checks/archive/changelog-{name}.yaml (and in git). Append new dated directives below;",
        "# a conformance version is a named tag (a pinned evaluation date) over this log.",
        "",
        "tags:",
    ]
    for tag in sorted(changelog.tags):
        lines.append(f'  "{tag}": "{changelog.tags[tag]}"')
    lines.append("")
    lines.append("entries:")
    for entry in changelog.entries:
        body = yaml.safe_dump(
            _entry_to_mapping(entry),
            default_flow_style=True,
            sort_keys=False,
            allow_unicode=True,
            width=4096,  # keep each entry on one line, like the hand-authored log
        ).strip()
        lines.append(f"  - {body}")
    return "\n".join(lines) + "\n"


def squash_changelog(
    config: Config, *, name: str, as_of: str | None = None
) -> SquashResult:
    """Squash the changelog to a fresh baseline named ``name``, archiving the old log.

    Writes ``checks/archive/changelog-<name>.yaml`` (a verbatim copy of the pre-squash log) and
    a regenerated ``checks/changelog.yaml``. Refuses to run on a changelog that does not already
    lint clean, and never overwrites an existing archive or live file's history without a fresh
    tag. Raises a :class:`~nectar_conformance.errors.ConformanceError` subclass on any problem.
    """
    today = datetime.now(timezone.utc).date()
    if as_of:
        try:
            instant = date.fromisoformat(as_of)
        except ValueError as exc:
            raise VersionError(f"invalid --as-of date '{as_of}': {exc}")
    else:
        instant = today
    # The squash date is when the squash happens. Dating it in the future would bake
    # not-yet-due rollouts into the baseline and change what a live run reports today.
    if instant > today:
        raise VersionError(
            f"cannot squash as of a future date {instant.isoformat()}: the squash date "
            f"must be on or before today ({today.isoformat()})"
        )

    definitions = load_definitions(config.checks_dir)
    changelog = load_changelog(config.checks_dir)

    pre = changelog_lint(changelog, definitions)
    if pre:
        raise RuleError(
            "refusing to squash a changelog with problems: " + "; ".join(pre)
        )

    new_changelog = squash(
        changelog, definitions, as_of=instant, name=name
    )  # raises VersionError on a bad or duplicate name

    post = changelog_lint(new_changelog, definitions)
    if post:  # the squash should always produce a clean log; guard regardless
        raise RuleError(
            "squashed changelog failed lint (internal error): "
            + "; ".join(post)
        )

    checks_dir = writable_checks_dir(config.checks_dir)
    archive_dir = checks_dir / "archive"
    archive_path = archive_dir / f"changelog-{name}.yaml"
    changelog_path = checks_dir / "changelog.yaml"
    if archive_path.exists():
        raise RuleError(
            f"archive already exists, refusing to overwrite: {archive_path}"
        )

    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path.write_text(read_changelog_text(config.checks_dir))
    changelog_path.write_text(
        _render_changelog_yaml(new_changelog, name, instant.isoformat())
    )

    baselines = sum(
        1 for e in new_changelog.entries if e.note == f"baseline {name}"
    )
    return SquashResult(
        name=name,
        as_of=instant.isoformat(),
        archive_path=str(archive_path),
        changelog_path=str(changelog_path),
        entries_before=len(changelog.entries),
        entries_after=len(new_changelog.entries),
        archived=len(changelog.entries),
        baselines=baselines,
        carried=len(new_changelog.entries) - baselines,
    )
