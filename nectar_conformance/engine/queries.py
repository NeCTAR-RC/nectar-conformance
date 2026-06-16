"""Read values from the model for a rule's query, capturing where they came from."""

from __future__ import annotations

import re
from typing import Any

from nectar_conformance.model import NodeModel, SiteModel
from nectar_conformance.rules.model import Query


class MissingValue:
    """Sentinel: the query target does not exist on a node (distinct from a None value)."""


MISSING = MissingValue()


def _apply_extract(value: Any, extract: str | None) -> Any:
    if not extract or value is None:
        return value
    if extract.startswith("regex:"):
        pattern = extract[len("regex:") :]
        match = re.search(pattern, str(value))
        if not match:
            return MISSING
        if "value" in (match.groupdict() or {}):
            return match.group("value")
        return match.group(1) if match.groups() else match.group(0)
    raise ValueError(f"unsupported extract directive '{extract}'")


def node_value(node: NodeModel, query: Query) -> tuple[Any, str]:
    """Return ``(observed, locator)`` for a per-node query (fact or resource_param).

    ``observed`` is :data:`MISSING` when the target is absent on the node.
    """
    p = query.params
    if query.type == "fact":
        path = p["path"]
        val = node.facts.get(path, MISSING)
        return val, f"fact:{path}"
    if query.type == "resource_param":
        rtype, rtitle, param = (
            p["resource_type"],
            p["resource_title"],
            p["param"],
        )
        res = node.resource(rtype, rtitle)
        if res is None or param not in res.parameters:
            return MISSING, f"{rtype}[{rtitle}].{param}"
        val = _apply_extract(res.parameters[param], p.get("extract"))
        return val, f"{rtype}[{rtitle}].{param}"
    if query.type == "class_present":
        class_name = p["class"]
        return node.has_class(class_name), f"class:{class_name}"
    raise ValueError(f"query type '{query.type}' is not a per-node query")


def site_count(model: SiteModel, query: Query) -> tuple[int, str]:
    """Count nodes matching the query's criterion (class or resource)."""
    p = query.params
    if "class" in p:
        return model.count_role(p["class"]), f"count:class:{p['class']}"
    if "resource_type" in p:
        title = p.get("resource_title")
        nodes = model.nodes_with_resource(p["resource_type"], title)
        ref = p["resource_type"] + (f"[{title}]" if title else "")
        return len(nodes), f"count:resource:{ref}"
    raise ValueError(
        "count query needs a 'class' or 'resource_type' parameter"
    )
