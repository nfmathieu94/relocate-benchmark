"""Accuracy metrics page."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Streamlit executes multipage scripts with dashboard/pages as the import
# context. Add the repository root so the dashboard package remains importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.components.filters import render_filters
from dashboard.components.messages import show_empty
from dashboard.data.transforms import (
    accuracy_summary,
    apply_filters,
    head_to_head_long,
    precision_summary,
)
from dashboard.plots.accuracy import accuracy_figure, caller_comparison_figure
from dashboard.runtime import configure_page, load_bundle

METRICS = {
    "Detection recall": "detection_recall",
    "Genotype-status accuracy | detected": "status_accuracy_given_detected",
    "Exact-TSD accuracy | detected": "exact_tsd_accuracy_given_detected",
    "Overall precision": "overall_precision",
    "False-discovery rate": "false_discovery_rate",
    "False-positive calls": "false_positive_calls",
}


def main() -> None:
    configure_page("Accuracy")
    bundle = load_bundle()
    selection = render_filters(bundle)

    st.title("Accuracy")
    label = st.selectbox("Metric", tuple(METRICS))
    metric = METRICS[label]

    if metric in {"overall_precision", "false_discovery_rate", "false_positive_calls"}:
        source = apply_filters(bundle.precision, selection)
        data = precision_summary(source, metric) if not source.empty else source
        st.caption(
            "This is a global per-sample metric from `precision.tsv`; insertion-class "
            "and cellular-fraction filters do not alter its denominator."
        )
    else:
        source = apply_filters(bundle.correctness, selection)
        data = accuracy_summary(source, metric) if not source.empty else source

    if data.empty:
        show_empty("No accuracy rows match the active filters.")
        return

    y_label = "Mean false-positive calls" if metric == "false_positive_calls" else label
    left, right = st.columns(2)
    with left:
        st.plotly_chart(
            caller_comparison_figure(data, f"{label}: caller comparison", y_label),
            width="stretch",
        )
    with right:
        st.plotly_chart(
            accuracy_figure(data, f"{label} vs. coverage", y_label),
            width="stretch",
        )

    if metric == "exact_tsd_accuracy_given_detected":
        st.caption(
            "Exact-TSD accuracy is calculated from the authoritative "
            "`tsd_exact_events / detected_events` counts in `correctness.tsv`."
        )

    st.subheader("Direct caller comparison")
    direct = apply_filters(head_to_head_long(bundle.head_to_head), selection)
    if direct.empty:
        show_empty("No head-to-head rows match the active filters.")
    else:
        direct_plot = direct.rename(columns={"detection_recall": "value"})
        st.plotly_chart(
            caller_comparison_figure(
                direct_plot,
                "Head-to-head detection recall from `head_to_head.tsv`",
                "Detection recall",
            ),
            width="stretch",
        )


if __name__ == "__main__":
    main()
