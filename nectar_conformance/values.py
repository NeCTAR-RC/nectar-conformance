"""Pattern-capable expected values.

A changelog entry's ``value`` is normally a literal (string, number, list). For checks
whose observed value churns without the requirement really changing (kolla image rebuild
suffixes), a value may instead be a **pattern mapping**::

    value: {regex: '29\\.4\\..*'}

The pattern is a Python regular expression matched against the whole observed string
(``re.fullmatch``), so an unanchored fragment can never match by accident. A plain scalar
value keeps exact-match semantics, which is how a security patch pins one specific build:
append a scalar entry that supersedes the pattern under the normal rollout rules.

This module is the single home for what counts as a pattern and how one is shown to a
human; it deliberately imports nothing from the rest of the package so the engine, the
rules layer and the reporters can all use it without layering cycles.
"""

from __future__ import annotations

import re
from typing import Any

PATTERN_KEY = "regex"

# Assertion ops whose expected value may be a pattern mapping. Value comparison is the
# only place a pattern substitutes for a literal; set-membership, counts and version
# floors keep literal values (changelog_lint enforces this).
PATTERN_CAPABLE_OPS = frozenset({"equals"})


def is_pattern(value: Any) -> bool:
    """Whether an expected value is a pattern mapping rather than a literal."""
    return isinstance(value, dict) and PATTERN_KEY in value


def pattern_text(value: Any) -> str:
    return str(value[PATTERN_KEY])


def matches(observed: Any, value: Any) -> bool:
    """Full-string match of ``observed`` against a pattern value."""
    return re.fullmatch(pattern_text(value), str(observed)) is not None


def describe(value: Any) -> str:
    """Render an expected value for humans: patterns read as a match, not a dict."""
    if is_pattern(value):
        return f"a value matching /{pattern_text(value)}/"
    return repr(value)
