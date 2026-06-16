"""Static-repo auto-compilation (Phase 1.5) with a mocked compiler."""

from conftest import FACTS_DIR
import pytest

from nectar_conformance.config import Config
from nectar_conformance.datasources.compile import CommandCompiler
from nectar_conformance.datasources.static_repo import StaticRepoDataSource
from nectar_conformance.errors import CatalogCompileError

DB1 = "db1.example.test"
MQ1 = "mq1.example.test"


class FakeCompiler:
    def __init__(self, fail=()):
        self.fail = set(fail)
        self.calls = []

    def compile(self, certname, facts_path, repo, environment):
        self.calls.append((certname, facts_path, repo, environment))
        if certname in self.fail:
            raise CatalogCompileError(f"boom {certname}")
        return {
            "certname": certname,
            "environment": environment,
            "resources": [{"type": "Class", "title": "Nectar::Profile::Test"}],
        }


def _source(compiler):
    return StaticRepoDataSource(
        Config(),
        site_repo="/repo",
        facts_dir=str(FACTS_DIR),
        compiler=compiler,
    )


def test_compile_path_builds_model():
    fake = FakeCompiler()
    model = _source(fake).load_site("ardctest")
    assert {n.certname for n in model.nodes} == {DB1, MQ1}
    assert all(n.has_class("nectar::profile::test") for n in model.nodes)
    # The compiler is given the repo, environment and per-node fact file.
    assert all(
        call[2] == "/repo" and call[3] == "ardctest" for call in fake.calls
    )
    # Facts are still attached from facts_dir for facts-based checks.
    db1 = next(n for n in model.nodes if n.certname == DB1)
    assert db1.facts.get("mariadb.version") == "10.11"


def test_compile_partial_failure_skips_node():
    model = _source(FakeCompiler(fail={MQ1})).load_site("ardctest")
    assert {n.certname for n in model.nodes} == {DB1}


def test_compile_all_fail_raises():
    with pytest.raises(CatalogCompileError):
        _source(FakeCompiler(fail={DB1, MQ1})).load_site("ardctest")


def test_command_compiler_renders_placeholders():
    compiler = CommandCompiler(
        command=[
            "x",
            "-n",
            "{certname}",
            "--repo",
            "{repo}",
            "--env",
            "{environment}",
            "--facts",
            "{facts}",
        ]
    )
    argv = compiler._render("node1", "/f.json", "/repo", "ardctest")
    assert argv == [
        "x",
        "-n",
        "node1",
        "--repo",
        "/repo",
        "--env",
        "ardctest",
        "--facts",
        "/f.json",
    ]


def test_command_compiler_missing_binary():
    compiler = CommandCompiler(
        command=["nectar-conformance-no-such-binary", "{certname}"]
    )
    with pytest.raises(CatalogCompileError):
        compiler.compile("n", "/f.json", "/repo", "ardctest")


def test_command_compiler_non_json_output():
    compiler = CommandCompiler(command=["echo", "not json"])
    with pytest.raises(CatalogCompileError):
        compiler.compile("n", "/f.json", "/repo", "ardctest")
