#!/usr/bin/env python3
"""Rank benchmark callers from the aggregated report tables (read-only).

Ranks every caller present in reports/correctness.tsv + reports/precision.tsv per
metric (detection recall, status accuracy, precision) and by a composite
(correctly-genotyped recall = recall x status accuracy), across four breakdowns:
overall, by coverage, by biological class, by somatic cellular fraction.
Writes reports/caller_ranking_<date>.md and prints it. Does not re-score.
"""
from __future__ import annotations

import argparse
import csv
import datetime as _dt
from collections import defaultdict
from pathlib import Path


def read_tsv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def _f(x):
    """Parse a float; return None for '', 'NA', None, or unparseable values."""
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.upper() == "NA":
        return None
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def pooled(rows):
    """Event-weighted metrics for a group of correctness rows."""
    truth = sum(_f(r["truth_events"]) or 0 for r in rows)
    det = sum(_f(r["detected_events"]) or 0 for r in rows)
    sc = sum(_f(r["status_correct_events"]) or 0 for r in rows)
    recall = det / truth if truth else 0.0
    status = sc / det if det else 0.0
    return {"recall": recall, "status_accuracy": status,
            "composite": recall * status, "truth": truth, "detected": det}


def rank(caller_values, tie_eps=0.01):
    """caller_values: dict caller->float. Returns [(rank, caller, value, tie)]
    sorted descending; tie=True when within tie_eps of the previous entry."""
    ordered = sorted(caller_values.items(), key=lambda kv: kv[1], reverse=True)
    out, prev = [], None
    for i, (c, v) in enumerate(ordered):
        tie = prev is not None and abs(v - prev) <= tie_eps
        out.append((i + 1, c, v, tie))
        prev = v
    return out


def _group(rows, key):
    g = defaultdict(list)
    for r in rows:
        g[r[key]].append(r)
    return g


def breakdowns(rows):
    """Return {breakdown_name: {stratum: [rows]}} for the four dataset views."""
    somatic = [r for r in rows if "somatic" in r["biological_class"].lower()]
    return {
        "overall": {"__overall__": rows},
        "by_coverage": _group(rows, "coverage"),
        "by_class": _group(rows, "biological_class"),
        "by_somatic_fraction": _group(somatic, "cellular_fraction"),
    }


def precision_by_caller(prec_rows):
    """dict caller -> {'precision': mean overall_precision (None if none), 'fp': sum FP}."""
    acc = defaultdict(lambda: {"p": [], "fp": 0.0})
    for r in prec_rows:
        p = _f(r.get("overall_precision"))
        if p is not None:
            acc[r["caller"]]["p"].append(p)
        acc[r["caller"]]["fp"] += _f(r.get("false_positive_calls")) or 0
    return {c: {"precision": (sum(v["p"]) / len(v["p"]) if v["p"] else None),
                "fp": v["fp"]} for c, v in acc.items()}


def is_stale(reports_dir):
    """True if correctness.tsv is missing, or any
    reports/per_sample/*/*/.complete is newer than correctness.tsv."""
    reports_dir = Path(reports_dir)
    corr = reports_dir / "correctness.tsv"
    if not corr.exists():
        return True
    ct = corr.stat().st_mtime
    return any(m.stat().st_mtime > ct
               for m in (reports_dir / "per_sample").glob("*/*/.complete"))


def _pct(x):
    return "  NA  " if x is None else f"{x:6.1%}"


def _rank_table(rows_by_caller, metric_key, tie_eps=0.01):
    vals = {c: pooled(rs)[metric_key] for c, rs in rows_by_caller.items()}
    lines = ["| rank | caller | value | |", "|---|---|---|---|"]
    for rnk, c, v, tie in rank(vals, tie_eps):
        lines.append(f"| {rnk} | {c} | {_pct(v)} | {'≈tie' if tie else ''} |")
    return "\n".join(lines)


def render_markdown(corr_rows, prec_rows, date, tie_eps=0.01):
    bd = breakdowns(corr_rows)
    prec = precision_by_caller(prec_rows)
    overall_by_caller = _group(corr_rows, "caller")
    # List callers in overall composite-ranked order (best first).
    overall_vals = {c: pooled(rs)["composite"] for c, rs in overall_by_caller.items()}
    callers = [c for _, c, _, _ in rank(overall_vals, tie_eps)]
    out = [f"# Caller ranking — {date}", "",
           f"Callers ranked: {', '.join(callers)}", ""]

    # Headline: overall composite
    out += ["## Headline — Composite (correctly-genotyped recall = recall × status accuracy)", "",
            _rank_table(overall_by_caller, "composite", tie_eps), ""]

    # Overall per-metric
    out += ["## Overall — per metric", ""]
    for label, key in [("Detection recall", "recall"),
                       ("Status accuracy | detected", "status_accuracy")]:
        out += [f"### {label}", "", _rank_table(overall_by_caller, key, tie_eps), ""]
    out += ["### Precision / false positives", "",
            "| caller | precision | total FP |", "|---|---|---|"]
    for c in sorted(prec, key=lambda c: (-(prec[c]["precision"] or 0), prec[c]["fp"])):
        out.append(f"| {c} | {_pct(prec[c]['precision'])} | {prec[c]['fp']:.0f} |")
    out.append("")

    # Breakdowns, composite-ranked per stratum
    for name, title in [("by_coverage", "By coverage"),
                        ("by_class", "By biological class"),
                        ("by_somatic_fraction", "By somatic cellular fraction")]:
        out += [f"## {title} — composite ranking", ""]
        for stratum in sorted(bd[name]):
            by_caller = _group(bd[name][stratum], "caller")
            out += [f"### {stratum}", "", _rank_table(by_caller, "composite", tie_eps), ""]
    return "\n".join(out).rstrip() + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--reports-dir", type=Path, default=Path("reports"))
    ap.add_argument("--date", default=_dt.date.today().strftime("%Y%m%d"))
    ap.add_argument("--tie-eps", type=float, default=0.01)
    args = ap.parse_args(argv)

    if is_stale(args.reports_dir):
        print("WARNING: combined report tables look STALE (per-sample data is newer "
              "than correctness.tsv). Run `bash pipeline/aggregate.sh` first.\n")

    corr = read_tsv(args.reports_dir / "correctness.tsv")
    prec = read_tsv(args.reports_dir / "precision.tsv")
    md = render_markdown(corr, prec, args.date, args.tie_eps)
    out_path = args.reports_dir / f"caller_ranking_{args.date}.md"
    out_path.write_text(md)
    print(md)
    print(f"\n[saved] {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
