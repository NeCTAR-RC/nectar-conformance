"""Emit a Report as canonical JSON to a stream."""

from __future__ import annotations

from typing import TextIO

from nectar_conformance.results.model import Report
from nectar_conformance.results.serialise import report_to_json


def render(report: Report, stream: TextIO) -> None:
    stream.write(report_to_json(report))
    stream.write("\n")
