"""The fixed assertion-operator vocabulary.

Each operator is a small pure function ``(observed, expected) -> bool``. The set of
names here must stay in sync with the ``assertion.op`` enum in ``rules/schema.json``
(a test asserts parity). Operators may raise; the runner catches that and records the
check as UNKNOWN rather than crashing the run.
"""

from __future__ import annotations

from collections.abc import Callable
import re
from typing import Any

from packaging.version import Version

_PRESENT_FALSE = (None, False)


def _to_version(value: Any) -> Version:
    # Use the leading dotted-numeric portion so tags like "10.11" or "24.04" parse.
    text = str(value).strip()
    match = re.match(r"\d+(?:\.\d+)*", text)
    return Version(match.group(0) if match else text)


def op_equals(observed: Any, expected: Any) -> bool:
    return observed == expected


def op_not_equals(observed: Any, expected: Any) -> bool:
    return observed != expected


def op_regex(observed: Any, expected: Any) -> bool:
    return re.search(str(expected), str(observed)) is not None


def op_semver_gte(observed: Any, expected: Any) -> bool:
    return _to_version(observed) >= _to_version(expected)


def op_semver_eq(observed: Any, expected: Any) -> bool:
    return _to_version(observed) == _to_version(expected)


def op_in_set(observed: Any, expected: Any) -> bool:
    if not isinstance(expected, (list, tuple, set)):
        raise ValueError("in_set expects a list value")
    return observed in expected


def op_count_gte(observed: Any, expected: Any) -> bool:
    return int(observed) >= int(expected)


def op_count_eq(observed: Any, expected: Any) -> bool:
    return int(observed) == int(expected)


def op_count_lte(observed: Any, expected: Any) -> bool:
    return int(observed) <= int(expected)


def op_all_equal(observed: Any, expected: Any) -> bool:
    # observed is a collection of values; pass if they are homogeneous.
    values = list(observed)
    return len(values) <= 1 or all(v == values[0] for v in values[1:])


def op_present(observed: Any, expected: Any) -> bool:
    return observed not in _PRESENT_FALSE


def op_absent(observed: Any, expected: Any) -> bool:
    return observed in _PRESENT_FALSE


OPERATORS: dict[str, Callable[[Any, Any], bool]] = {
    "equals": op_equals,
    "not_equals": op_not_equals,
    "regex": op_regex,
    "semver_gte": op_semver_gte,
    "semver_eq": op_semver_eq,
    "in_set": op_in_set,
    "count_gte": op_count_gte,
    "count_eq": op_count_eq,
    "count_lte": op_count_lte,
    "all_equal": op_all_equal,
    "present": op_present,
    "absent": op_absent,
}

# Operators whose query yields a single aggregate (site-level), not a per-node value.
SITE_LEVEL_OPS = frozenset({"count_gte", "count_eq", "count_lte", "all_equal"})


def apply(op: str, observed: Any, expected: Any) -> bool:
    try:
        func = OPERATORS[op]
    except KeyError:
        raise ValueError(f"unknown assertion operator '{op}'")
    return func(observed, expected)
