"""Configuration, environment, and report provenance page."""
from __future__ import annotations

import sys
import tomllib
from datetime import datetime
from pathlib import Path

import streamlit as st

# Streamlit executes multipage scripts with dashboard/pages as the import
# context. Add the repository root so the dashboard package remains importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.components.filters import render_filters
from dashboard.runtime import configure_page, load_bundle


def _modified(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).astimezone().isoformat(timespec="seconds")


def main() -> None:
    configure_page("Provenance")
    bundle = load_bundle()
    render_filters(bundle)

    st.title("Provenance and interpretation")
    st.warning(
        "The current benchmark uses a fixed-length 3-bp wildcard TSD pattern "
        "for RelocaTE3 while the truth panel contains 4–5 bp TSDs. Interpret "
        "exact-TSD accuracy with that limitation."
    )

    config_path = Path("config/benchmark.toml")
    if config_path.is_file():
        with open(config_path, "rb") as handle:
            config = tomllib.load(handle)
        dataset = config.get("dataset", {})
        callers = {
            name: values
            for name, values in config.get("callers", {}).items()
            if values.get("enabled") is True
        }
        st.subheader("Dataset")
        st.json(
            {
                "panel_root": dataset.get("panel_root"),
                "reference": dataset.get("reference"),
                "te_library": dataset.get("te_library"),
                "te_name": dataset.get("te_name"),
            }
        )
        st.subheader("Enabled callers")
        st.json(callers)
        with st.expander("Complete benchmark configuration"):
            st.code(config_path.read_text(), language="toml")
    else:
        st.warning(f"Configuration file not found: {config_path}")

    st.subheader("Pinned caller environments")
    for path in (
        Path("callers/relocate3/pixi.toml"),
        Path("callers/relocate2/images.txt"),
        Path("callers/relocate2/pinned-modules.txt"),
    ):
        if path.is_file():
            with st.expander(str(path)):
                st.code(path.read_text(), language="toml" if path.suffix == ".toml" else None)

    st.subheader("Report files")
    rows = []
    for name in ("correctness.tsv", "precision.tsv", "head_to_head.tsv", "resources.tsv"):
        path = bundle.report_dir / name
        rows.append(
            {
                "report": name,
                "path": str(path),
                "bytes": path.stat().st_size,
                "modified": _modified(path),
            }
        )
    st.dataframe(rows, hide_index=True, width="stretch")

    st.subheader("Metric interpretation")
    st.markdown(
        """
        - **Detection recall:** matched truth events divided by truth events.
        - **Status accuracy:** correct genotype status among detected events.
        - **Overall precision:** matched calls divided by all calls, sourced from
          `precision.tsv`.
        - **Class call share:** a diagnostic share of all calls, not precision.
        - **Resources:** GNU `time -v` measurements collected by the array runner.
        """
    )


if __name__ == "__main__":
    main()
