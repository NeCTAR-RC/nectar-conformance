"""Web/refresh runtime settings: the Config plus the few web-only knobs.

The conformance Config (PuppetDB, checks dir, ...) is loaded the usual layered way. The
deployment-level tier, the reports directory shared with the refresh job, and the SPA
static directory are web-only and read here from arguments or the ``NECTAR_CONFORMANCE_*``
environment.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from nectar_conformance import config as config_mod
from nectar_conformance.config import ENV_PREFIX

# Where the refresh job publishes reports and the web app reads them. In k8s this is the
# mount path of the shared PVC.
DEFAULT_REPORTS_DIR = "/var/lib/nectar-conformance"


@dataclass
class WebSettings:
    config: config_mod.Config
    tier: str
    reports_dir: Path
    static_dir: Path | None  # SPA bundle; None -> API only (no UI mounted)


def _packaged_static() -> Path | None:
    candidate = Path(__file__).resolve().parent / "static"
    return candidate if candidate.is_dir() else None


def load_settings(
    *,
    config_path: str | None = None,
    overrides: dict | None = None,
    tier: str | None = None,
    reports_dir: str | None = None,
    static_dir: str | None = None,
) -> WebSettings:
    """Build settings from explicit arguments, then the environment, then defaults."""
    config_path = config_path or os.environ.get(ENV_PREFIX + "CONFIG")
    cfg = config_mod.load(config_path, overrides)

    tier = tier or os.environ.get(ENV_PREFIX + "TIER") or "prod"
    reports = (
        reports_dir
        or os.environ.get(ENV_PREFIX + "REPORTS_DIR")
        or DEFAULT_REPORTS_DIR
    )
    static = static_dir or os.environ.get(ENV_PREFIX + "WEB_STATIC")
    static_path = Path(static) if static else _packaged_static()
    if static_path is not None and not static_path.is_dir():
        static_path = None
    return WebSettings(
        config=cfg,
        tier=tier,
        reports_dir=Path(reports),
        static_dir=static_path,
    )
