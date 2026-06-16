"""FastAPI app factory and the ``nectar-conformance-web`` console entry point.

The app serves the JSON API under ``/api`` and, when a built SPA bundle is present, serves
it for every other path (with a client-side-routing fallback to ``index.html``).
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

from nectar_conformance import __version__
from nectar_conformance.web.api import build_router
from nectar_conformance.web.settings import WebSettings, load_settings
from nectar_conformance.web.store import ReportStore


def create_app(settings: WebSettings | None = None) -> FastAPI:
    if settings is None:
        settings = load_settings()
    store = ReportStore(settings.reports_dir)
    app = FastAPI(
        title="nectar-conformance dashboard",
        version=__version__,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )
    app.state.settings = settings
    app.state.store = store
    app.include_router(build_router(settings, store))
    _mount_spa(app, settings)
    return app


def _mount_spa(app: FastAPI, settings: WebSettings) -> None:
    static_dir = settings.static_dir
    if static_dir is None:
        return
    index = static_dir / "index.html"

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        # The API router is registered first and wins; anything reaching here that still
        # looks like an API path is a genuine miss, not an SPA route.
        if full_path.startswith("api"):
            raise HTTPException(status_code=404, detail="not found")
        candidate = (static_dir / full_path).resolve()
        if static_dir in candidate.parents and candidate.is_file():
            return FileResponse(candidate)
        if index.is_file():
            return FileResponse(
                index
            )  # client-side route -> serve the SPA shell
        raise HTTPException(status_code=404, detail="not found")


# Importable target for `uvicorn nectar_conformance.web.app:app`. The console entry below
# uses the factory form so --reload works.
app = create_app()


def main(argv: list[str] | None = None) -> int:
    import argparse
    import os

    import uvicorn

    from nectar_conformance.config import ENV_PREFIX

    parser = argparse.ArgumentParser(
        prog="nectar-conformance-web",
        description="Serve the nectar-conformance dashboard (read-only).",
    )
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument(
        "--reports-dir", help="directory the refresh job publishes reports to"
    )
    parser.add_argument("--tier", choices=["test", "prod"])
    parser.add_argument("--config", help="path to a config file")
    parser.add_argument("--checks-dir", help="load check data from this dir")
    parser.add_argument("--static-dir", help="SPA bundle to serve")
    parser.add_argument(
        "--reload", action="store_true", help="auto-reload (development)"
    )
    args = parser.parse_args(argv)

    # The factory (possibly in a reloader subprocess) reads settings from the environment.
    if args.reports_dir:
        os.environ[ENV_PREFIX + "REPORTS_DIR"] = args.reports_dir
    if args.tier:
        os.environ[ENV_PREFIX + "TIER"] = args.tier
    if args.config:
        os.environ[ENV_PREFIX + "CONFIG"] = args.config
    if args.checks_dir:
        os.environ[ENV_PREFIX + "CHECKS_DIR"] = args.checks_dir
    if args.static_dir:
        os.environ[ENV_PREFIX + "WEB_STATIC"] = args.static_dir

    uvicorn.run(
        "nectar_conformance.web.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
