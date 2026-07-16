#!/usr/bin/env python3
"""Produce an N-caller-safe head-to-head comparison from combined correctness.

Reads a combined ``correctness.tsv`` (as written by ``combine_reports.py``) and
pivots it to one row per ``(coverage, replicate, biological_class)`` with, for
each caller present, ``<caller>_detection_recall``, ``<caller>_precision`` and
``<caller>_status_accuracy_given_detected`` columns, plus a recall delta column
``<callerA>_minus_<callerB>_recall`` for every unordered pair of callers.
"""
from __future__ import annotations

import argparse
import csv
import itertools
from collections import OrderedDict
from pathlib import Path

# Per-caller metrics carried into the wide table.
_METRICS = ("detection_recall", "precision", "status_accuracy_given_detected")


def _read_tsv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _int_or_inf(value):
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


def _to_float(value):
    if value is None or value == "" or value == "NA":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def compare(rows):
    callers = sorted({r.get("caller", "") for r in rows if r.get("caller", "")})
    # Group cells by (coverage, replicate, biological_class).
    groups = OrderedDict()
    for r in rows:
        key = (r.get("coverage", ""), r.get("replicate", ""), r.get("biological_class", ""))
        groups.setdefault(key, {})[r.get("caller", "")] = r

    out_rows = []
    for (coverage, replicate, cls), by_caller in groups.items():
        out = OrderedDict()
        out["coverage"] = coverage
        out["replicate"] = replicate
        out["biological_class"] = cls
        for caller in callers:
            cell = by_caller.get(caller)
            for metric in _METRICS:
                out[f"{caller}_{metric}"] = cell.get(metric, "") if cell else ""
        for a, b in itertools.combinations(callers, 2):
            ra = _to_float(by_caller.get(a, {}).get("detection_recall"))
            rb = _to_float(by_caller.get(b, {}).get("detection_recall"))
            out[f"{a}_minus_{b}_recall"] = ("%g" % (ra - rb)) if (ra is not None and rb is not None) else ""
        out_rows.append(out)

    out_rows.sort(key=lambda o: (
        _int_or_inf(o["coverage"]),
        _int_or_inf(o["replicate"]),
        o["biological_class"],
    ))

    # Column order: keys of the first row (stable across all rows).
    fields = list(out_rows[0].keys()) if out_rows else [
        "coverage", "replicate", "biological_class"]
    return fields, out_rows


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--correctness", required=True, type=Path)
    ap.add_argument("--outdir", type=Path, default=Path("reports"))
    args = ap.parse_args(argv)

    rows = _read_tsv(args.correctness)
    fields, out_rows = compare(rows)

    args.outdir.mkdir(parents=True, exist_ok=True)
    out_path = args.outdir / "head_to_head.tsv"
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(out_rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
