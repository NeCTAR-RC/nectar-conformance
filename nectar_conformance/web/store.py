"""Read-only access to the reports the refresh job publishes.

Layout under ``reports_dir`` (the shared PVC mount):

* ``reports/<site>.json`` -- one serialised Report per site;
* ``status.json``         -- last-run metadata (timestamp, tier, per-site errors).

Reads are cached by file mtime so repeated requests do not re-parse unchanged files. The
store never writes; only :mod:`nectar_conformance.web.refresh` does.
"""

from __future__ import annotations

import json
from pathlib import Path

_EMPTY_STATUS = {
    "tier": None,
    "generated_at": None,
    "version": None,
    "source": None,
    "sites": {},
    "errors": {},
}


class ReportStore:
    def __init__(self, reports_dir: Path):
        self.reports_dir = Path(reports_dir)
        self._reports_subdir = self.reports_dir / "reports"
        self._cache: dict[str, tuple[float, dict]] = {}
        self._status_cache: tuple[float, dict] | None = None

    def _site_path(self, site: str) -> Path:
        return self._reports_subdir / f"{site}.json"

    def site_ids(self) -> list[str]:
        if not self._reports_subdir.is_dir():
            return []
        return sorted(p.stem for p in self._reports_subdir.glob("*.json"))

    def get_report(self, site: str) -> dict | None:
        path = self._site_path(site)
        if not path.is_file():
            return None
        mtime = path.stat().st_mtime
        cached = self._cache.get(site)
        if cached is not None and cached[0] == mtime:
            return cached[1]
        data = json.loads(path.read_text())
        self._cache[site] = (mtime, data)
        return data

    def all_reports(self) -> dict[str, dict]:
        out: dict[str, dict] = {}
        for site in self.site_ids():
            report = self.get_report(site)
            if report is not None:
                out[site] = report
        return out

    def status(self) -> dict:
        path = self.reports_dir / "status.json"
        if not path.is_file():
            return dict(_EMPTY_STATUS)
        mtime = path.stat().st_mtime
        if self._status_cache is not None and self._status_cache[0] == mtime:
            return self._status_cache[1]
        data = json.loads(path.read_text())
        self._status_cache = (mtime, data)
        return data
