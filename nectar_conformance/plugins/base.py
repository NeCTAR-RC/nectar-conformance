"""Base class for escape-hatch check plugins.

A check definition with ``kind: plugin`` names a plugin (registered under the
``nectar_conformance.checks`` entry-point group). The plugin runs against the same
:class:`~nectar_conformance.model.SiteModel` and returns the same
:class:`~nectar_conformance.results.model.CheckResult` objects as declarative checks,
so plugin output is uniform with the rest of the report.
"""

from __future__ import annotations

import abc

from nectar_conformance.model import SiteModel
from nectar_conformance.results.model import CheckResult


class CheckPlugin(abc.ABC):
    """Implement complex checks that exceed the declarative operator vocabulary."""

    name: str = ""

    @abc.abstractmethod
    def run(self, model: SiteModel, rule, params: dict) -> list[CheckResult]:
        """Evaluate the check and return one or more CheckResults.

        ``rule`` is the resolved :class:`~nectar_conformance.rules.model.Rule` (for
        id, title, spec_section); ``params`` is ``plugin.params`` from the
        definition.
        """
        raise NotImplementedError
