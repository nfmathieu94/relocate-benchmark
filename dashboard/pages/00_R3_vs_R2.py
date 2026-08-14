"""Cross-dataset comparison: RelocaTE3 against RelocaTE2 on every benchmark.

Every other page scopes to a single dataset through the sidebar selector.
This one puts all datasets side by side so the headline question -- where
does RelocaTE3 lead, and where does it only tie -- is answerable without
switching datasets one at a time.

Figures come from ``dashboard.plots.overview`` so axis naming and the
shared-axis-title handling stay consistent with the rest of the dashboard.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Streamlit executes multipage scripts with dashboard/pages as the import
# context. Add the repository root so the dashboard package remains importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.components.messages import show_empty
from dashboard.data.transforms import cross_dataset_summary
from dashboard.plots.overview import dataset_comparison_figure, divergence_figure
from dashboard.runtime import configure_page, load_suite

METRICS = {
    "F1 score": "f1",
    "Detection recall": "detection_recall",
    "Overall precision": "mean_sample_precision",
}


def _is_baseline(caller: str) -> bool:
    return str(caller).lower().startswith("relocate2")


def _headline(summary: pd.DataFrame, focus: str) -> None:
    """One metric row per dataset: RelocaTE3 vs RelocaTE2, with the delta."""
    for _key, block in summary.groupby("dataset_key", sort=False):
        label = block["dataset_label"].iloc[0]
        base = block[block["caller"].map(_is_baseline)]
        cand = block[block["caller"] == focus]
        if base.empty or cand.empty:
            continue
        st.markdown(f"**{label}**")
        for column, (name, metric) in zip(
            st.columns(len(METRICS)), METRICS.items(), strict=True
        ):
            new = float(cand[metric].iloc[0])
            old = float(base[metric].iloc[0])
            column.metric(name, f"{new:.3f}", delta=f"{new - old:+.3f} vs RelocaTE2")


def _divergence_panel(suite, focus: str) -> None:
    """Recall against percent divergence, which per-dataset pages average away."""
    bundles = [b for b in suite.datasets if "divergence" in b.dataset_key]
    if not bundles:
        return
    frame = bundles[0].correctness
    if "divergence_percent" not in frame.columns:
        return

    st.subheader("TE divergence panel")
    st.caption(
        "Detection recall as the element drifts from the canonical TE "
        "sequence, pooled over replicates."
    )

    scoped = frame[frame["caller"].map(_is_baseline) | (frame["caller"] == focus)]
    if scoped.empty:
        show_empty("The divergence panel has no runs for this variant yet.")
        return

    grouped = (
        scoped.groupby(
            ["caller", "divergence_percent", "coverage"], as_index=False, observed=True
        )[["detected_events", "truth_events"]]
        .sum()
        .assign(
            recall=lambda d: d["detected_events"] / d["truth_events"].replace(0, pd.NA)
        )
    )
    st.plotly_chart(divergence_figure(grouped), width="stretch")


def main() -> None:
    configure_page("RelocaTE3 vs RelocaTE2")
    suite = load_suite()
    summary = cross_dataset_summary(suite)

    st.title("RelocaTE3 vs RelocaTE2")
    st.caption(
        "Pooled detection recall and mean per-sample precision across every "
        "benchmark dataset. F1 is their harmonic mean. This page compares "
        "datasets side by side; use the other pages to drill into one."
    )

    if summary.empty:
        show_empty("No benchmark reports are available yet.")
        return

    callers = sorted(summary["caller"].unique())
    candidates = [caller for caller in callers if not _is_baseline(caller)]
    if not candidates:
        show_empty("No RelocaTE3 caller found alongside the RelocaTE2 baseline.")
        return

    # Default to the release configuration (blat TE aligner + bwa aln genome
    # aligner) when it is present rather than whichever sorts first.
    default = next(
        (
            index
            for index, caller in enumerate(candidates)
            if "blat" in caller.lower() and "aln" in caller.lower()
        ),
        0,
    )
    focus = st.selectbox("RelocaTE3 variant", candidates, index=default)

    _headline(summary, focus)

    metric_label = st.radio(
        "Metric", tuple(METRICS), horizontal=True, key="overview_metric"
    )
    shown = summary[summary["caller"].map(_is_baseline) | (summary["caller"] == focus)]
    st.plotly_chart(
        dataset_comparison_figure(shown, METRICS[metric_label], metric_label),
        width="stretch",
    )

    _divergence_panel(suite, focus)

    st.subheader("Every variant, every dataset")
    st.caption("F1 score. Blank where that variant has not been run on that dataset.")
    st.dataframe(
        summary.pivot_table(index="caller", columns="dataset_label", values="f1"),
        width="stretch",
    )


if __name__ == "__main__":
    main()
