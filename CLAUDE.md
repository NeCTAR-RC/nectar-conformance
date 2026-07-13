# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`nectar-conformance` checks how a Nectar puppet-managed OpenStack **site** conforms to a
versioned Nectar conformance specification, reports what is wrong, and says how to fix it.
A site is a **puppet environment**: the tool identifies a site by the node's `environment`.

Full design rationale lives in `/home/sam/.claude/plans/read-braindump-compressed-galaxy.md`
and the source material is `braindump` and `nectar-specification-doc.md` in this repo.

## Commands

```bash
tox                       # default envlist: py3 (pytest + coverage) and pep8 (flake8)
tox -e pep8               # lint only
.venv/bin/pytest tests/test_engine.py::test_image_tag_drift_fails   # a single test
pip install -e '.[test]'  # editable install into a venv (needed to refresh CLI entry points)
```

- `tox -e releasenotes` (reno) only works once the repo has at least one git commit; reno
  scans `HEAD`, so it fails on a fresh repo. It is not in the default envlist.
- The CLI entry point is `nectar-conformance` (see `cli/main.py`). The check data lives in
  the separate `nectar-conformance-checks` repo, so every command that reads it needs a
  `--checks-dir` (or `NECTAR_CONFORMANCE_CHECKS_DIR` / the `checks_dir` config key); there is
  no packaged fallback. Try it offline against the bundled fixtures (`tests/fixtures/checks`
  carries a mirror of the definitions plus a frozen changelog):
  ```bash
  nectar-conformance check run --site ardctest --conformance-version 2026.1 \
    --checks-dir tests/fixtures/checks \
    --source static --catalog-dir tests/fixtures/catalogs --facts-dir tests/fixtures/facts
  ```
- Squash the changelog into a fresh yearly baseline (writes files, so point `--checks-dir` at a
  `nectar-conformance-checks` checkout). The new version is dated to the squash date, which
  defaults to today; `--as-of` must be on or before today:
  ```bash
  nectar-conformance version squash --name 2027.0
  ```

## Architecture

The pipeline is `DataSource -> SiteModel -> engine.evaluate(model, rules) -> Report -> reporter`.

- **`model.py`** is the single contract. A `SiteModel` holds `NodeModel`s (facts, applied
  `classes`, catalog `resources`). The engine only ever sees this, so PuppetDB, static-repo
  compilation, and test fixtures are interchangeable. `engine/runner.py:evaluate` is a **pure
  function** (no I/O) so the CLI and a future web dashboard drive it identically.
- **Data sources** (`datasources/`) build a `SiteModel`. `puppetdb.py` is primary: it filters
  every PQL query by `environment` (exact, server-side). `static_repo.py` is secondary, for
  pre-deployment / commissioning of sites not yet in PuppetDB; it either reads pre-compiled
  catalog JSON (`--catalog-dir`) or compiles per node from a site repo (`--site-repo` +
  `--facts-dir`) via the pluggable `compile.py:CatalogCompiler` (configurable command,
  defaults to octocatalog-diff). The node list comes from the facts files present.
- **Checks are two layers** (`rules/` here + the data in the `nectar-conformance-checks` repo).
  A **definition** (`definitions/*.yaml` in that repo) is value-free logic: selector (which
  nodes) + query (what to read) + assertion operator + remediation template. The **changelog**
  (`changelog.yaml` in that repo) is an append-only list of
  dated, tier-scoped `ChangeEntry` directives that bind each check's **expected value** over
  time (Glance tag, MariaDB floor, etc.), plus named `tags` (a tag is a pinned date == a
  "conformance version"). `rules/changelog.py:fold` resolves the log for one site tier at one
  instant into the `Rule`s the engine runs: it picks the latest enforced value and, when a
  change is pending (announced but not yet due), the upcoming value so the engine accepts it
  early and emits a "due in N days" advisory. The engine compares observed against the enforced
  value (and the pending value when set) and stays a pure function; the temporal decision is
  baked into each `Rule` by the fold, with `now` injected via `--as-of` (default: today).

## Conventions that bite

- **A conformance "version" is a named `tag` in the changelog: a pinned evaluation date**,
  unrelated to any OpenStack version. There is no `<major>.<minor>` tree or subset invariant;
  the spec is the changelog fold and a tag just reproduces it at a date. `rules/changelog.py:`
  `changelog_lint` checks structural soundness instead (known check ids, `effective <= due`,
  test due not later than prod due, no colliding entries); a test asserts the shipped changelog
  passes it. Dates are date-granular UTC; a change is enforced **on and from** its due date.
- **A version is also the boundary of a yearly `squash`** that stops the append-only log from
  growing forever. `rules/changelog.py:squash` (pure; orchestrated by `service.py:`
  `squash_changelog` and the `version squash` command) folds the log at the squash date into
  fresh value-free baseline entries (one per check, collapsing `test`/`prod` to `all` when they
  agree), carries pending/future entries forward verbatim, drops the superseded history, and
  pins a new tag to the squash date. **The squash date is when the squash happens (defaults to
  today; `--as-of` must be on or before today)** — dating it in the future is refused because it
  would bake not-yet-due rollouts into the baseline and change what a live run reports. A no-flag
  `check run` stays live (it does not adopt the new tag as a pinned default). Baselines keep the
  **winning enforced entry's real
  `effective` date, not the squash date** — using the squash date would outrank a carried
  pending entry and silently drop a rollout. The full pre-squash log is copied verbatim to
  `checks/archive/changelog-<name>.yaml` (history is never lost). Folding the squashed log at
  any date on/after the squash reproduces the original behaviour; older dates are served by the
  archive, so `version diff` across a squash boundary is a known gap.
- **`version diff` reports value changes, not just check-id sets**: `service.py:diff_versions`
  folds both tag dates (neutral tier `prod`) and adds a `changed` list of `expected` value
  differences alongside `added`/`removed`.
- **Test sites get dated changes before production**: a `ChangeEntry.tier` of `test`/`prod`
  scopes a directive, and a site's tier comes from `config.site_tier` (default `prod`,
  fail-safe) or the `--site-tier` flag. `tier: all` (the default) matches every site.
- **The operator vocabulary must stay in sync** between `rules/schema.json` (the
  `assertion.op` enum) and `engine/operators.py` (the `OPERATORS` registry).
  `tests/test_operators.py::test_schema_and_registry_agree` fails if they diverge.
- **The check data is not in this repo; tests carry their own mirror**:
  `tests/fixtures/checks/` holds a frozen `changelog.yaml` plus a copy of the real
  `definitions/`, loaded via the `fixture_changelog`/`fixture_definitions`/`fixture_rules`
  helpers in `tests/conftest.py`. The frozen changelog binds the values the `site_model` and
  static catalog fixtures satisfy, so a dated rollout in the `nectar-conformance-checks` repo
  never forces a test update. There is no packaged fallback, so every test that loads checks
  passes a `--checks-dir` (or `checks_dir=`) pointing at this mirror; `test_loader_schema.py`
  also asserts the loader *requires* a dir. **The real changelog is validated in the
  `nectar-conformance-checks` repo's CI (`nectar-conformance changelog lint`), not here.** Do
  not add value-coupled assertions against the real changelog.
- **Pre-merge "will this fix conformance?" flow**: a site is an environment, so
  `check run --site ardctest --environment <branch-env>` checks a proposed branch
  environment while keeping the `ardctest` label. `report diff before.json after.json`
  (`results/compare.py`) classifies fixed/regressed/still-failing and exits `1` on any
  regression, for CI gating.
- **cliff turns entry-point underscores into spaces**: `check_run` -> `check run`,
  `version_diff` -> `version diff`. Adding or renaming a command means editing the
  `[project.entry-points."nectar_conformance.cli"]` table in `pyproject.toml` and
  reinstalling (`pip install -e .`) so the entry point is re-registered.
- **Class matching is case-insensitive and over the full applied class set** (catalog
  containment), because puppet stores class titles in PascalCase and roles include contained
  profiles. Selectors therefore prefer the contained profile class (e.g.
  `nectar::profile::glance::api`) or resource presence over the role class.
- **Check data is NOT packaged.** The definitions and changelog live in the separate
  `nectar-conformance-checks` repo and are supplied at runtime via `--checks-dir` /
  `NECTAR_CONFORMANCE_CHECKS_DIR` / `checks_dir`; only `rules/schema.json` ships as package
  data. `rules/loader.py` raises a clear `RuleError` when no checks dir is configured (no
  fallback). In k8s the Helm chart git-syncs that repo into a volume both pods mount, so a
  changelog change is a push to it, not a tool release.

## Exit codes (CLI)

`0` conformant, `1` any conformance failure, `2` usage error, `3` operational error
(PuppetDB unreachable, unknown version, missing repo). Every check is blocking; there
is no severity concept.
