"""Typed exceptions for nectar-conformance.

These let the CLI and engine degrade gracefully and map failures onto distinct
process exit codes (a conformance failure is not the same as the tool being unable
to run).
"""


class ConformanceError(Exception):
    """Base class for all nectar-conformance errors."""


class ConfigError(ConformanceError):
    """Configuration is missing or invalid."""


class DataSourceError(ConformanceError):
    """A data source could not produce a site model (operational failure)."""


class SiteNotFoundError(DataSourceError):
    """The requested site (puppet environment) has no nodes / does not exist."""


class PQLError(DataSourceError):
    """A PuppetDB query failed or returned an unexpected shape."""


class CatalogCompileError(DataSourceError):
    """A puppet catalog could not be compiled for a node."""


class RuleError(ConformanceError):
    """A check definition or the conformance changelog is malformed."""


class VersionError(RuleError):
    """A conformance version could not be resolved (unknown, or bad extends chain)."""
