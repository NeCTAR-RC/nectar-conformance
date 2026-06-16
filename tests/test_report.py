"""Report serialisation (JSON contract) and human rendering."""

import io
import json

from conftest import FIXTURE_TAG_DATE, VERSION, fixture_rules

from nectar_conformance.engine.runner import evaluate
from nectar_conformance.report import human
from nectar_conformance.results.model import REPORT_SCHEMA_VERSION
from nectar_conformance.results.serialise import report_to_dict, report_to_json


def _report(site_model):
    rules = fixture_rules(tier="prod", as_of=FIXTURE_TAG_DATE)
    return evaluate(site_model, rules, VERSION)


def test_json_contract(site_model):
    report = _report(site_model)
    data = report_to_dict(report)
    assert data["schema_version"] == REPORT_SCHEMA_VERSION
    assert data["site"] == "ardctest"
    assert data["conformance_version"] == "2026.1"
    assert set(data["summary"]) >= {"total", "pass", "fail", "score", "result"}
    assert isinstance(data["results"], list) and data["results"]
    # Round-trips through JSON.
    assert json.loads(report_to_json(report)) == data


def test_human_render_contains_key_lines(site_model):
    report = _report(site_model)
    buf = io.StringIO()
    human.render(report, buf)
    text = buf.getvalue()
    assert "Nectar Conformance Report" in text
    assert "glance.api.image_tag" in text
    assert "Result:" in text
