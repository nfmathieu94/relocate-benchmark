"""Performance stratified by the multi-TE truth taxonomy."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.components.filters import render_filters
from dashboard.components.messages import show_empty
from dashboard.data.transforms import apply_filters, te_group_summary
from dashboard.plots.accuracy import te_group_figure, te_group_heatmap
from dashboard.runtime import configure_page, load_bundle

METRICS = {
    "Detection recall": "detection_recall",
    "Genotype-status accuracy | detected": "status_accuracy_given_detected",
    "Exact-TSD accuracy | detected": "exact_tsd_accuracy_given_detected",
}


def main() -> None:
    configure_page("TE groups")
    bundle = load_bundle()
    selection = render_filters(bundle)
    correctness = apply_filters(bundle.correctness, selection)

    st.title("Performance by TE group")
    st.caption(
        f"Dataset: {bundle.dataset_label}. Values are derived by summing the "
        "authoritative event counts within each curated truth group."
    )
    label = st.selectbox("Metric", tuple(METRICS), key="te_group_metric")
    data = te_group_summary(correctness, METRICS[label])
    if data.empty:
        show_empty(
            "This dataset has no TE-group metadata, or the active filters exclude it."
        )
        return

    st.plotly_chart(
        te_group_figure(data, f"{label} vs. coverage by TE group", label),
        width="stretch",
    )
    st.plotly_chart(
        te_group_heatmap(data, f"Mean {label.lower()} across selected coverages"),
        width="stretch",
    )
    st.dataframe(data, hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
