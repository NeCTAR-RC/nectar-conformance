"""Discover check plugins registered under the ``nectar_conformance.checks`` group."""

from __future__ import annotations

import functools
from importlib.metadata import entry_points

from nectar_conformance.plugins.base import CheckPlugin

ENTRY_POINT_GROUP = "nectar_conformance.checks"


@functools.lru_cache(maxsize=1)
def _registry() -> dict[str, CheckPlugin]:
    found: dict[str, CheckPlugin] = {}
    for ep in entry_points(group=ENTRY_POINT_GROUP):
        plugin_cls = ep.load()
        instance = plugin_cls()
        found[instance.name or ep.name] = instance
    return found


def get_plugin(name: str) -> CheckPlugin | None:
    return _registry().get(name)
