"""Conformance checker for Nectar puppet-managed OpenStack cloud sites."""

from importlib.metadata import PackageNotFoundError, version

# Falls back when not installed, e.g. running from a bare checkout.
try:
    __version__ = version("nectar-conformance")
except PackageNotFoundError:
    __version__ = "0.0.0+unknown"
