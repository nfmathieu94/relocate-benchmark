#!/usr/bin/env python3
"""Export simulator panel truth into stable, caller-agnostic benchmark files.

Reads ``<panel_root>/panel_manifest.tsv`` and the truth file declared by each
normalized sample. Legacy manifests implicitly declare root ``truth_events.tsv``.
Writes normalized truth artifacts into ``outdir``:
    truth.tsv   - combined unique scenario truth tables
    truth.bed   - one BED line per event, sorted by (chrom, position)
    samples.tsv - normalized manifest with stable sample/replicate/truth fields
    per_sample/ - exact truth table used to score each benchmark sample
    .complete   - sentinel marking a finished export
"""
from __future__ import annotations

import argparse
import csv
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.panel import panel_path, read_panel_manifest

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

    manifest_path = args.panel_root / "panel_manifest.tsv"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing panel manifest file: {manifest_path}")

    if args.outdir.exists() and any(args.outdir.iterdir()) and not args.force:
        raise FileExistsError(f"Refusing non-empty truth directory: {args.outdir}")
    args.outdir.mkdir(parents=True, exist_ok=True)
    # Do not leave an old success marker visible while a forced refresh is
    # rebuilding the exported truth contract.
    (args.outdir / ".complete").unlink(missing_ok=True)

    manifest = read_panel_manifest(args.panel_root)
    truth_by_path: dict[Path, tuple[list[str], list[dict[str, str]]]] = {}
    for row in manifest:
        truth_path = panel_path(args.panel_root, row["truth_tsv"])
        if not truth_path.is_file():
            raise FileNotFoundError(f"Missing truth events file: {truth_path}")
        if truth_path not in truth_by_path:
            with truth_path.open(newline="") as handle:
                reader = csv.DictReader(handle, delimiter="\t")
                fields = reader.fieldnames or []
                records = list(reader)
            if not fields or not records:
                raise ValueError(f"Truth events file is empty: {truth_path}")
            truth_by_path[truth_path] = (fields, records)

    truth_fields: list[str] = []
    seen_fields: set[str] = set()
    truth = []
    for fields, records in truth_by_path.values():
        for field in fields:
            if field not in seen_fields:
                seen_fields.add(field)
                truth_fields.append(field)
        truth.extend(records)
    with open(args.outdir / "truth.tsv", "w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=truth_fields, delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(truth)

    with open(args.outdir / "truth.bed", "w", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        for row in sorted(truth, key=lambda item: (item["chrom"], int(item["position"]))):
            anchor = int(row["position"])
            writer.writerow(
                (row["chrom"], anchor - 1, anchor, *(row[col] for col in _BED_COLUMNS))
            )

    manifest_fields = []
    manifest_seen = set()
    for row in manifest:
        for field in row:
            if field not in manifest_seen:
                manifest_seen.add(field)
                manifest_fields.append(field)
    with open(args.outdir / "samples.tsv", "w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=manifest_fields, delimiter="\t", extrasaction="ignore"
        )
        writer.writeheader()
        writer.writerows(manifest)

    per_sample = args.outdir / "per_sample"
    per_sample.mkdir(exist_ok=True)
    for row in manifest:
        source = panel_path(args.panel_root, row["truth_tsv"])
        destination = per_sample / f"{row['sample']}.tsv"
        temporary = destination.with_name(f".{destination.name}.tmp")
        shutil.copyfile(source, temporary)
        temporary.replace(destination)

    (args.outdir / ".complete").touch()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
