"""The normalised intermediate model the engine evaluates rules against.

A data source (PuppetDB or static repo) builds a :class:`SiteModel`; rules are
evaluated against it. Rules never see PQL or YAML, so a check is written once and
runs against any source. Role membership and host counts are first-class because two
of the canonical checks ("N hosts run role X", "roles defined in puppet-nectar") are
fundamentally about them.

A *site is a puppet environment*: ``SiteModel.site_id`` is the environment name.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CatalogResource:
    """A resource from a node's compiled catalog, e.g. ``Docker::Run[glance-api]``."""

    type: str
    title: str
    parameters: dict = field(default_factory=dict)

    @property
    def ref(self) -> str:
        return f"{self.type}[{self.title}]"


@dataclass(frozen=True)
class FactSet:
    """A node's facts, queried by dotted path (e.g. ``os.release.full``)."""

    raw: dict = field(default_factory=dict)

    def get(self, dotted: str, default: Any = None) -> Any:
        cur: Any = self.raw
        for key in dotted.split("."):
            if not isinstance(cur, dict) or key not in cur:
                return default
            cur = cur[key]
        return cur


@dataclass(frozen=True)
class NodeModel:
    """A single node within a site, source-agnostic."""

    certname: str
    environment: str  # the environment == the site
    site_id: str  # == environment by default
    facts: FactSet = field(default_factory=FactSet)
    classes: tuple[
        str, ...
    ] = ()  # ALL applied classes, including contained profiles
    resources: tuple[CatalogResource, ...] = ()
    source: str = "unknown"  # "puppetdb" | "static_repo"
    datacenter: str | None = None
    nodegroup: str | None = None
    hardwaregroup: str | None = None

    def has_class(self, name: str) -> bool:
        """Case-insensitive membership over the full applied class set.

        Matching the full set (not just top-level includes) means a contained profile
        such as ``nectar::profile::glance::api`` is found on a controller node even
        though the node only declares ``nectar::role::openstack::controller``.
        """
        target = name.lower()
        return any(c.lower() == target for c in self.classes)

    def roles(self) -> tuple[str, ...]:
        return tuple(
            c for c in self.classes if c.lower().startswith("nectar::role::")
        )

    def resource(self, type_: str, title: str) -> CatalogResource | None:
        t, ti = type_.lower(), title.lower()
        for res in self.resources:
            if res.type.lower() == t and res.title.lower() == ti:
                return res
        return None

    def has_resource(self, type_: str, title: str | None = None) -> bool:
        t = type_.lower()
        if title is None:
            return any(r.type.lower() == t for r in self.resources)
        return self.resource(type_, title) is not None


@dataclass(frozen=True)
class SiteModel:
    """A whole site (puppet environment) and its nodes."""

    site_id: str
    source: str
    collected_at: str  # ISO 8601 timestamp, for evidence / traceability
    nodes: tuple[NodeModel, ...] = ()

    def nodes_with_class(self, class_name: str) -> tuple[NodeModel, ...]:
        return tuple(n for n in self.nodes if n.has_class(class_name))

    # "role" is the operator-facing word; it is matched as a class (role or profile).
    nodes_with_role = nodes_with_class

    def count_role(self, class_name: str) -> int:
        return len(self.nodes_with_class(class_name))

    def nodes_with_resource(
        self, type_: str, title: str | None = None
    ) -> tuple[NodeModel, ...]:
        return tuple(n for n in self.nodes if n.has_resource(type_, title))
