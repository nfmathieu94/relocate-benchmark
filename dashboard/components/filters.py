"""Data-driven sidebar filters shared by every dashboard page."""
from __future__ import annotations

import streamlit as st

from dashboard.data.loaders import ReportBundle
from dashboard.data.transforms import FilterSelection, available_filters

_WIDGET_KEYS = {
    "callers": "filter_callers",
    "coverages": "filter_coverages",
    "classes": "filter_classes",
    "cellular_fractions": "filter_cellular_fractions",
    "samples": "filter_samples",
    "replicates": "filter_replicates",
}


def _reset_filters() -> None:
    for key in _WIDGET_KEYS.values():
        st.session_state.pop(key, None)


def render_filters(bundle: ReportBundle) -> FilterSelection:
    options = available_filters(bundle)
    with st.sidebar:
        st.header("Filters")
        st.button("Reset filters", on_click=_reset_filters, width="stretch")
        selected = {
            "callers": st.multiselect(
                "Caller", options["callers"], default=options["callers"], key=_WIDGET_KEYS["callers"]
            ),
            "coverages": st.multiselect(
                "Coverage (x)", options["coverages"], default=options["coverages"], key=_WIDGET_KEYS["coverages"]
            ),
            "classes": st.multiselect(
                "Insertion class", options["classes"], default=options["classes"], key=_WIDGET_KEYS["classes"]
            ),
            "cellular_fractions": st.multiselect(
                "Cellular fraction",
                options["cellular_fractions"],
                default=options["cellular_fractions"],
                key=_WIDGET_KEYS["cellular_fractions"],
            ),
            "samples": st.multiselect(
                "Sample", options["samples"], default=options["samples"], key=_WIDGET_KEYS["samples"]
            ),
            "replicates": st.multiselect(
                "Replicate", options["replicates"], default=options["replicates"], key=_WIDGET_KEYS["replicates"]
            ),
        }
    return FilterSelection(**{name: tuple(values) for name, values in selected.items()})
