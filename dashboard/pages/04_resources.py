"""Computational resource usage page."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Streamlit executes multipage scripts with dashboard/pages as the import
# context. Add the repository root so the dashboard package remains importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.components.filters import render_filters
from dashboard.components.messages import show_empty
from dashboard.data.transforms import apply_filters, resource_summary
from dashboard.plots.resources import memory_figure, runtime_figure
from dashboard.runtime import configure_page, load_bundle


def main() -> None:
    configure_page("Resources")
    bundle = load_bundle()
    selection = render_filters(bundle)
    resources = apply_filters(bundle.resources, selection)

    st.title("Computational resources")
    st.caption(
        f"Dataset: {bundle.dataset_label}. Measurements are comparable only when "
        "runs used the benchmark's "
        "standardized SLURM resources and execution conditions."
    )
    if resources.empty:
        show_empty("No resource rows match the active filters.")
        return

    data = resource_summary(resources)
    left, right = st.columns(2)
    with left:
        st.plotly_chart(runtime_figure(data), width="stretch")
    with right:
        st.plotly_chart(memory_figure(data), width="stretch")
    st.dataframe(data, hide_index=True, width="stretch")


if __name__ == "__main__":
    main()
