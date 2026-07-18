"""Read the four authoritative combined benchmark reports."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .validation import REPORT_SPECS, ReportSpec, ReportValidationError, validate_report


@dataclass(frozen=True)
class ReportBundle:
    report_dir: Path
    correctness: pd.DataFrame
    precision: pd.DataFrame
    head_to_head: pd.DataFrame
    resources: pd.DataFrame

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


def load_reports(report_dir: str | Path = "reports") -> ReportBundle:
    """Load all dashboard inputs, failing with the precise invalid report."""
    report_dir = Path(report_dir)
    loaded = {
        name: load_report(report_dir / spec.filename, spec)
        for name, spec in REPORT_SPECS.items()
    }
    return ReportBundle(report_dir=report_dir, **loaded)

