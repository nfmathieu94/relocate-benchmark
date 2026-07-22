"""Score a caller's normalized calls against simulated truth (caller-agnostic)."""
from __future__ import annotations

import argparse
import csv
import shutil
from collections import defaultdict
from pathlib import Path


def _norm(v: str) -> str:
    # Strip any RepeatMasker class/family suffix so caller TE names match the
    # truth family name (e.g. "mPing#DNA/Harbinger" -> "mPing"). Then lowercase,
    # drop underscores, and collapse the "somatic_insertion"/"somatic" vocabulary
    # so truth classes and caller genotype strings compare on equal footing.
    lo = v.split("#", 1)[0].lower().replace("_", "")
    return lo.replace("insertion", "") if "somatic" in lo else lo


def _load(path):
    with open(path) as fh:
        return list(csv.DictReader(fh, delimiter="\t"))


def score(truth_path, calls_path, sample: str, caller: str, window: int):
    truth = _load(truth_path)
    calls = _load(calls_path)
    by_chrom = defaultdict(list)
    for i, c in enumerate(calls):
        by_chrom[c["chrom"]].append((i, c))
    used: set[int] = set()
    matches = []
    for ev in sorted(truth, key=lambda r: (r["chrom"], int(r["position"]))):
        cands = [
            (abs(int(ev["position"]) - int(c["position"])), i, c)
            for i, c in by_chrom[ev["chrom"]]
            if i not in used
            and abs(int(ev["position"]) - int(c["position"])) <= window
            and _norm(ev["te_family"]) == _norm(c["te_family"])
        ]
        if not cands:
            matches.append({"event_id": ev["event_id"], "matched": "0", **ev})
            continue
        dist, i, c = min(cands)
        used.add(i)
        matches.append({
            "event_id": ev["event_id"], "matched": "1", "call_position": c["position"],
            "distance_bp": dist, "call_status": c["status"], "call_tsd": c["tsd"],
            "status_correct": str(int(_norm(ev["biological_class"]) == _norm(c["status"]))),
            "tsd_exact": str(int(ev["tsd"] == c["tsd"])), **ev,
        })
    fps = [c for i, c in enumerate(calls) if i not in used]
    summary = []
    # Group per-class metrics by the (biological_class, cellular_fraction) pair so
    # somatic events break out by cellular fraction while hom/het (cellular_fraction
    # 1.0, or "" for truth files lacking the column) each yield a single row.
    groups: dict = {}
    for m in matches:
        key = (m["biological_class"], m.get("cellular_fraction", ""))
        groups.setdefault(key, []).append(m)
    for (label, cell_frac) in sorted(groups):
        grp = groups[(label, cell_frac)]
        det = [m for m in grp if m["matched"] == "1"]
        summary.append({
            "caller": caller, "sample": sample, "biological_class": label,
            "cellular_fraction": cell_frac,
            "expected_vaf": grp[0].get("expected_vaf", ""),
            "truth_events": len(grp), "detected_events": len(det),
            "detection_recall": (len(det) / len(grp)) if grp else "NA",
            "status_correct_events": sum(m.get("status_correct") == "1" for m in det),
            "status_accuracy_given_detected": (
                sum(m.get("status_correct") == "1" for m in det) / len(det) if det else "NA"),
            "tsd_exact_events": sum(m.get("tsd_exact") == "1" for m in det),
            # AGGREGATION CONTRACT: false_positive_calls and class_call_share use
            # GLOBAL (all-calls) denominators. len(fps) is the total unmatched calls
            # and len(calls) is the total call count -- both are repeated verbatim on
            # every per-group row. Downstream consumers must NOT sum
            # false_positive_calls across group rows (that would multiply the
            # single global count by the number of groups). class_call_share is the
            # share of ALL calls that are true detections of this group.
            "false_positive_calls": len(fps),
            "class_call_share": (len(det) / len(calls)) if calls else "NA",
        })
    # Per-SAMPLE overall precision / false-discovery rate over ALL calls.
    matched_calls = len(used)
    total_calls = len(calls)
    overall_precision = (matched_calls / total_calls) if total_calls else "NA"
    precision_row = {
        "caller": caller, "sample": sample,
        "total_calls": total_calls, "matched_calls": matched_calls,
        "false_positive_calls": len(fps),
        "overall_precision": overall_precision,
        "false_discovery_rate": (1 - overall_precision) if total_calls else "NA",
    }
    return summary, matches, fps, precision_row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--truth", required=True, type=Path)
    ap.add_argument("--calls", required=True, type=Path)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--caller", required=True)
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--outdir", required=True, type=Path)
    args = ap.parse_args(argv)
    if args.outdir.exists() and any(args.outdir.iterdir()):
        if (args.outdir / ".complete").exists():
            # Idempotent re-score: this dir holds THIS step's own completed
            # output (.complete marker written below), so replace it cleanly.
            # A non-empty dir WITHOUT the marker is foreign/partial -> still refuse.
            shutil.rmtree(args.outdir)
        else:
            raise FileExistsError(f"Refusing non-empty report dir: {args.outdir}")
    args.outdir.mkdir(parents=True, exist_ok=True)
    summary, matches, fps, precision_row = score(
        args.truth, args.calls, args.sample, args.caller, args.window)
    _write(args.outdir / "matches.tsv", matches)
    _write(args.outdir / "false_positive_calls.tsv", fps)
    _write(args.outdir / "correctness.tsv", summary)
    _write(args.outdir / "precision.tsv", [precision_row])
    (args.outdir / ".complete").touch()
    return 0


def _write(path, rows):
    if not rows:
        Path(path).write_text("")
        return
    fields = list(rows[0].keys()) if path.name != "matches.tsv" else sorted({k for r in rows for k in r})
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, delimiter="\t", extrasaction="ignore")
        w.writeheader(); w.writerows(rows)


if __name__ == "__main__":
    raise SystemExit(main())
