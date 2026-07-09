"""Resolve a rule selector to the set of nodes it applies to."""

from __future__ import annotations

from nectar_conformance.engine.queries import MISSING
from nectar_conformance.model import NodeModel, SiteModel
from nectar_conformance.rules.model import Selector


def resolve(model: SiteModel, selector: Selector) -> list[NodeModel]:
    """Return the nodes a selector matches.

    ``site`` and ``all`` both return every node; the distinction is only that a
    ``site`` selector signals the check is evaluated once for the whole site (the
    runner decides that from the query type, e.g. ``count``).

    ``all_of`` matches the nodes satisfying every sub-clause (AND); the schema
    keeps it one level deep. A ``fact_match`` with ``match: present`` selects the
    nodes where the fact path exists at all (a fact legitimately set to null still
    counts as present); the default is exact equality against ``value``.
    """
    stype = selector.type
    params = selector.params

    if stype in ("all", "site"):
        return list(model.nodes)
    if stype == "all_of":
        keep: set | None = None
        for sub in params["selectors"]:
            clause = Selector(
                type=sub["type"],
                params={k: v for k, v in sub.items() if k != "type"},
            )
            matched = {n.certname for n in resolve(model, clause)}
            keep = matched if keep is None else keep & matched
        return [n for n in model.nodes if n.certname in (keep or set())]
    if stype == "contains_class":
        return list(model.nodes_with_class(params["class"]))
    if stype == "has_resource":
        return list(
            model.nodes_with_resource(
                params["resource_type"], params.get("resource_title")
            )
        )
    if stype == "fact_match":
        path = params["path"]
        if params.get("match") == "present":
            return [
                n
                for n in model.nodes
                if n.facts.get(path, MISSING) is not MISSING
            ]
        return [
            n for n in model.nodes if n.facts.get(path) == params.get("value")
        ]
    raise ValueError(f"unknown selector type '{stype}'")
