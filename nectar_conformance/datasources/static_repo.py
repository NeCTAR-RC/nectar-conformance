"""Static-repo data source (secondary): build a model from compiled catalogs.

Primary purpose: pre-deployment / commissioning checks for a site that is not live
yet (so it has no nodes in PuppetDB). A site repo *is* a puppet environment.

Two modes:

* ``catalog_dir`` - read already-compiled catalog JSON (one file per node). Useful when
  catalogs are produced elsewhere (CI, or PuppetDB's catalogs endpoint).
* ``site_repo`` + ``facts_dir`` - compile each node's catalog from the repo via a
  configurable command (Phase 1.5; see :mod:`compile`). The node list comes from the
  facts files present. Per-node compile failures are logged and skipped; if every node
  fails, the whole load fails rather than reporting an empty (falsely-clean) site.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from nectar_conformance.config import Config
from nectar_conformance.errors import (
    CatalogCompileError,
    DataSourceError,
    SiteNotFoundError,
)
from nectar_conformance.model import (
    CatalogResource,
    FactSet,
    NodeModel,
    SiteModel,
)
from nectar_conformance.datasources.base import DataSource
from nectar_conformance.datasources.compile import (
    CatalogCompiler,
    build_compiler,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _node_from_catalog(
    catalog: dict, site_id: str, env: str, facts: dict
) -> NodeModel:
    certname = catalog.get("certname") or catalog.get("name") or "unknown"
    resources = []
    classes = []
    # Accept both a bare resources list (puppet catalog compile / octocatalog-diff) and
    # PuppetDB's catalog shape where resources are nested under {"data": [...]}.
    raw_resources = catalog.get("resources", [])
    if isinstance(raw_resources, dict):
        raw_resources = raw_resources.get("data", [])
    for res in raw_resources:
        rtype, title = res.get("type"), res.get("title")
        if rtype == "Class":
            classes.append(title)
        resources.append(
            CatalogResource(
                type=rtype, title=title, parameters=res.get("parameters") or {}
            )
        )
    factset = FactSet(facts)
    return NodeModel(
        certname=certname,
        environment=catalog.get("environment") or env,
        site_id=site_id,
        facts=factset,
        classes=tuple(classes),
        resources=tuple(resources),
        source="static_repo",
        datacenter=factset.get("datacenter"),
    )


class StaticRepoDataSource(DataSource):
    name = "static_repo"

    def __init__(
        self,
        config: Config,
        site_repo: str | None = None,
        catalog_dir: str | None = None,
        facts_dir: str | None = None,
        compiler: CatalogCompiler | None = None,
    ):
        self.config = config
        self.site_repo = site_repo
        self.catalog_dir = catalog_dir
        self.facts_dir = facts_dir
        self._compiler = compiler

    def _facts_for(self, certname: str) -> dict:
        if not self.facts_dir:
            return {}
        path = Path(self.facts_dir) / f"{certname}.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text())
        # Accept either a bare fact tree or a Puppet facts document with a "values" key.
        return data.get("values", data) if isinstance(data, dict) else {}

    # -- mode: pre-compiled catalog JSON ---------------------------------------
    def _from_catalog_dir(self, site_id: str, env: str) -> list:
        directory = Path(self.catalog_dir)
        if not directory.is_dir():
            raise DataSourceError(f"catalog_dir does not exist: {directory}")
        nodes = []
        for path in sorted(directory.glob("*.json")):
            try:
                catalog = json.loads(path.read_text())
            except json.JSONDecodeError as exc:
                raise DataSourceError(
                    f"invalid catalog JSON in {path.name}: {exc}"
                ) from exc
            certname = (
                catalog.get("certname") or catalog.get("name") or path.stem
            )
            nodes.append(
                _node_from_catalog(
                    catalog, site_id, env, self._facts_for(certname)
                )
            )
        return nodes

    # -- mode: compile from a site repo (Phase 1.5) ----------------------------
    def _from_compile(self, site_id: str, env: str) -> list:
        facts_root = Path(self.facts_dir)
        if not facts_root.is_dir():
            raise DataSourceError(f"facts_dir does not exist: {facts_root}")
        fact_files = sorted(facts_root.glob("*.json"))
        if not fact_files:
            raise SiteNotFoundError(
                f"no fact files in {facts_root}; cannot determine nodes to compile"
            )

        compiler = self._compiler or build_compiler(self.config)
        nodes = []
        failures = []
        for facts_path in fact_files:
            certname = facts_path.name[: -len(".json")]
            try:
                catalog = compiler.compile(
                    certname, str(facts_path), self.site_repo, env
                )
            except CatalogCompileError as exc:
                failures.append((certname, str(exc)))
                continue
            nodes.append(
                _node_from_catalog(
                    catalog, site_id, env, self._facts_for(certname)
                )
            )

        if failures and not nodes:
            detail = "; ".join(f"{cn}: {err}" for cn, err in failures)
            raise CatalogCompileError(
                f"all nodes failed to compile for '{site_id}': {detail}"
            )
        if failures:
            logger.warning(
                "%d of %d nodes failed to compile and are absent from the report: %s",
                len(failures),
                len(fact_files),
                ", ".join(cn for cn, _ in failures),
            )
        return nodes

    def load_site(self, site_id: str) -> SiteModel:
        env = self.config.environment_for(site_id)
        if self.catalog_dir:
            nodes = self._from_catalog_dir(site_id, env)
        elif self.site_repo and self.facts_dir:
            nodes = self._from_compile(site_id, env)
        else:
            raise CatalogCompileError(
                "static source needs either --catalog-dir (pre-compiled catalogs) or "
                "--site-repo together with --facts-dir (compile from the repo)"
            )
        if not nodes:
            raise SiteNotFoundError(f"no nodes produced for site '{site_id}'")
        return SiteModel(
            site_id=site_id,
            source=self.name,
            collected_at=_now_iso(),
            nodes=tuple(nodes),
        )
