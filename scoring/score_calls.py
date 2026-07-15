"""Score a caller's normalized calls against simulated truth (caller-agnostic)."""
from __future__ import annotations

import argparse
import csv
from collections import defaultdict
from pathlib import Path


def _norm(v: str) -> str:
    return v.lower().replace("_", "").replace("insertion", "") if "somatic" in v.lower() else v.lower().replace("_", "")


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
    for label in sorted({r["biological_class"] for r in truth}):
        grp = [m for m in matches if m["biological_class"] == label]
        det = [m for m in grp if m["matched"] == "1"]
        summary.append({
            "caller": caller, "sample": sample, "biological_class": label,
            "truth_events": len(grp), "detected_events": len(det),
            "detection_recall": (len(det) / len(grp)) if grp else "NA",
            "status_correct_events": sum(m.get("status_correct") == "1" for m in det),
            "status_accuracy_given_detected": (
                sum(m.get("status_correct") == "1" for m in det) / len(det) if det else "NA"),
            "tsd_exact_events": sum(m.get("tsd_exact") == "1" for m in det),
            "false_positive_calls": len(fps),
            "precision": (len(det) / len(calls)) if calls else "NA",
        })
    return summary, matches, fps


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--truth", required=True, type=Path)
    ap.add_argument("--calls", required=True, type=Path)
    ap.add_argument("--sample", required=True)
    ap.add_argument("--caller", required=True)
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--outdir", required=True, type=Path)
    args = ap.parse_args()
    if args.outdir.exists() and any(args.outdir.iterdir()):
        raise FileExistsError(f"Refusing non-empty report dir: {args.outdir}")
    args.outdir.mkdir(parents=True)
    summary, matches, fps = score(args.truth, args.calls, args.sample, args.caller, args.window)
    _write(args.outdir / "matches.tsv", matches)
    _write(args.outdir / "false_positive_calls.tsv", fps)
    _write(args.outdir / "correctness.tsv", summary)
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
