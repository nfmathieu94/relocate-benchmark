"""Shared Streamlit runtime helpers."""
from __future__ import annotations

from pathlib import Path

import streamlit as st

from dashboard.components.messages import show_validation_error
from dashboard.config import report_dir_from_args
from dashboard.data.loaders import BenchmarkSuite, ReportBundle, load_report_suite
from dashboard.data.validation import ReportValidationError


@st.cache_data(ttl=60, show_spinner="Validating benchmark reports...")
def _cached_load(report_dir: str) -> BenchmarkSuite:
    return load_report_suite(Path(report_dir))


def configure_page(title: str) -> None:
    st.set_page_config(
        page_title=f"{title} | RelocaTE benchmark",
        page_icon="🧬",
        layout="wide",
    )


def load_bundle() -> ReportBundle:
    report_dir = report_dir_from_args()
    try:
        suite = _cached_load(str(report_dir))
    except ReportValidationError as error:
        show_validation_error(error)
        st.stop()
        raise AssertionError("streamlit.stop() returned unexpectedly")
    if len(suite.datasets) == 1:
        bundle = suite.datasets[0]
    else:
        keys = [bundle.dataset_key for bundle in suite.datasets]
        selected = st.sidebar.selectbox(
            "Benchmark dataset",
            keys,
            format_func=lambda key: suite.by_key(key).dataset_label,
            key="benchmark_dataset",
        )
        bundle = suite.by_key(selected)
    st.sidebar.caption(f"Dataset: **{bundle.dataset_label}** (`{bundle.dataset_key}`)")
    st.sidebar.caption(f"Reports: `{bundle.report_dir}`")
    return bundle
