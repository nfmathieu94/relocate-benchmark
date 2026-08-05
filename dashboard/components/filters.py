"""Data-driven sidebar filters shared by every dashboard page."""
from __future__ import annotations

import streamlit as st

from dashboard.data.loaders import ReportBundle
from dashboard.data.transforms import FilterSelection, available_filters

_WIDGET_KEYS = {
    "callers": "filter_callers",
    "coverages": "filter_coverages",
    "divergences": "filter_divergences",
    "classes": "filter_classes",
    "cellular_fractions": "filter_cellular_fractions",
    "samples": "filter_samples",
    "replicates": "filter_replicates",
    "te_groups": "filter_te_groups",
    "te_classes": "filter_te_classes",
    "te_orders": "filter_te_orders",
    "te_superfamilies": "filter_te_superfamilies",
}


def _reset_filters(keys: list[str]) -> None:
    for key in keys:
        st.session_state.pop(key, None)


def render_filters(bundle: ReportBundle) -> FilterSelection:
    options = available_filters(bundle)
    # Scope every widget key by dataset so switching the dataset selector starts
    # from that dataset's own defaults. With one shared key per filter, a keyed
    # widget retains the previous dataset's selection; when the datasets have
    # disjoint values (e.g. sample names) the retained selection intersects to
    # empty and `isin([])` silently zeroes every row.
    keys = {
        name: f"{base}__{bundle.dataset_key}" for name, base in _WIDGET_KEYS.items()
    }
    with st.sidebar:
        st.header("Filters")
        st.button(
            "Reset filters",
            on_click=_reset_filters,
            args=(list(keys.values()),),
            width="stretch",
        )
        selected = {
            "callers": st.multiselect(
                "Caller", options["callers"], default=options["callers"], key=keys["callers"]
            ),
            "coverages": st.multiselect(
                "Coverage (x)", options["coverages"], default=options["coverages"], key=keys["coverages"]
            ),
            "classes": st.multiselect(
                "Insertion class", options["classes"], default=options["classes"], key=keys["classes"]
            ),
            "cellular_fractions": st.multiselect(
                "Cellular fraction",
                options["cellular_fractions"],
                default=options["cellular_fractions"],
                key=keys["cellular_fractions"],
            ),
            "samples": st.multiselect(
                "Sample", options["samples"], default=options["samples"], key=keys["samples"]
            ),
            "replicates": st.multiselect(
                "Replicate", options["replicates"], default=options["replicates"], key=keys["replicates"]
            ),
        }
        if options["divergences"]:
            selected["divergences"] = st.multiselect(
                "TE divergence (%)",
                options["divergences"],
                default=options["divergences"],
                key=keys["divergences"],
            )
        taxonomy = (
            ("te_groups", "TE group"),
            ("te_classes", "TE class"),
            ("te_orders", "TE order"),
            ("te_superfamilies", "TE superfamily"),
        )
        visible = [(name, label) for name, label in taxonomy if options[name]]
        if visible:
            st.subheader("TE taxonomy")
        for name, label in visible:
            selected[name] = st.multiselect(
                label,
                options[name],
                default=options[name],
                key=keys[name],
            )
    return FilterSelection(**{name: tuple(values) for name, values in selected.items()})
