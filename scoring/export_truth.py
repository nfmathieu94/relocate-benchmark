#!/usr/bin/env python3
"""Export simulator panel truth into stable, caller-agnostic benchmark files.

Reads ``<panel_root>/truth_events.tsv`` and ``<panel_root>/panel_manifest.tsv``
and writes normalized truth artifacts into ``outdir``:
    truth.tsv   - verbatim copy of truth_events.tsv (header + rows)
    truth.bed   - one BED line per event, sorted by (chrom, position)
    samples.tsv - verbatim copy of panel_manifest.tsv (header + rows)
    .complete   - sentinel marking a finished export
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

_BED_COLUMNS = (
    "event_id", "te_family", "tsd", "strand",
    "biological_class", "cellular_fraction", "expected_vaf",
)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--panel-root", required=True, type=Path)
    ap.add_argument("--outdir", required=True, type=Path)
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args(argv)

    truth_path = args.panel_root / "truth_events.tsv"
    manifest_path = args.panel_root / "panel_manifest.tsv"
    if not truth_path.is_file():
        raise FileNotFoundError(f"Missing truth events file: {truth_path}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing panel manifest file: {manifest_path}")

    if args.outdir.exists() and any(args.outdir.iterdir()) and not args.force:
        raise FileExistsError(f"Refusing non-empty truth directory: {args.outdir}")
    args.outdir.mkdir(parents=True, exist_ok=True)

    with open(truth_path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        truth_fields = reader.fieldnames
        truth = list(reader)
    with open(args.outdir / "truth.tsv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=truth_fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(truth)

    with open(args.outdir / "truth.bed", "w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        for row in sorted(truth, key=lambda item: (item["chrom"], int(item["position"]))):
            anchor = int(row["position"])
            writer.writerow(
                (row["chrom"], anchor - 1, anchor, *(row[col] for col in _BED_COLUMNS))
            )

    with open(manifest_path) as handle:
        manifest_reader = csv.DictReader(handle, delimiter="\t")
        manifest_fields = manifest_reader.fieldnames
        manifest = list(manifest_reader)
    with open(args.outdir / "samples.tsv", "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=manifest_fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(manifest)

    (args.outdir / ".complete").touch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
