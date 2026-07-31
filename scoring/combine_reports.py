#!/usr/bin/env python3
"""Aggregate per-sample benchmark outputs into two combined tables.

Reads per-sample ``correctness.tsv`` files under
``<report-root>/per_sample/<caller>/<sample>/`` and per-sample resource rows
under ``<report-root>/resources/<caller>/<sample>.tsv`` and writes:
    <report-root>/correctness.tsv - all correctness rows, joined with
        coverage/replicate from the panel manifest (samples.tsv)
    <report-root>/precision.tsv   - all per-sample precision rows, joined with
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


SAMPLE_META_FIELDS = (
    "coverage",
    "replicate",
    "dataset_id",
    "divergence_percent",
    "divergence_replicate",
)


def _load_sample_meta(samples_path):
    """Return selected experimental metadata keyed by normalized sample."""
    meta = {}
    if samples_path is None or not Path(samples_path).is_file():
        return meta
    _, rows = _read_tsv(samples_path)
    for row in rows:
        meta[row["sample"]] = {
            field: row.get(field, "") for field in SAMPLE_META_FIELDS
        }
    return meta


def _join_sample_meta(rows, out_fields, meta):
    """Attach manifest conditions and return the expanded output field order."""
    present = [
        field
        for field in SAMPLE_META_FIELDS
        if any(values.get(field, "") != "" for values in meta.values())
    ]
    fields = [field for field in out_fields if field not in present]
    idx = fields.index("sample") + 1 if "sample" in fields else len(fields)
    fields[idx:idx] = present
    for row in rows:
        row.update(meta.get(row.get("sample", ""), {}))
    return fields


def _int_or_inf(value):
    try:
        return (0, int(value))
    except (TypeError, ValueError):
        return (1, str(value))


def _belongs_to_caller_dir(path, rows, caller_parent):
    """Return whether every row's caller matches its containing caller directory.

    This prevents renamed/archive directories left under ``reports/per_sample``
    or ``reports/resources`` from being combined with the active reports. For
    example, rows that still say ``relocate3-bwa-bwa`` must not be loaded from a
    directory renamed to ``relocate3-bwa-bwa.pre-te-family-fix``.
    """
    expected = Path(path).parents[caller_parent].name
    observed = {row.get("caller", "") for row in rows}
    if observed and observed != {expected}:
        print(
            f"WARNING: skipping archived or misplaced report {path}: "
            f"directory caller={expected!r}, row caller(s)={sorted(observed)!r}",
            file=sys.stderr,
        )
        return False
    return True


def _combine_correctness(report_root, samples_path, out_path):
    meta = _load_sample_meta(samples_path)
    paths = sorted(glob.glob(str(report_root / "per_sample" / "*" / "*" / "correctness.tsv")))
    rows = []
    # Union of columns across all files (preserving first-seen order) so newer
    # columns such as cellular_fraction/expected_vaf are carried through even if
    # the first file scanned predates them.
    base_fields = []
    seen = set()
    for path in paths:
        fields, file_rows = _read_tsv(path)
        if not _belongs_to_caller_dir(path, file_rows, caller_parent=1):
            continue
        for f in fields:
            if f not in seen:
                seen.add(f)
                base_fields.append(f)
        rows.extend(file_rows)

    if not rows:
        print(f"WARNING: no correctness rows found under {report_root}/per_sample", file=sys.stderr)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("")
        return

    out_fields = _join_sample_meta(rows, list(base_fields), meta)

    rows.sort(key=lambda r: (
        r.get("caller", ""),
        _int_or_inf(r.get("divergence_percent")),
        _int_or_inf(r.get("coverage")),
        _int_or_inf(r.get("replicate")),
        r.get("biological_class", ""),
        r.get("cellular_fraction", ""),
        r.get("te_group", ""),
        r.get("te_class", ""),
        r.get("te_order", ""),
        r.get("te_superfamily", ""),
    ))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _combine_precision(report_root, samples_path, out_path):
    meta = _load_sample_meta(samples_path)
    paths = sorted(glob.glob(str(report_root / "per_sample" / "*" / "*" / "precision.tsv")))
    rows = []
    base_fields = []
    seen = set()
    for path in paths:
        fields, file_rows = _read_tsv(path)
        if not _belongs_to_caller_dir(path, file_rows, caller_parent=1):
            continue
        for f in fields:
            if f not in seen:
                seen.add(f)
                base_fields.append(f)
        rows.extend(file_rows)

    if not rows:
        print(f"WARNING: no precision rows found under {report_root}/per_sample", file=sys.stderr)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("")
        return

    out_fields = _join_sample_meta(rows, list(base_fields), meta)

    rows.sort(key=lambda r: (
        r.get("caller", ""),
        _int_or_inf(r.get("divergence_percent")),
        _int_or_inf(r.get("coverage")),
        _int_or_inf(r.get("replicate")),
    ))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=out_fields, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _combine_resources(report_root, samples_path, out_path):
    meta = _load_sample_meta(samples_path)
    paths = sorted(glob.glob(str(report_root / "resources" / "*" / "*.tsv")))
    rows = []
    fields = []
    seen = set()
    for path in paths:
        file_fields, file_rows = _read_tsv(path)
        if not _belongs_to_caller_dir(path, file_rows, caller_parent=0):
            continue
        for f in file_fields:
            if f not in seen:
                seen.add(f)
                fields.append(f)
        rows.extend(file_rows)

    fields = _join_sample_meta(rows, fields, meta)
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
    ap.add_argument("--out-precision", type=Path)
    ap.add_argument("--out-resources", type=Path)
    args = ap.parse_args(argv)

    out_corr = args.out_correctness or (args.report_root / "correctness.tsv")
    out_prec = args.out_precision or (args.report_root / "precision.tsv")
    out_res = args.out_resources or (args.report_root / "resources.tsv")

    _combine_correctness(args.report_root, args.samples, out_corr)
    _combine_precision(args.report_root, args.samples, out_prec)
    _combine_resources(args.report_root, args.samples, out_res)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
