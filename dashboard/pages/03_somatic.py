"""Somatic insertion performance page."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Streamlit executes multipage scripts with dashboard/pages as the import
# context. Add the repository root so the dashboard package remains importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.components.filters import render_filters
from dashboard.components.messages import show_empty
from dashboard.data.transforms import apply_filters, somatic_summary
from dashboard.plots.accuracy import somatic_figure
from dashboard.runtime import configure_page, load_bundle


def main() -> None:
    configure_page("Somatic performance")
    bundle = load_bundle()
    selection = render_filters(bundle)
    correctness = apply_filters(bundle.correctness, selection)
    data = somatic_summary(correctness)

    st.title("Somatic insertion performance")
    st.caption(
        f"Dataset: {bundle.dataset_label}. Recall across cellular fractions and "
        "expected variant allele frequencies "
        "using the benchmark's existing truth and detection counts."
    )
    if data.empty:
        show_empty(
            "The selected reports contain no somatic rows, or the active filters "
            "exclude all somatic conditions."
        )
        return

    st.plotly_chart(somatic_figure(data), width="stretch")
    st.dataframe(data, hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
