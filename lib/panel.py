"""Normalize simulator panel manifests for benchmark task generation.

Legacy panels provide ``sample``/``replicate`` columns and one root-level
``truth_events.tsv``. Treatment panels may instead provide ``dataset_id``,
``divergence_replicate``, and a row-specific ``truth_tsv``. This module gives
both layouts one stable benchmark-facing schema without changing source data.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path


def _required(row: dict[str, str], field: str, line_number: int) -> str:
    value = (row.get(field) or "").strip()
    if not value:
        raise ValueError(
            f"panel manifest row {line_number} is missing required field {field!r}"
        )
    return value


def _sample_name(row: dict[str, str], line_number: int) -> str:
    sample = (row.get("sample") or "").strip()
    if sample:
        return sample
    dataset_id = _required(row, "dataset_id", line_number)
    coverage = _required(row, "coverage", line_number)
    coverage_token = re.sub(r"[^A-Za-z0-9]+", "p", coverage).strip("p")
    if not coverage_token:
        raise ValueError(
            f"panel manifest row {line_number} has invalid coverage {coverage!r}"
        )
    return f"{dataset_id}_cov{coverage_token}x"


def read_panel_manifest(panel_root: Path) -> list[dict[str, str]]:
    """Read and normalize ``panel_manifest.tsv`` under ``panel_root``."""
    panel_root = Path(panel_root)
    manifest = panel_root / "panel_manifest.tsv"
    if not manifest.is_file():
        raise FileNotFoundError(f"panel manifest missing: {manifest}")
    with manifest.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        if not reader.fieldnames:
            raise ValueError(f"panel manifest has no header: {manifest}")
        source_rows = list(reader)
    if not source_rows:
        raise ValueError(f"panel manifest has no data rows: {manifest}")

    normalized = []
    seen_samples: set[str] = set()
    for line_number, source in enumerate(source_rows, start=2):
        row = dict(source)
        row["coverage"] = _required(row, "coverage", line_number)
        row["r1"] = _required(row, "r1", line_number)
        row["r2"] = _required(row, "r2", line_number)
        row["sample"] = _sample_name(row, line_number)
        row["replicate"] = (
            (row.get("replicate") or "").strip()
            or _required(row, "divergence_replicate", line_number)
        )
        row["truth_tsv"] = (
            (row.get("truth_tsv") or "").strip() or "truth_events.tsv"
        )
        if row["sample"] in seen_samples:
            raise ValueError(
                f"panel manifest sample is not unique: {row['sample']!r}"
            )
        seen_samples.add(row["sample"])
        normalized.append(row)
    return normalized


def panel_path(panel_root: Path, value: str) -> Path:
    """Resolve a manifest path while requiring it to be panel-relative."""
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError(f"panel manifest path must be relative and contained: {value}")
    return Path(panel_root) / relative
