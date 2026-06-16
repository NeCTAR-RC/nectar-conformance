"""Compile puppet catalogs for the static-repo data source (Phase 1.5).

The static source can either read pre-compiled catalog JSON (Phase 1) or compile
catalogs itself from a site repo (here). Compilation shells out to a configurable
command (default: octocatalog-diff) so it reuses puppet's own hiera resolution, eyaml
and certname-regex classification rather than reimplementing them.

The command is a template list with ``{certname}``, ``{facts}``, ``{repo}`` and
``{environment}`` placeholders, configured via ``static.compile_command`` so each
site can match its own toolchain. The compiler must print a catalog JSON document to
stdout.
"""

from __future__ import annotations

import abc
import json
import subprocess

from nectar_conformance.config import Config
from nectar_conformance.errors import CatalogCompileError

# Default invocation. Sites adjust this via config to match their toolchain.
DEFAULT_COMPILE_COMMAND = [
    "octocatalog-diff",
    "--catalog-only",
    "--no-color",
    "-n",
    "{certname}",
    "--fact-file",
    "{facts}",
    "--basedir",
    "{repo}",
    "--hiera-config",
    "{repo}/hiera.yaml",
]


class CatalogCompiler(abc.ABC):
    @abc.abstractmethod
    def compile(
        self, certname: str, facts_path: str, repo: str, environment: str
    ) -> dict:
        """Return the compiled catalog as a dict, or raise CatalogCompileError."""
        raise NotImplementedError


class CommandCompiler(CatalogCompiler):
    """Run an external command per node and parse its stdout as a catalog JSON doc."""

    def __init__(self, command: list | None = None, timeout: int = 120):
        self.command = list(command or DEFAULT_COMPILE_COMMAND)
        self.timeout = timeout

    def _render(
        self, certname: str, facts_path: str, repo: str, environment: str
    ) -> list:
        subs = {
            "certname": certname,
            "facts": facts_path,
            "repo": repo,
            "environment": environment,
        }
        return [arg.format(**subs) for arg in self.command]

    def compile(
        self, certname: str, facts_path: str, repo: str, environment: str
    ) -> dict:
        argv = self._render(certname, facts_path, repo, environment)
        try:
            proc = subprocess.run(
                argv,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise CatalogCompileError(
                f"compiler '{argv[0]}' not found; set static.compile_command"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise CatalogCompileError(
                f"compiling {certname} timed out"
            ) from exc
        if proc.returncode != 0:
            # The real error (e.g. "Could not find class ...") is at the START of the
            # compiler's output; the Ruby backtrace that follows is noise. Keep the head.
            detail = (proc.stderr or proc.stdout or "").strip()
            if len(detail) > 2000:
                detail = (
                    detail[:2000]
                    + "\n...[truncated; run the compiler by hand for more]"
                )
            raise CatalogCompileError(
                f"compiling {certname} failed (exit {proc.returncode}):\n{detail}"
            )
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise CatalogCompileError(
                f"compiler output for {certname} was not valid JSON: {exc}"
            ) from exc


def build_compiler(config: Config) -> CatalogCompiler:
    static = config.static
    return CommandCompiler(
        command=static.compile_command, timeout=static.compile_timeout
    )
