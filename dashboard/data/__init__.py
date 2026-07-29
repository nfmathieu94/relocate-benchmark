"""Validated report loading and display-only transformations."""

from .loaders import (
    BenchmarkSuite,
    ReportBundle,
    load_report,
    load_report_suite,
    load_reports,
)
from .validation import ReportValidationError

__all__ = ["ReportBundle", "ReportValidationError", "load_report", "load_reports"]
