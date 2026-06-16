"""Load and apply the JSON Schema for check definitions and the conformance changelog."""

from __future__ import annotations

import functools
from importlib import resources
import json
from typing import Any

import jsonschema

from nectar_conformance.errors import RuleError


@functools.lru_cache(maxsize=1)
def _schemas() -> dict:
    text = (
        resources.files("nectar_conformance.rules")
        .joinpath("schema.json")
        .read_text()
    )
    return json.loads(text)


def _validate(instance: Any, schema_key: str, label: str) -> None:
    schema = _schemas()[schema_key]
    validator = jsonschema.Draft202012Validator(schema)
    errors = sorted(
        validator.iter_errors(instance), key=lambda e: list(e.path)
    )
    if errors:
        first = errors[0]
        loc = "/".join(str(p) for p in first.path) or "<root>"
        raise RuleError(f"{label} is invalid at '{loc}': {first.message}")


def validate_definition(data: dict) -> None:
    """Validate a check definition; raise RuleError on the first problem."""
    _validate(data, "definition", f"check definition '{data.get('id', '?')}'")


def validate_changelog(data: dict) -> None:
    """Validate the conformance changelog; raise RuleError on the first problem."""
    _validate(data, "changelog", "conformance changelog")
