"""Operator behaviour and schema/registry parity."""

from importlib import resources
import json

import pytest

from nectar_conformance.engine import operators


@pytest.mark.parametrize(
    "op,observed,expected,result",
    [
        ("equals", "x", "x", True),
        ("equals", "x", "y", False),
        ("not_equals", "x", "y", True),
        ("regex", "glance-api:30.1.0", r"30\.1\.0$", True),
        ("semver_gte", "10.11", "10.4", True),
        ("semver_gte", "10.4", "10.11", False),
        ("semver_gte", "24.04", "24.04", True),
        ("semver_eq", "10.4", "10.4", True),
        ("in_set", "a", ["a", "b"], True),
        ("in_set", "z", ["a", "b"], False),
        ("count_gte", 3, 2, True),
        ("count_gte", 1, 2, False),
        ("count_eq", 2, 2, True),
        ("count_lte", 1, 2, True),
        ("all_equal", ["x", "x"], None, True),
        ("all_equal", ["x", "y"], None, False),
        ("all_equal", [], None, True),
        ("present", True, None, True),
        ("present", False, None, False),
        ("present", None, None, False),
        ("absent", False, None, True),
        ("absent", True, None, False),
    ],
)
def test_operator(op, observed, expected, result):
    assert operators.apply(op, observed, expected) is result


def test_unknown_operator_raises():
    with pytest.raises(ValueError):
        operators.apply("nope", 1, 1)


def test_schema_and_registry_agree():
    text = (
        resources.files("nectar_conformance.rules")
        .joinpath("schema.json")
        .read_text()
    )
    schema = json.loads(text)
    enum = set(
        schema["definition"]["properties"]["assertion"]["properties"]["op"][
            "enum"
        ]
    )
    assert enum == set(operators.OPERATORS), (
        "schema op enum and operators registry diverge"
    )
