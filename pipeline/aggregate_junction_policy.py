#!/usr/bin/env python3
"""Aggregate RelocaTE3 vs RelocaTE2 across datasets, coverages and junction policy.

Emits JSON for the release dashboard. Scoring is identical for every caller:
a call matches a truth site when it is on the same chromosome within WINDOW bp.

TSD accuracy is reported only over truth sites that HAVE a TSD. ~10% of
riceTElib truth is TSD-less (`tsd = NONE`); counting those as TSD errors makes a
caller that *detects* them look worse, which is backwards.
"""
from __future__ import annotations

import csv
import json
import os
import sys
from collections import defaultdict

WINDOW = 10
BASE = "/rhome/nmath020/bigdata/github/github_tools/RelocaTE/relocate_benchmark/relocate-benchmark"

CALLERS = {
    "RelocaTE2": "relocate2",
    "RelocaTE3": "relocate3-blat-bwaaln",
    "RelocaTE3-strict": "relocate3-blat-bwaaln-strict",
}
DATASETS = {"mping": "mPing only", "ricetelib": "riceTElib multi-TE"}
COVERAGES = ["cov5x", "cov15x", "cov30x"]
REPS = [1, 2, 3]


def truth(dataset: str, sample: str):
    path = f"{BASE}/truth/{dataset}/per_sample/{sample}.tsv"
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return [
            (r["chrom"], int(r["position"]), (r.get("tsd") or "").upper())
            for r in csv.DictReader(fh, delimiter="\t")
        ]


def calls(dataset: str, caller_dir: str, sample: str):
    path = f"{BASE}/runs/{dataset}/{caller_dir}/{sample}/calls.normalized.tsv"
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return [
            (r["chrom"], int(r["position"]), (r.get("tsd") or "").upper())
            for r in csv.DictReader(fh, delimiter="\t")
        ]


def score(t, c):
    """recall/precision/F1 plus TSD stats split by whether truth has a TSD."""
    matched = []
    for y in c:
        hit = next(
            (x for x in t if x[0] == y[0] and abs(x[1] - y[1]) <= WINDOW), None
        )
        if hit:
            matched.append((hit, y))
    recovered = sum(
        1 for x in t if any(x[0] == y[0] and abs(x[1] - y[1]) <= WINDOW for y in c)
    )
    prec = len(matched) / len(c) if c else 0.0
    rec = recovered / len(t) if t else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0

    real = [(x, y) for x, y in matched if x[2] and x[2] != "NONE"]
    none = [(x, y) for x, y in matched if x[2] == "NONE"]
    return {
        "calls": len(c),
        "recall": rec,
        "precision": prec,
        "f1": f1,
        "tsd_real_n": len(real),
        "tsd_real_exact": sum(1 for x, y in real if y[2] == x[2]),
        "tsdless_n": len(none),
        "tsdless_ok": sum(1 for x, y in none if y[2] in ("UNK", "")),
    }


def main():
    out = {"window": WINDOW, "datasets": {}}
    for ds, ds_label in DATASETS.items():
        out["datasets"][ds] = {"label": ds_label, "coverages": {}}
        for cov in COVERAGES:
            entry = {}
            for caller, cdir in CALLERS.items():
                acc = []
                for rep in REPS:
                    sample = f"{cov}_rep{rep}"
                    t = truth(ds, sample)
                    c = calls(ds, cdir, sample)
                    if t is None or c is None:
                        continue
                    acc.append(score(t, c))
                if not acc:
                    continue
                agg = {"n": len(acc)}
                for k in ("calls", "recall", "precision", "f1"):
                    agg[k] = sum(a[k] for a in acc) / len(acc)
                for k in ("tsd_real_n", "tsd_real_exact", "tsdless_n", "tsdless_ok"):
                    agg[k] = sum(a[k] for a in acc)
                agg["tsd_exact_pct"] = (
                    agg["tsd_real_exact"] / agg["tsd_real_n"] if agg["tsd_real_n"] else None
                )
                agg["tsdless_ok_pct"] = (
                    agg["tsdless_ok"] / agg["tsdless_n"] if agg["tsdless_n"] else None
                )
                entry[caller] = agg
            if entry:
                out["datasets"][ds]["coverages"][cov] = entry
    json.dump(out, sys.stdout, indent=2)
    print()


if __name__ == "__main__":
    main()
