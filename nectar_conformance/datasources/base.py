"""The DataSource contract and a small factory.

A data source turns a site id into a :class:`~nectar_conformance.model.SiteModel`. The
engine only ever sees the model, so PuppetDB, static-repo compilation and test
fixtures are interchangeable.
"""

from __future__ import annotations

import abc
from collections.abc import Iterable

from nectar_conformance.config import Config
from nectar_conformance.errors import ConfigError
from nectar_conformance.model import SiteModel


class DataSource(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    def load_site(self, site_id: str) -> SiteModel:
        """Build the normalised model for a site (puppet environment)."""
        raise NotImplementedError


def get_datasource(
    name: str,
    config: Config,
    resource_types: Iterable[str] = (),
    **kwargs,
) -> DataSource:
    """Instantiate a data source by name.

    ``resource_types`` lets the caller (CLI) tell the PuppetDB source which catalog
    resource types the loaded rules actually need, so it can fetch only those.
    """
    if name == "puppetdb":
        from nectar_conformance.datasources.puppetdb import PuppetDBDataSource

        return PuppetDBDataSource(config, resource_types=resource_types)
    if name in ("static", "static_repo"):
        from nectar_conformance.datasources.static_repo import (
            StaticRepoDataSource,
        )

        return StaticRepoDataSource(config, **kwargs)
    raise ConfigError(f"unknown data source '{name}'")
