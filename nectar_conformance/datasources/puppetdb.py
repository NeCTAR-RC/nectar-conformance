"""PuppetDB data source (primary).

A site is a puppet environment, so every query filters by ``environment`` (exact,
server-side). This is robust across heterogeneous site layouts and cannot leak
another site's nodes. Reads the compiled catalog (classes + selected resource types)
and facts for each node and assembles a SiteModel.
"""

from __future__ import annotations

from datetime import datetime, timezone
from collections.abc import Iterable

import httpx

from nectar_conformance.config import Config
from nectar_conformance.errors import ConfigError, PQLError, SiteNotFoundError
from nectar_conformance.model import (
    CatalogResource,
    FactSet,
    NodeModel,
    SiteModel,
)
from nectar_conformance.datasources.base import DataSource

# Resource types always worth fetching even if no rule names them explicitly.
_DEFAULT_RESOURCE_TYPES = frozenset({"Docker::Run"})


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _q(value: str) -> str:
    """Quote a string for embedding in a PQL query."""
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


class PuppetDBDataSource(DataSource):
    name = "puppetdb"

    def __init__(self, config: Config, resource_types: Iterable[str] = ()):
        self.config = config
        self.pdb = config.puppetdb
        self.resource_types = set(_DEFAULT_RESOURCE_TYPES) | {
            t for t in resource_types
        }
        # Resolved per-site in load_site, since the default endpoint depends on tier.
        self._base_url: str | None = self.pdb.base_url
        self._client: httpx.Client | None = None

    # -- HTTP -------------------------------------------------------------------
    def _http(self) -> httpx.Client:
        if self._client is None:
            if not self._base_url:
                raise ConfigError("PuppetDB base_url is not configured")
            headers = {}
            token = self.pdb.resolved_token()
            if token:
                headers["X-Authentication"] = token
            cert = None
            if self.pdb.client_cert:
                cert = (
                    (self.pdb.client_cert, self.pdb.client_key)
                    if self.pdb.client_key
                    else self.pdb.client_cert
                )
            verify = self.pdb.ca_cert or self.pdb.verify
            self._client = httpx.Client(
                base_url=self._base_url,
                headers=headers,
                verify=verify,
                cert=cert,
                timeout=30.0,
            )
        return self._client

    def _pql(self, query: str) -> list:
        try:
            resp = self._http().post("/pdb/query/v4", json={"query": query})
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as exc:
            raise PQLError(f"PuppetDB query failed: {exc}") from exc

    # -- model building ---------------------------------------------------------
    def _facts_by_cert(self, env: str) -> dict:
        out: dict = {}
        for row in self._pql(
            f"facts[certname, name, value] {{ environment = {_q(env)} }}"
        ):
            out.setdefault(row["certname"], {})[row["name"]] = row["value"]
        return out

    def _classes_by_cert(self, env: str) -> dict:
        out: dict = {}
        query = f'resources[certname, title] {{ type = "Class" and environment = {_q(env)} }}'
        for row in self._pql(query):
            out.setdefault(row["certname"], []).append(row["title"])
        return out

    def _resources_by_cert(self, env: str) -> dict:
        out: dict = {}
        if not self.resource_types:
            return out
        type_filter = " or ".join(
            f"type = {_q(t)}" for t in sorted(self.resource_types)
        )
        query = (
            "resources[certname, type, title, parameters] "
            f"{{ environment = {_q(env)} and ({type_filter}) }}"
        )
        for row in self._pql(query):
            res = CatalogResource(
                type=row["type"],
                title=row["title"],
                parameters=row.get("parameters") or {},
            )
            out.setdefault(row["certname"], []).append(res)
        return out

    def list_environments(self, base_url: str | None = None) -> list[str]:
        """All distinct catalog environments known to PuppetDB (one per site).

        Used by the web dashboard to discover sites. The unfiltered projection returns one
        row per node, so distinct values are folded client-side. ``base_url`` overrides the
        endpoint (discovery has no site to resolve a per-tier default from).
        """
        if base_url:
            self._base_url = base_url
        rows = self._pql("nodes[catalog_environment] { }")
        return sorted(
            {
                r["catalog_environment"]
                for r in rows
                if r.get("catalog_environment")
            }
        )

    def load_site(self, site_id: str) -> SiteModel:
        self._base_url = self.config.puppetdb_base_url_for(site_id)
        env = self.config.environment_for(site_id)
        node_rows = self._pql(
            f"nodes[certname] {{ catalog_environment = {_q(env)} }}"
        )
        certnames = sorted({r["certname"] for r in node_rows})
        if not certnames:
            raise SiteNotFoundError(
                f"no nodes found for site '{site_id}' (environment '{env}')"
            )

        facts = self._facts_by_cert(env)
        classes = self._classes_by_cert(env)
        resources = self._resources_by_cert(env)

        nodes = []
        for certname in certnames:
            factset = FactSet(facts.get(certname, {}))
            nodes.append(
                NodeModel(
                    certname=certname,
                    environment=env,
                    site_id=site_id,
                    facts=factset,
                    classes=tuple(classes.get(certname, ())),
                    resources=tuple(resources.get(certname, ())),
                    source=self.name,
                    datacenter=factset.get("datacenter"),
                    nodegroup=factset.get("nodegroup"),
                    hardwaregroup=factset.get("hardwaregroup"),
                )
            )
        return SiteModel(
            site_id=site_id,
            source=self.name,
            collected_at=_now_iso(),
            nodes=tuple(nodes),
        )
