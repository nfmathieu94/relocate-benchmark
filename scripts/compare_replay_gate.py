#!/usr/bin/env python3
"""Acceptance gate: dev-tier results must reproduce the checkpoint exactly.

Compares each dev caller's normalized calls (multiset, caller column excluded)
and per-sample precision tables with its checkpoint counterpart. Writes a TSV
and exits 1 on any difference or missing sample, or when no checkpoint calls or
precision files are found (an empty comparison proves nothing). Run from the
benchmark root:

  python3.12 scripts/compare_replay_gate.py --out reports/dev/replay_gate.tsv
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

DEFAULT_PAIRS = {
    "relocate3-replay": "relocate3-blat-bwaaln",
    "relocate2-frozen": "relocate2",
}


def _rows(path: Path) -> Counter:
    with open(path) as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return Counter(
            tuple((k, v) for k, v in sorted(row.items()) if k != "caller")
            for row in reader
        )


def _compare(dev_files: dict, source_files: dict, kind: str) -> list[dict]:
    results = []
    for key in sorted(source_files):
        dataset, dev_caller, sample = key
        row = {"kind": kind, "dataset": dataset, "caller": dev_caller,
               "sample": sample, "dev_only": 0, "source_only": 0}
        if key not in dev_files:
            row["status"] = "missing"
        else:
            dev, source = _rows(dev_files[key]), _rows(source_files[key])
            row["dev_only"] = sum((dev - source).values())
            row["source_only"] = sum((source - dev).values())
            row["status"] = "identical" if dev == source else "different"
        results.append(row)
    return results


def compare_calls(dev_root: Path, source_root: Path, pairs: dict) -> list[dict]:
    dev_files, source_files = {}, {}
    for dev_caller, source_caller in pairs.items():
        for path in Path(source_root).glob(f"*/{source_caller}/*/calls.normalized.tsv"):
            dataset, sample = path.parts[-4], path.parts[-2]
            source_files[(dataset, dev_caller, sample)] = path
            candidate = Path(dev_root) / dataset / dev_caller / sample / "calls.normalized.tsv"
            if candidate.is_file():
                dev_files[(dataset, dev_caller, sample)] = candidate
    return _compare(dev_files, source_files, "calls")


def compare_precision(dev_reports: Path, source_reports: Path, pairs: dict) -> list[dict]:
    dev_files, source_files = {}, {}
    for dev_caller, source_caller in pairs.items():
        pattern = f"datasets/*/per_sample/{source_caller}/*/precision.tsv"
        for path in Path(source_reports).glob(pattern):
            dataset, sample = path.parts[-5], path.parts[-2]
            source_files[(dataset, dev_caller, sample)] = path
            candidate = (Path(dev_reports) / "datasets" / dataset / "per_sample"
                         / dev_caller / sample / "precision.tsv")
            if candidate.is_file():
                dev_files[(dataset, dev_caller, sample)] = candidate
    return _compare(dev_files, source_files, "precision")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dev-runs", default="runs/dev", type=Path)
    ap.add_argument("--source-runs", default="runs/checkpoint-213a0df", type=Path)
    ap.add_argument("--dev-reports", default="reports/dev", type=Path)
    ap.add_argument("--source-reports", default="reports/checkpoint-213a0df", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args(argv)
    rows = compare_calls(args.dev_runs, args.source_runs, DEFAULT_PAIRS)
    rows += compare_precision(args.dev_reports, args.source_reports, DEFAULT_PAIRS)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fields = ["kind", "dataset", "caller", "sample", "status", "dev_only", "source_only"]
    with open(args.out, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
    summary = Counter((r["kind"], r["caller"], r["status"]) for r in rows)
    for (kind, caller, status), n in sorted(summary.items()):
        print(f"{kind}\t{caller}\t{status}\t{n}")
    empty = False
    for kind, root in (("calls", args.source_runs), ("precision", args.source_reports)):
        if not any(r["kind"] == kind for r in rows):
            print(f"ERROR: no checkpoint {kind} files found under {root} for "
                  f"{', '.join(sorted(set(DEFAULT_PAIRS.values())))}; "
                  "nothing was compared (wrong path?)", file=sys.stderr)
            empty = True
    if empty:
        return 1
    return 0 if all(r["status"] == "identical" for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
