"""RelocaTE benchmark dashboard overview page."""
from __future__ import annotations

import sys
from pathlib import Path

# `streamlit run dashboard/app.py` puts only this file's directory on sys.path,
# not the repo root, so the absolute `dashboard.*` imports below fail on first
# load (they only start working once a page under dashboard/pages/ runs and adds
# the repo root globally). Add the repo root here so the entry script imports
# reliably on the very first load. Mirrors the inserts in dashboard/pages/*.py.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st

from dashboard.components.filters import render_filters
from dashboard.components.messages import show_empty
from dashboard.data.transforms import apply_filters, overall_summary
from dashboard.runtime import configure_page, load_bundle


def main() -> None:
    configure_page("Overview")
    bundle = load_bundle()
    selection = render_filters(bundle)
    correctness = apply_filters(bundle.correctness, selection)
    precision = apply_filters(bundle.precision, selection)

    st.title("RelocaTE benchmark dashboard")
    st.caption(
        f"Dataset: {bundle.dataset_label}. Interactive presentation of already "
        "aggregated benchmark reports. "
        "This application does not execute callers or recalculate truth matches."
    )

    callers = sorted(correctness["caller"].dropna().unique().tolist())
    samples = sorted(correctness["sample"].dropna().unique().tolist())
    coverages = sorted(correctness["coverage"].dropna().unique().tolist())
    classes = sorted(correctness["biological_class"].dropna().unique().tolist())
    somatic = correctness[
        correctness["biological_class"].str.contains("somatic", case=False, na=False)
    ]
    fractions = sorted(somatic["cellular_fraction"].dropna().unique().tolist())

    cols = st.columns(5)
    cols[0].metric("Callers", len(callers))
    cols[1].metric("Samples", len(samples))
    cols[2].metric("Coverages", len(coverages))
    cols[3].metric("Insertion classes", len(classes))
    cols[4].metric("Somatic fractions", len(fractions))

    st.subheader("Active benchmark slice")
    st.write(
        {
            "callers": callers,
            "coverages": coverages,
            "classes": classes,
            "somatic_cellular_fractions": fractions,
        }
    )

    st.subheader("Overall comparison")
    if correctness.empty or precision.empty:
        show_empty("No rows match the active filters.")
    else:
        summary = overall_summary(correctness, precision).rename(
            columns={
                "caller": "Caller",
                "detected_events": "Detected events",
                "truth_events": "Truth events",
                "detection_recall": "Pooled detection recall",
                "mean_sample_precision": "Mean per-sample precision",
            }
        )
        st.dataframe(
            summary,
            hide_index=True,
            width="stretch",
            column_config={
                "Pooled detection recall": st.column_config.NumberColumn(format="percent"),
                "Mean per-sample precision": st.column_config.NumberColumn(format="percent"),
            },
        )

    st.info(
        "Precision is read exclusively from `precision.tsv`. It is never "
        "inferred from the per-class `class_call_share` diagnostic."
    )


if __name__ == "__main__":
    main()
