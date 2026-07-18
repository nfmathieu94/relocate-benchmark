"""Consistent actionable dashboard messages."""
from __future__ import annotations

import streamlit as st

from dashboard.data.validation import ReportValidationError


def show_validation_error(error: ReportValidationError) -> None:
    st.error("The benchmark reports cannot be displayed safely.")
    st.code(str(error), language=None)
    st.info(
        "Regenerate the combined reports with `bash pipeline/aggregate.sh`, "
        "or select a complete report directory with `--report-dir`. The "
        "dashboard does not modify malformed results."
    )


def show_empty(message: str) -> None:
    st.info(message)

