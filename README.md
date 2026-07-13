# nectar-conformance

A conformance checker for Nectar puppet-managed OpenStack cloud sites.

Nectar Core Services manage every site through a central puppet server. Sites drift
from the published specification over time. This tool tells a site operator how their
site conforms to a versioned Nectar conformance specification, what is wrong or
missing, and how to fix it.

## How it works

```
DataSource -> normalised Model -> Engine (versioned rules) -> Report -> human / JSON
```

- A **site is a puppet environment**. The tool identifies a site by the node's
  `environment` in PuppetDB.
- The **PuppetDB** data source (primary) reads the compiled catalog (resources and
  parameters, with hiera fully resolved) and facts for every node in the site's
  environment. The **static repo** data source reads pre-compiled catalog JSON, or
  compiles catalogs from a site repo, for pre-deployment and commissioning checks.
- **Checks** are curated by Core Services as value-free *definitions* (the logic) plus
  per-version *manifests* (which checks apply and their expected values). Conformance
  is versioned; several conformance versions are active at once.

## Usage

The check definitions and conformance changelog live in the separate
[`nectar-conformance-checks`](https://review.rc.nectar.org.au) repository, not in this
tool. Every command that reads them needs a checks directory: pass `--checks-dir <path>`,
set `NECTAR_CONFORMANCE_CHECKS_DIR`, or set `checks_dir` in the config file. The examples
below omit it for brevity.

```
nectar-conformance check run --site ardctest --conformance-version 2025.1
nectar-conformance check run --site ardctest --conformance-version 2025.1 --format json
nectar-conformance check list --conformance-version 2025.1
nectar-conformance check show glance.api.image_tag
nectar-conformance version list
nectar-conformance version diff 2024.1 2025.1
```

Static source (no live PuppetDB), either pre-compiled catalogs or compile-from-repo:

```
# pre-compiled catalog JSON, one file per node
nectar-conformance check run --site ardctest --source static \
  --catalog-dir ./catalogs --facts-dir ./facts

# compile from the site repo (one node per facts file; compiler set via
# static.compile_command in config, defaults to octocatalog-diff)
nectar-conformance check run --site ardctest --source static \
  --site-repo /path/to/site-repo --facts-dir ./facts
```

### Will a change fix conformance before it goes live?

A site is a puppet environment, and r10k deploys each branch of the control repo as its
own environment, so you can check a *proposed* change pre-merge and compare it to the
live site. Capture the live baseline, capture the proposed environment, and diff them:

```
# baseline: the live site
nectar-conformance check run --site ardctest --conformance-version 2025.1 \
  --format json > before.json

# the proposed change, deployed as a branch environment (--environment keeps the
# 'ardctest' label but queries that environment)
nectar-conformance check run --site ardctest --environment ardctest_fix_glance \
  --conformance-version 2025.1 --format json > after.json

# what does the change fix, and does it break anything? (exit 1 if it regresses)
nectar-conformance report diff before.json after.json
```

For a truly offline check (no deploy, no node runs), produce `after.json` with the
static source by compiling the proposed branch (`--source static --site-repo ...`); that
needs the environment's modules assembled, which is what octocatalog-diff / r10k do.

Exit codes: `0` conformant, `1` any conformance failure, `2` usage error, `3`
operational error (PuppetDB unreachable, etc.). `report diff` exits `1` if the
change introduces any new failure.

## Development

```
tox            # run unit tests and lint
tox -e pep8    # lint only
```

Releases use [reno](https://docs.openstack.org/reno/) for release notes. Contributions
go through gerrit; use conventional commits and `git commit -s`.
