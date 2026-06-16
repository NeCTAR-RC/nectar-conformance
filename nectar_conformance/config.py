"""Layered configuration: command-line flags > environment > config file > defaults.

The PuppetDB read token is never inlined in the config file (which may live in a
gerrit repo); it comes from the environment or a referenced ``token_file``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from nectar_conformance.errors import ConfigError

ENV_PREFIX = "NECTAR_CONFORMANCE_"
DEFAULT_CONFIG_PATHS = (
    Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config")))
    / "nectar-conformance"
    / "config.yaml",
    Path("/etc/nectar-conformance/config.yaml"),
)

# Sites treated as the "test" tier by default, so dated changes are enforced there
# before production without needing a config entry. The `site_tier` config map (or the
# `--site-tier` flag) still overrides this per site, and any unlisted site stays "prod".
DEFAULT_TEST_SITES = frozenset(
    {
        "ardctest",
        "rctest",
        "site1test",
        "site2test",
        "site3test",
        "site4test",
    }
)

# Default PuppetDB endpoint per site tier, used when no base_url is configured. A site's
# tier comes from `site_tier_for`, so test sites query the test PuppetDB and everything
# else queries production. These are placeholder hosts: set the real endpoints via config,
# the NECTAR_CONFORMANCE_PUPPETDB_URL env var, or --puppetdb-url, which override them.
DEFAULT_PUPPETDB_URLS = {
    "prod": "https://puppetdb.example.org:8080",
    "test": "https://puppetdb-test.example.org:8080",
}

# Example sites the web dashboard evaluates per tier, by default. Built in so dev and the
# deployments share one source of truth without any config; a `sites` config entry (or the
# Helm chart's `sites` value) overrides a tier's list with the real site ids per deployment.
DEFAULT_SITES = {
    "prod": [
        "ardc",
        "site1",
        "site2",
        "site3",
        "site4",
        "site5",
        "site6",
        "site7",
        "site8",
    ],
    "test": [
        "ardctest",
        "site1test",
        "site2test",
        "site3test",
        "site4test",
    ],
}


@dataclass
class PuppetDBConfig:
    base_url: str | None = None
    token: str | None = None
    token_file: str | None = None
    ca_cert: str | None = None
    client_cert: str | None = None
    client_key: str | None = None
    verify: bool = True

    def resolved_token(self) -> str | None:
        if self.token:
            return self.token
        if self.token_file:
            path = Path(self.token_file).expanduser()
            if not path.exists():
                raise ConfigError(
                    f"PuppetDB token_file does not exist: {path}"
                )
            return path.read_text().strip()
        return None


@dataclass
class StaticConfig:
    # Catalog-compile command template for the static source (Phase 1.5). Placeholders:
    # {certname} {facts} {repo} {environment}. None -> compile.DEFAULT_COMPILE_COMMAND.
    compile_command: list | None = None
    compile_timeout: int = 120


@dataclass
class Config:
    puppetdb: PuppetDBConfig = field(default_factory=PuppetDBConfig)
    static: StaticConfig = field(default_factory=StaticConfig)
    source: str = "puppetdb"
    default_conformance_version: str | None = None
    # Optional site_id -> puppet environment overrides (default: site_id == environment).
    site_environment: dict = field(default_factory=dict)
    # Optional site_id -> tier (test|prod) map; controls when dated changes are enforced.
    # Overrides the built-in DEFAULT_TEST_SITES. An unlisted site that is not a known test
    # site defaults to "prod" (held to the enforced schedule, fail-safe).
    site_tier: dict = field(default_factory=dict)
    # Optional tier -> list of site ids the web refresh should evaluate. When set for a
    # deployment's tier, exactly those sites are evaluated instead of discovering every
    # environment from PuppetDB. Keyed by tier so one config serves both the prod and test
    # deployment.
    sites: dict = field(default_factory=dict)
    # Directory holding the check definitions/changelog (the nectar-conformance-checks
    # repo). Required at load time: there is no packaged fallback. Set via the checks_dir
    # config key, NECTAR_CONFORMANCE_CHECKS_DIR, or --checks-dir.
    checks_dir: str | None = None

    def environment_for(self, site_id: str) -> str:
        return self.site_environment.get(site_id, site_id)

    def site_tier_for(self, site_id: str) -> str:
        # Explicit config/flag wins; then the built-in test sites; else "prod" (fail-safe).
        if site_id in self.site_tier:
            return self.site_tier[site_id]
        if site_id in DEFAULT_TEST_SITES:
            return "test"
        return "prod"

    def sites_for(self, tier: str) -> list | None:
        # Configured allowlist wins (even an explicit empty list); else the built-in default
        # for the tier; else None (let discovery enumerate PuppetDB).
        if tier in self.sites:
            return self.sites[tier]
        return DEFAULT_SITES.get(tier)

    def puppetdb_base_url_for(self, site_id: str) -> str | None:
        # Explicit base_url wins; otherwise fall back to the per-tier default endpoint.
        if self.puppetdb.base_url:
            return self.puppetdb.base_url
        return DEFAULT_PUPPETDB_URLS.get(self.site_tier_for(site_id))


def _load_file(path: str | None) -> dict:
    if path is not None:
        p = Path(path).expanduser()
        if not p.exists():
            raise ConfigError(f"config file not found: {p}")
        return yaml.safe_load(p.read_text()) or {}
    for candidate in DEFAULT_CONFIG_PATHS:
        if candidate.exists():
            return yaml.safe_load(candidate.read_text()) or {}
    return {}


def _from_env() -> dict:
    out: dict = {}
    pdb: dict = {}
    mapping = {
        "PUPPETDB_URL": ("puppetdb", "base_url"),
        "PUPPETDB_TOKEN": ("puppetdb", "token"),
        "PUPPETDB_TOKEN_FILE": ("puppetdb", "token_file"),
        "PUPPETDB_CA_CERT": ("puppetdb", "ca_cert"),
        "PUPPETDB_CLIENT_CERT": ("puppetdb", "client_cert"),
        "PUPPETDB_CLIENT_KEY": ("puppetdb", "client_key"),
        "SOURCE": ("source",),
        "CONFORMANCE_VERSION": ("default_conformance_version",),
        "CHECKS_DIR": ("checks_dir",),
    }
    for suffix, dest in mapping.items():
        val = os.environ.get(ENV_PREFIX + suffix)
        if val is None:
            continue
        if dest[0] == "puppetdb":
            pdb[dest[1]] = val
        else:
            out[dest[0]] = val
    if pdb:
        out["puppetdb"] = pdb
    return out


def _merge(base: dict, overlay: dict) -> dict:
    out = dict(base)
    for key, value in overlay.items():
        if value is None:
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(
    config_path: str | None = None, overrides: dict | None = None
) -> Config:
    """Build a Config from file, then environment, then explicit flag overrides."""
    data = _load_file(config_path)
    data = _merge(data, _from_env())
    if overrides:
        data = _merge(data, overrides)

    pdb_data = data.get("puppetdb", {}) or {}
    puppetdb = PuppetDBConfig(
        base_url=pdb_data.get("base_url"),
        token=pdb_data.get("token"),
        token_file=pdb_data.get("token_file"),
        ca_cert=pdb_data.get("ca_cert"),
        client_cert=pdb_data.get("client_cert"),
        client_key=pdb_data.get("client_key"),
        verify=pdb_data.get("verify", True),
    )
    static_data = data.get("static", {}) or {}
    static = StaticConfig(
        compile_command=static_data.get("compile_command"),
        compile_timeout=static_data.get("compile_timeout", 120),
    )
    return Config(
        puppetdb=puppetdb,
        static=static,
        source=data.get("source", "puppetdb"),
        default_conformance_version=data.get("default_conformance_version"),
        site_environment=data.get("site_environment", {}) or {},
        site_tier=data.get("site_tier", {}) or {},
        sites=data.get("sites", {}) or {},
        checks_dir=data.get("checks_dir"),
    )
