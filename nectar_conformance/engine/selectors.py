"""Resolve a rule selector to the set of nodes it applies to."""

from __future__ import annotations

from nectar_conformance.model import NodeModel, SiteModel
from nectar_conformance.rules.model import Selector


def resolve(model: SiteModel, selector: Selector) -> list[NodeModel]:
    """Return the nodes a selector matches.

    ``site`` and ``all`` both return every node; the distinction is only that a
    ``site`` selector signals the check is evaluated once for the whole site (the
    runner decides that from the query type, e.g. ``count``).
    """
    stype = selector.type
    params = selector.params

    if stype in ("all", "site"):
        return list(model.nodes)
    if stype == "contains_class":
        return list(model.nodes_with_class(params["class"]))
    if stype == "has_resource":
        return list(
            model.nodes_with_resource(
                params["resource_type"], params.get("resource_title")
            )
        )
    if stype == "fact_match":
        path, want = params["path"], params.get("value")
        return [n for n in model.nodes if n.facts.get(path) == want]
    raise ValueError(f"unknown selector type '{stype}'")
