"""Display-only summaries derived from authoritative combined report values."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from .loaders import ReportBundle, pretty_caller


@dataclass(frozen=True)
class FilterSelection:
    callers: tuple[Any, ...] | None = None
    coverages: tuple[Any, ...] | None = None
    classes: tuple[Any, ...] | None = None
    cellular_fractions: tuple[Any, ...] | None = None
    samples: tuple[Any, ...] | None = None
    replicates: tuple[Any, ...] | None = None
    te_groups: tuple[Any, ...] | None = None
    te_classes: tuple[Any, ...] | None = None
    te_orders: tuple[Any, ...] | None = None
    te_superfamilies: tuple[Any, ...] | None = None


FILTER_COLUMNS = {
    "callers": "caller",
    "coverages": "coverage",
    "classes": "biological_class",
    "cellular_fractions": "cellular_fraction",
    "samples": "sample",
    "replicates": "replicate",
    "te_groups": "te_group",
    "te_classes": "te_class",
    "te_orders": "te_order",
    "te_superfamilies": "te_superfamily",
}


def _sorted_values(values: set[Any]) -> tuple[Any, ...]:
    clean = [value for value in values if not pd.isna(value) and value != ""]
    try:
        return tuple(sorted(clean))
    except TypeError:
        return tuple(sorted(clean, key=str))


def available_filters(bundle: ReportBundle) -> dict[str, tuple[Any, ...]]:
    """Return data-driven filter values from every report that has the field."""
    options: dict[str, set[Any]] = {name: set() for name in FILTER_COLUMNS}
    for frame in bundle.frames().values():
        for name, column in FILTER_COLUMNS.items():
            if column in frame.columns:
                options[name].update(frame[column].dropna().tolist())
    return {name: _sorted_values(values) for name, values in options.items()}


def apply_filters(frame: pd.DataFrame, selection: FilterSelection) -> pd.DataFrame:
    """Apply only filters represented by columns in ``frame``."""
    keep = pd.Series(True, index=frame.index)
    for attr, column in FILTER_COLUMNS.items():
        selected = getattr(selection, attr)
        if selected is not None and column in frame.columns:
            keep &= frame[column].isin(selected)
    return frame.loc[keep].copy()


def overall_summary(correctness: pd.DataFrame, precision: pd.DataFrame) -> pd.DataFrame:
    """Return pooled recall and mean per-sample precision for each caller."""
    recall = (
        correctness.groupby("caller", as_index=False, observed=True)[
            ["detected_events", "truth_events"]
        ]
        .sum()
        .assign(
            detection_recall=lambda data: data["detected_events"] / data["truth_events"]
        )
    )
    prec = (
        precision.groupby("caller", as_index=False, observed=True)["overall_precision"]
        .mean()
        .rename(columns={"overall_precision": "mean_sample_precision"})
    )
    return recall.merge(prec, on="caller", how="outer")


def accuracy_summary(correctness: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Aggregate a count-backed correctness metric by caller/coverage/class."""
    definitions = {
        "detection_recall": ("detected_events", "truth_events"),
        "status_accuracy_given_detected": ("status_correct_events", "detected_events"),
        "exact_tsd_accuracy_given_detected": ("tsd_exact_events", "detected_events"),
    }
    if metric not in definitions:
        raise ValueError(f"Unsupported correctness metric: {metric}")
    numerator, denominator = definitions[metric]
    grouped = correctness.groupby(
        ["caller", "coverage", "biological_class"], as_index=False, observed=True
    )[[numerator, denominator]].sum()
    grouped["value"] = grouped[numerator] / grouped[denominator].replace(0, pd.NA)
    grouped["metric"] = metric
    return grouped


def precision_summary(precision: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Aggregate authoritative per-sample precision metrics by caller/coverage."""
    allowed = {"overall_precision", "false_discovery_rate", "false_positive_calls"}
    if metric not in allowed:
        raise ValueError(f"Unsupported precision metric: {metric}")
    grouped = precision.groupby(
        ["caller", "coverage"], as_index=False, observed=True
    )[metric].mean()
    return grouped.rename(columns={metric: "value"}).assign(metric=metric)


def somatic_summary(correctness: pd.DataFrame) -> pd.DataFrame:
    """Return somatic recall by caller, coverage, and cellular fraction."""
    somatic = correctness[
        correctness["biological_class"].str.contains("somatic", case=False, na=False)
    ]
    grouped = somatic.groupby(
        ["caller", "coverage", "cellular_fraction", "expected_vaf"],
        as_index=False,
        observed=True,
    )[["detected_events", "truth_events"]].sum()
    grouped["detection_recall"] = (
        grouped["detected_events"] / grouped["truth_events"].replace(0, pd.NA)
    )
    return grouped


def te_group_summary(correctness: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Aggregate a count-backed metric by caller, coverage, and curated TE group."""
    if "te_group" not in correctness.columns:
        return pd.DataFrame()
    definitions = {
        "detection_recall": ("detected_events", "truth_events"),
        "status_accuracy_given_detected": ("status_correct_events", "detected_events"),
        "exact_tsd_accuracy_given_detected": ("tsd_exact_events", "detected_events"),
    }
    if metric not in definitions:
        raise ValueError(f"Unsupported TE-group metric: {metric}")
    numerator, denominator = definitions[metric]
    dimensions = [
        column
        for column in (
            "caller",
            "coverage",
            "te_group",
            "te_class",
            "te_order",
            "te_superfamily",
        )
        if column in correctness.columns
    ]
    grouped = correctness.groupby(
        dimensions, as_index=False, observed=True, dropna=False
    )[[numerator, denominator]].sum()
    grouped["value"] = grouped[numerator] / grouped[denominator].replace(0, pd.NA)
    return grouped.assign(metric=metric)


def head_to_head_long(head_to_head: pd.DataFrame) -> pd.DataFrame:
    """Convert dynamic N-caller comparison columns into tidy caller rows."""
    suffix = "_detection_recall"
    id_columns = [
        "coverage",
        "replicate",
        "biological_class",
        "cellular_fraction",
    ] + [
        column
        for column in ("te_group", "te_class", "te_order", "te_superfamily")
        if column in head_to_head.columns
    ]
    frames = []
    for recall_column in sorted(
        column for column in head_to_head.columns if column.endswith(suffix)
    ):
        caller_key = recall_column[: -len(suffix)]
        status_column = f"{caller_key}_status_accuracy_given_detected"
        columns = id_columns + [recall_column]
        if status_column in head_to_head.columns:
            columns.append(status_column)
        frame = head_to_head[columns].copy().rename(
            columns={
                recall_column: "detection_recall",
                status_column: "status_accuracy_given_detected",
            }
        )
        frame["caller"] = pretty_caller(caller_key)
        frames.append(frame)
    if not frames:
        return pd.DataFrame(columns=id_columns + ["caller", "detection_recall"])
    return pd.concat(frames, ignore_index=True)


def resource_summary(resources: pd.DataFrame) -> pd.DataFrame:
    """Return mean runtime and memory by caller and coverage."""
    grouped = resources.groupby(
        ["caller", "coverage"], as_index=False, observed=True
    )[["wall_seconds", "max_rss_kb"]].mean()
    grouped["wall_minutes"] = grouped["wall_seconds"] / 60
    grouped["max_rss_gib"] = grouped["max_rss_kb"] / (1024**2)
    return grouped
