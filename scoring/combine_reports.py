#!/usr/bin/env python3
"""Aggregate per-sample benchmark outputs into two combined tables.

Reads per-sample ``correctness.tsv`` files under
``<report-root>/per_sample/<caller>/<sample>/`` and per-sample resource rows
under ``<report-root>/resources/<caller>/<sample>.tsv`` and writes:
    <report-root>/correctness.tsv - all correctness rows, joined with
        coverage/replicate from the panel manifest (samples.tsv)
    <report-root>/resources.tsv   - all resource rows (union of columns)
"""
from __future__ import annotations

import argparse
import csv
import glob
import sys
from pathlib import Path


def _read_tsv(path):
    with open(path) as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        return reader.fieldnames or [], list(reader)


def _load_sample_meta(samples_path):
    """Return {sample: (coverage, replicate)} from a panel manifest."""
    meta = {}
    if samples_path is None or not Path(samples_path).is_file():
        return meta
    _, rows = _read_tsv(samples_path)
    for row in rows:
        meta[row["sample"]] = (row.get("coverage", ""), row.get("replicate", ""))
    return meta


def _int_or_inf(value):
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


def _combine_correctness(report_root, samples_path, out_path):
    meta = _load_sample_meta(samples_path)
    paths = sorted(glob.glob(str(report_root / "per_sample" / "*" / "*" / "correctness.tsv")))
    rows = []
    base_fields = []
    for path in paths:
        fields, file_rows = _read_tsv(path)
        if fields and not base_fields:
            base_fields = fields
        rows.extend(file_rows)

    if not rows:
        print(f"WARNING: no correctness rows found under {report_root}/per_sample", file=sys.stderr)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("")
        return

    # Insert coverage/replicate right after the 'sample' column.
    out_fields = list(base_fields)
    if "sample" in out_fields:
        idx = out_fields.index("sample") + 1
    else:
        idx = len(out_fields)
    for extra in ("replicate", "coverage"):
        if extra not in out_fields:
            out_fields.insert(idx, extra)

    for row in rows:
        cov, rep = meta.get(row.get("sample", ""), ("", ""))
        row["coverage"] = cov
        row["replicate"] = rep

    rows.sort(key=lambda r: (
        r.get("caller", ""),
        _int_or_inf(r.get("coverage")),
        _int_or_inf(r.get("replicate")),
        r.get("biological_class", ""),
    ))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _combine_resources(report_root, out_path):
    paths = sorted(glob.glob(str(report_root / "resources" / "*" / "*.tsv")))
    rows = []
    fields = []
    seen = set()
    for path in paths:
        file_fields, file_rows = _read_tsv(path)
        for f in file_fields:
            if f not in seen:
                seen.add(f)
                fields.append(f)
        rows.extend(file_rows)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        print(f"WARNING: no resource rows found under {report_root}/resources", file=sys.stderr)
        # Write just the header if we discovered columns, else an empty file.
        if fields:
            with open(out_path, "w", newline="") as fh:
                fh.write("\t".join(fields) + "\n")
        else:
            out_path.write_text("")
        return

    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--report-root", required=True, type=Path)
    ap.add_argument("--samples", required=True, type=Path)
    ap.add_argument("--out-correctness", type=Path)
    ap.add_argument("--out-resources", type=Path)
    args = ap.parse_args(argv)

    out_corr = args.out_correctness or (args.report_root / "correctness.tsv")
    out_res = args.out_resources or (args.report_root / "resources.tsv")

    _combine_correctness(args.report_root, args.samples, out_corr)
    _combine_resources(args.report_root, out_res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
