"""Cross-dataset overview: RelocaTE3 against RelocaTE2 on every benchmark.

Every other page scopes to a single dataset through the sidebar selector.
This one puts all datasets side by side so the headline question -- where
does RelocaTE3 lead, and where does it only tie -- is answerable without
switching datasets one at a time.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

# Streamlit executes multipage scripts with dashboard/pages as the import
# context. Add the repository root so the dashboard package remains importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.components.messages import show_empty
from dashboard.data.transforms import cross_dataset_summary
from dashboard.runtime import configure_page, load_suite

BASELINE = "relocate2"


def _is_baseline(caller: str) -> bool:
    return str(caller).lower().startswith("relocate2")


def _headline(summary: pd.DataFrame, focus: str) -> None:
    """One metric row per dataset: RelocaTE3 vs RelocaTE2, with the delta."""
    for key, block in summary.groupby("dataset_key", sort=False):
        label = block["dataset_label"].iloc[0]
        base = block[block["caller"].map(_is_baseline)]
        cand = block[block["caller"] == focus]
        if base.empty or cand.empty:
            continue
        st.markdown(f"**{label}**")
        columns = st.columns(3)
        for column, metric, name in zip(
            columns,
            ("detection_recall", "mean_sample_precision", "f1"),
            ("Recall", "Precision", "F1"),
            strict=True,
        ):
            new = float(cand[metric].iloc[0])
            old = float(base[metric].iloc[0])
            column.metric(
                name,
                f"{new:.3f}",
                delta=f"{new - old:+.3f} vs RelocaTE2",
                # A drop in a benchmark metric is bad; Streamlit's default
                # green-on-positive already encodes that correctly here.
            )


def main() -> None:
    configure_page("RelocaTE3 vs RelocaTE2")
    suite = load_suite()
    summary = cross_dataset_summary(suite)

    st.title("RelocaTE3 vs RelocaTE2")
    st.caption(
        "Pooled detection recall and mean per-sample precision across every "
        "benchmark dataset. F1 is their harmonic mean."
    )

    if summary.empty:
        show_empty("No benchmark reports are available yet.")
        return

    callers = sorted(summary["caller"].unique())
    candidates = [c for c in callers if not _is_baseline(c)]
    if not candidates:
        show_empty("No RelocaTE3 caller found alongside the RelocaTE2 baseline.")
        return

    default = next(
        (i for i, c in enumerate(candidates) if "blat" in c.lower() and "aln" in c.lower()),
        0,
    )
    focus = st.selectbox("RelocaTE3 variant", candidates, index=default)

    _headline(summary, focus)

    shown = summary[summary["caller"].map(_is_baseline) | (summary["caller"] == focus)]
    st.plotly_chart(
        px.bar(
            shown,
            x="dataset_label",
            y="f1",
            color="caller",
            barmode="group",
            title="F1 by dataset",
            labels={"dataset_label": "Dataset", "f1": "F1", "caller": "Caller"},
        ).update_yaxes(range=[0, 1]),
        width="stretch",
    )

    _divergence_panel(suite, focus)

    st.subheader("All variants, all datasets")
    st.dataframe(
        summary.pivot_table(
            index="caller", columns="dataset_label", values="f1"
        ).style.format("{:.3f}"),
        width="stretch",
    )


def _divergence_panel(suite, focus: str) -> None:
    """Recall against percent divergence from the canonical TE sequence.

    This is the panel that shows how each caller degrades as elements drift,
    which the per-dataset pages average away.
    """
    bundles = [b for b in suite.datasets if "divergence" in b.dataset_key]
    if not bundles:
        return
    bundle = bundles[0]
    frame = bundle.correctness
    if "divergence_percent" not in frame.columns:
        return

    scoped = frame[frame["caller"].map(_is_baseline) | (frame["caller"] == focus)]
    if scoped.empty:
        show_empty("The divergence panel has no runs for this variant yet.")
        return

    grouped = (
        scoped.groupby(["caller", "divergence_percent"], as_index=False, observed=True)[
            ["detected_events", "truth_events"]
        ]
        .sum()
        .assign(
            recall=lambda d: d["detected_events"] / d["truth_events"].replace(0, pd.NA)
        )
    )

    st.subheader("Divergence panel")
    st.caption(
        "Detection recall as the TE sequence drifts from the canonical copy. "
        "Pooled over coverage and replicate."
    )
    st.plotly_chart(
        px.line(
            grouped,
            x="divergence_percent",
            y="recall",
            color="caller",
            markers=True,
            title="Recall vs TE divergence",
            labels={
                "divergence_percent": "Divergence (%)",
                "recall": "Detection recall",
                "caller": "Caller",
            },
        ).update_yaxes(range=[0, 1], tickformat=".0%"),
        width="stretch",
    )


if __name__ == "__main__":
    main()
