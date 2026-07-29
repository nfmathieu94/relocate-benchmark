"""Read one or more isolated benchmark-dataset report bundles."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .validation import REPORT_SPECS, ReportSpec, ReportValidationError, validate_report


def pretty_caller(key: str) -> str:
    """Display label for a caller key.

    ``relocate3-<te>-<genome>`` -> ``RelocaTE3-<te>/<genome>``; ``relocate2`` ->
    ``RelocaTE2``. Mirrors ``pipeline/config_env.py::pretty_caller`` and the R
    ``pretty_caller`` so the dashboard, PDF, and figures agree.
    """
    m = re.match(r"^relocate3-([^-]+)-(.+)$", key)
    if m:
        return f"RelocaTE3-{m.group(1)}/{m.group(2)}"
    if key.lower().startswith("relocate"):
        return "RelocaTE" + key[len("relocate") :]
    return key


@dataclass(frozen=True)
class ReportBundle:
    report_dir: Path
    correctness: pd.DataFrame
    precision: pd.DataFrame
    head_to_head: pd.DataFrame
    resources: pd.DataFrame
    dataset_key: str = "benchmark"
    dataset_label: str = "Benchmark"

    def frames(self) -> dict[str, pd.DataFrame]:
        return {
            "correctness": self.correctness,
            "precision": self.precision,
            "head_to_head": self.head_to_head,
            "resources": self.resources,
        }


def load_report(path: str | Path, spec: ReportSpec) -> pd.DataFrame:
    """Load one TSV under an explicit schema contract."""
    path = Path(path)
    if not path.is_file():
        raise ReportValidationError(path, ["file does not exist"])
    if path.stat().st_size == 0:
        raise ReportValidationError(path, ["file is empty"])
    try:
        frame = pd.read_csv(path, sep="\t", dtype="string", keep_default_na=False)
    except pd.errors.EmptyDataError as exc:
        raise ReportValidationError(path, ["file has no header or data"]) from exc
    except pd.errors.ParserError as exc:
        raise ReportValidationError(path, [f"TSV parse error: {exc}"]) from exc
    return validate_report(frame, spec, path)


@dataclass(frozen=True)
class BenchmarkSuite:
    report_dir: Path
    datasets: tuple[ReportBundle, ...]

    def by_key(self, key: str) -> ReportBundle:
        for bundle in self.datasets:
            if bundle.dataset_key == key:
                return bundle
        raise KeyError(key)


def load_reports(
    report_dir: str | Path = "reports",
    *,
    dataset_key: str = "benchmark",
    dataset_label: str = "Benchmark",
) -> ReportBundle:
    """Load all dashboard inputs, failing with the precise invalid report."""
    report_dir = Path(report_dir)
    loaded = {
        name: load_report(report_dir / spec.filename, spec)
        for name, spec in REPORT_SPECS.items()
    }
    # Render caller keys as display labels (RelocaTE3-<te>/<genome>) uniformly so
    # every page/filter/plot agrees. The `caller` column is display + filter key
    # here; the on-disk reports keep the fs-safe keys.
    for frame in loaded.values():
        if "caller" in frame.columns:
            frame["caller"] = frame["caller"].map(pretty_caller)
    return ReportBundle(
        report_dir=report_dir,
        dataset_key=dataset_key,
        dataset_label=dataset_label,
        **loaded,
    )


def load_report_suite(report_dir: str | Path = "reports") -> BenchmarkSuite:
    """Load a dataset manifest, falling back to the legacy single-report layout."""
    report_dir = Path(report_dir)
    manifest = report_dir / "datasets.tsv"
    if not manifest.is_file():
        return BenchmarkSuite(report_dir, (load_reports(report_dir),))
    table = pd.read_csv(manifest, sep="\t", dtype="string", keep_default_na=False)
    required = {"dataset", "label", "report_dir"}
    missing = sorted(required - set(table.columns))
    if missing:
        raise ReportValidationError(
            manifest, [f"missing required column(s): {', '.join(missing)}"]
        )
    if table.empty:
        raise ReportValidationError(manifest, ["table has no data rows"])
    if table["dataset"].duplicated().any():
        raise ReportValidationError(manifest, ["dataset keys are not unique"])
    bundles = []
    root = report_dir.resolve()
    for row in table.to_dict("records"):
        path = (report_dir / row["report_dir"]).resolve()
        if path != root and root not in path.parents:
            raise ReportValidationError(
                manifest, [f"report_dir escapes report root: {row['report_dir']}"]
            )
        bundles.append(
            load_reports(
                path,
                dataset_key=row["dataset"],
                dataset_label=row["label"],
            )
        )
    return BenchmarkSuite(report_dir, tuple(bundles))
