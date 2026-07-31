"""Schema contracts for the benchmark's combined report tables."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd


class ReportValidationError(ValueError):
    """A report cannot be displayed without changing its meaning."""

    def __init__(self, path: Path, problems: list[str]):
        self.path = Path(path)
        self.problems = tuple(problems)
        detail = "; ".join(problems)
        super().__init__(f"Invalid benchmark report {self.path}: {detail}")


@dataclass(frozen=True)
class ReportSpec:
    filename: str
    required: frozenset[str]
    numeric: frozenset[str]
    integers: frozenset[str]
    unique_key: tuple[str, ...]
    optional_key: tuple[str, ...] = ()
    required_metric_suffix: str | None = None


COMMON_CONDITION = frozenset(
    {"caller", "sample", "coverage", "replicate"}
)

REPORT_SPECS: dict[str, ReportSpec] = {
    "correctness": ReportSpec(
        filename="correctness.tsv",
        required=COMMON_CONDITION
        | frozenset(
            {
                "biological_class",
                "cellular_fraction",
                "expected_vaf",
                "truth_events",
                "detected_events",
                "detection_recall",
                "status_correct_events",
                "status_accuracy_given_detected",
                "tsd_exact_events",
                "false_positive_calls",
                "class_call_share",
            }
        ),
        numeric=frozenset(
            {
                "coverage",
                "replicate",
                "divergence_percent",
                "divergence_replicate",
                "cellular_fraction",
                "expected_vaf",
                "truth_events",
                "detected_events",
                "detection_recall",
                "status_correct_events",
                "status_accuracy_given_detected",
                "tsd_exact_events",
                "false_positive_calls",
                "class_call_share",
            }
        ),
        integers=frozenset(
            {
                "coverage",
                "replicate",
                "divergence_replicate",
                "truth_events",
                "detected_events",
                "status_correct_events",
                "tsd_exact_events",
                "false_positive_calls",
            }
        ),
        unique_key=("caller", "sample", "biological_class", "cellular_fraction"),
        optional_key=(
            "dataset_id",
            "divergence_percent",
            "divergence_replicate",
            "te_group",
            "te_class",
            "te_order",
            "te_superfamily",
        ),
    ),
    "precision": ReportSpec(
        filename="precision.tsv",
        required=COMMON_CONDITION
        | frozenset(
            {
                "total_calls",
                "matched_calls",
                "false_positive_calls",
                "overall_precision",
                "false_discovery_rate",
            }
        ),
        numeric=frozenset(
            {
                "coverage",
                "replicate",
                "divergence_percent",
                "divergence_replicate",
                "total_calls",
                "matched_calls",
                "false_positive_calls",
                "overall_precision",
                "false_discovery_rate",
            }
        ),
        integers=frozenset(
            {
                "coverage",
                "replicate",
                "divergence_replicate",
                "total_calls",
                "matched_calls",
                "false_positive_calls",
            }
        ),
        unique_key=("caller", "sample"),
    ),
    "head_to_head": ReportSpec(
        filename="head_to_head.tsv",
        required=frozenset(
            {"coverage", "replicate", "biological_class", "cellular_fraction"}
        ),
        numeric=frozenset(
            {
                "coverage",
                "replicate",
                "divergence_percent",
                "divergence_replicate",
                "cellular_fraction",
            }
        ),
        integers=frozenset({"coverage", "replicate", "divergence_replicate"}),
        unique_key=("coverage", "replicate", "biological_class", "cellular_fraction"),
        optional_key=(
            "dataset_id",
            "divergence_percent",
            "divergence_replicate",
            "te_group",
            "te_class",
            "te_order",
            "te_superfamily",
        ),
        required_metric_suffix="_detection_recall",
    ),
    "resources": ReportSpec(
        filename="resources.tsv",
        required=COMMON_CONDITION
        | frozenset(
            {"wall_seconds", "max_rss_kb", "user_seconds", "system_seconds", "percent_cpu"}
        ),
        numeric=frozenset(
            {
                "coverage",
                "replicate",
                "divergence_percent",
                "divergence_replicate",
                "wall_seconds",
                "max_rss_kb",
                "user_seconds",
                "system_seconds",
                "percent_cpu",
            }
        ),
        integers=frozenset(
            {"coverage", "replicate", "divergence_replicate", "max_rss_kb"}
        ),
        unique_key=("caller", "sample"),
    ),
}


def _coerce_numeric(frame: pd.DataFrame, spec: ReportSpec, path: Path) -> pd.DataFrame:
    problems: list[str] = []
    converted = frame.copy()
    numeric_columns = set(spec.numeric)
    if spec.required_metric_suffix:
        numeric_columns.update(
            column
            for column in frame.columns
            if column.endswith(spec.required_metric_suffix)
            or column.endswith("_status_accuracy_given_detected")
            or "_minus_" in column
        )

    for column in sorted(numeric_columns & set(frame.columns)):
        raw = frame[column].astype("string").str.strip()
        # GNU time writes this field as e.g. "725%". The unit is fixed by the
        # report schema, so remove only that documented suffix before parsing.
        if column == "percent_cpu":
            raw = raw.str.removesuffix("%")
        missing = raw.isna() | raw.isin(("", "NA", "NaN", "nan", "."))
        values = pd.to_numeric(raw.mask(missing), errors="coerce")
        invalid = ~missing & values.isna()
        if invalid.any():
            examples = sorted(set(raw[invalid].tolist()))[:3]
            problems.append(
                f"column '{column}' contains non-numeric value(s): {examples}"
            )
            continue
        if column in spec.integers:
            non_integer = values.dropna().mod(1).ne(0)
            if non_integer.any():
                problems.append(f"column '{column}' contains non-integer values")
                continue
            converted[column] = values.astype("Int64")
        else:
            converted[column] = values.astype("Float64")

    if problems:
        raise ReportValidationError(path, problems)
    return converted


def validate_report(frame: pd.DataFrame, spec: ReportSpec, path: Path) -> pd.DataFrame:
    """Validate and type a report without changing invalid source values."""
    path = Path(path)
    problems: list[str] = []
    if frame.empty:
        problems.append("table has no data rows")

    missing = sorted(spec.required - set(frame.columns))
    if missing:
        problems.append(f"missing required column(s): {', '.join(missing)}")

    if spec.required_metric_suffix and not any(
        column.endswith(spec.required_metric_suffix) for column in frame.columns
    ):
        problems.append(
            f"no caller metric column ends with '{spec.required_metric_suffix}'"
        )

    if problems:
        raise ReportValidationError(path, problems)

    typed = _coerce_numeric(frame, spec, path)
    unique_key = spec.unique_key + tuple(
        field for field in spec.optional_key if field in typed.columns
    )
    duplicates = typed.duplicated(list(unique_key), keep=False)
    if duplicates.any():
        example = typed.loc[duplicates, list(unique_key)].iloc[0].to_dict()
        raise ReportValidationError(
            path,
            [f"duplicate row for expected key {unique_key}: {example}"],
        )
    return typed
