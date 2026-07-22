# compare-callers Skill Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A project skill that ranks every benchmark caller/variant per metric and by a composite, across overall/coverage/class/somatic-fraction breakdowns, presented in chat and saved to `reports/caller_ranking_<date>.md`.

**Architecture:** A deterministic helper `scoring/rank_callers.py` reads the existing aggregated report tables (`reports/correctness.tsv`, `reports/precision.tsv`) and emits a ranked markdown report; a thin `.claude/skills/compare-callers/SKILL.md` wraps it (freshness check → run helper → Claude presents + narrates). Read-only; N-caller-safe (ranks whatever callers appear).

**Tech Stack:** Python 3.12 stdlib (csv, argparse), pytest (via the benchmark pixi env), Claude Agent Skill (SKILL.md).

**Conventions:** tests in `tests/test_*.py`; `scoring` is a package (import `from scoring import rank_callers`). Run tests with `pixi run --manifest-path env/benchmark/pixi.toml python -m pytest`. Metrics are event-weighted (Σdetected/Σtruth). Composite = recall × status_accuracy.

---

### Task 1: Core metric computation (`pooled`)

**Files:**
- Create: `scoring/rank_callers.py`
- Test: `tests/test_rank_callers.py`

**Step 1: Write the failing test**

```python
# tests/test_rank_callers.py
from scoring import rank_callers as rc

def _row(truth, detected, status_correct, **kw):
    d = {"truth_events": truth, "detected_events": detected,
         "status_correct_events": status_correct}
    d.update(kw)
    return d

def test_pooled_event_weighted():
    rows = [_row(100, 80, 40), _row(100, 60, 45)]
    m = rc.pooled(rows)
    assert m["recall"] == (80 + 60) / 200          # 0.70
    assert m["status_accuracy"] == (40 + 45) / 140  # 0.6071...
    assert abs(m["composite"] - 0.70 * (85/140)) < 1e-9

def test_pooled_zero_safe():
    m = rc.pooled([_row(0, 0, 0)])
    assert m["recall"] == 0.0 and m["status_accuracy"] == 0.0 and m["composite"] == 0.0
```

**Step 2: Run test to verify it fails**

Run: `pixi run --manifest-path env/benchmark/pixi.toml python -m pytest tests/test_rank_callers.py::test_pooled_event_weighted -v`
Expected: FAIL (ModuleNotFoundError / AttributeError: no `pooled`).

**Step 3: Write minimal implementation**

```python
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
    try:
        return float(x)
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
```

**Step 4: Run test to verify it passes**

Run: `pixi run --manifest-path env/benchmark/pixi.toml python -m pytest tests/test_rank_callers.py -v`
Expected: PASS (both pooled tests).

**Step 5: Commit**

```bash
git add scoring/rank_callers.py tests/test_rank_callers.py
git commit -m "feat(rank_callers): event-weighted pooled metrics + composite"
```

---

### Task 2: Ranking with tie flags + breakdown grouping

**Files:**
- Modify: `scoring/rank_callers.py`
- Test: `tests/test_rank_callers.py`

**Step 1: Write the failing tests**

```python
def test_rank_orders_desc_and_flags_ties():
    ranked = rc.rank({"a": 0.90, "b": 0.895, "c": 0.70}, tie_eps=0.01)
    assert [r[1] for r in ranked] == ["a", "b", "c"]      # sorted desc
    assert ranked[1][3] is True   # b within 0.01 of a -> tie
    assert ranked[2][3] is False  # c not a tie

def test_breakdowns_group_keys():
    rows = [
        _row(100, 90, 90, caller="x", coverage="5",  biological_class="homozygous",       cellular_fraction="1.0"),
        _row(100, 50, 10, caller="x", coverage="30", biological_class="somatic_insertion", cellular_fraction="0.1"),
        _row(100, 70, 20, caller="x", coverage="30", biological_class="somatic_insertion", cellular_fraction="0.4"),
    ]
    bd = rc.breakdowns(rows)
    assert set(bd["by_coverage"]) == {"5", "30"}
    assert set(bd["by_class"]) == {"homozygous", "somatic_insertion"}
    assert set(bd["by_somatic_fraction"]) == {"0.1", "0.4"}   # somatic only
    assert "__overall__" in bd["overall"]
```

**Step 2: Run to verify fail** — `... -k "rank_orders or breakdowns" -v` → FAIL (no `rank`/`breakdowns`).

**Step 3: Implement**

```python
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
```

**Step 4: Run to verify pass** — `pytest tests/test_rank_callers.py -v` → all PASS.

**Step 5: Commit**

```bash
git add scoring/rank_callers.py tests/test_rank_callers.py
git commit -m "feat(rank_callers): ranking with tie flags + dataset breakdowns"
```

---

### Task 3: Precision, freshness check, markdown render, CLI

**Files:**
- Modify: `scoring/rank_callers.py`
- Test: `tests/test_rank_callers.py`

**Step 1: Write the failing tests**

```python
import os

def _write(p, header, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, delimiter="\t")
        w.writeheader(); w.writerows(rows)

def _fixture_reports(tmp_path):
    corr = tmp_path / "correctness.tsv"
    _write(corr, ["caller","sample","coverage","replicate","biological_class",
                  "cellular_fraction","expected_vaf","truth_events","detected_events",
                  "detection_recall","status_correct_events","status_accuracy_given_detected",
                  "tsd_exact_events","false_positive_calls","class_call_share"],
        [
          {"caller":"relocate2","sample":"s","coverage":"5","replicate":"1","biological_class":"homozygous","cellular_fraction":"1.0","expected_vaf":"1.0","truth_events":"100","detected_events":"90","detection_recall":"0.9","status_correct_events":"80","status_accuracy_given_detected":"0.89","tsd_exact_events":"90","false_positive_calls":"0","class_call_share":"0.5"},
          {"caller":"relocate3-bwa-bwa","sample":"s","coverage":"5","replicate":"1","biological_class":"homozygous","cellular_fraction":"1.0","expected_vaf":"1.0","truth_events":"100","detected_events":"90","detection_recall":"0.9","status_correct_events":"88","status_accuracy_given_detected":"0.98","tsd_exact_events":"90","false_positive_calls":"0","class_call_share":"0.5"},
        ])
    _write(tmp_path / "precision.tsv",
           ["caller","sample","coverage","replicate","total_calls","matched_calls",
            "overall_precision","false_discovery_rate","false_positive_calls"],
        [
          {"caller":"relocate2","sample":"s","coverage":"5","replicate":"1","total_calls":"90","matched_calls":"90","overall_precision":"1.0","false_discovery_rate":"0.0","false_positive_calls":"0"},
          {"caller":"relocate3-bwa-bwa","sample":"s","coverage":"5","replicate":"1","total_calls":"90","matched_calls":"90","overall_precision":"1.0","false_discovery_rate":"0.0","false_positive_calls":"0"},
        ])
    return tmp_path

def test_is_stale_when_per_sample_newer(tmp_path):
    r = _fixture_reports(tmp_path)
    marker = r / "per_sample" / "relocate2" / "s" / ".complete"
    marker.parent.mkdir(parents=True, exist_ok=True); marker.touch()
    os.utime(r / "correctness.tsv", (1, 1))  # make correctness.tsv old
    assert rc.is_stale(r) is True

def test_main_writes_report_ranked_by_composite(tmp_path):
    r = _fixture_reports(tmp_path)
    out = rc.main(["--reports-dir", str(r), "--date", "20260722"])
    md_path = r / "caller_ranking_20260722.md"
    assert md_path.exists()
    text = md_path.read_text()
    assert "Composite" in text and "relocate3-bwa-bwa" in text and "relocate2" in text
    # RT3 has higher status accuracy -> higher composite -> ranked first overall
    assert text.index("relocate3-bwa-bwa") < text.index("relocate2")
    assert out == 0
```

**Step 2: Run to verify fail** — `pytest tests/test_rank_callers.py -k "stale or main_writes" -v` → FAIL.

**Step 3: Implement** (append to `scoring/rank_callers.py`)

```python
def precision_by_caller(prec_rows):
    """dict caller -> {'precision': mean overall_precision, 'fp': sum FP}."""
    acc = defaultdict(lambda: {"p": [], "fp": 0.0})
    for r in prec_rows:
        p = _f(r.get("overall_precision"))
        if p is not None:
            acc[r["caller"]]["p"].append(p)
        acc[r["caller"]]["fp"] += _f(r.get("false_positive_calls")) or 0
    return {c: {"precision": (sum(v["p"]) / len(v["p"]) if v["p"] else None),
                "fp": v["fp"]} for c, v in acc.items()}


def is_stale(reports_dir):
    """True if any reports/per_sample/*/*/.complete is newer than correctness.tsv."""
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
    callers = sorted({r["caller"] for r in corr_rows})
    bd = breakdowns(corr_rows)
    prec = precision_by_caller(prec_rows)
    out = [f"# Caller ranking — {date}", "",
           f"Callers ranked: {', '.join(callers)}", ""]

    # Headline: overall composite
    out += ["## Headline — composite (correctly-genotyped recall = recall × status accuracy)", "",
            _rank_table(bd["overall"], "composite", tie_eps), ""]

    # Overall per-metric
    out += ["## Overall — per metric", ""]
    for label, key in [("Detection recall", "recall"), ("Status accuracy | detected", "status_accuracy")]:
        out += [f"### {label}", "", _rank_table(bd["overall"], key, tie_eps), ""]
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
```

**Step 4: Run tests** — `pytest tests/test_rank_callers.py -v` → all PASS.

**Step 5: Smoke-run on real reports**

Run: `pixi run --manifest-path env/benchmark/pixi.toml python scoring/rank_callers.py --reports-dir reports`
Expected: prints headline + breakdown tables (3 callers), writes `reports/caller_ranking_<today>.md`; RT3 variants rank above relocate2 on composite.

**Step 6: Commit**

```bash
git add scoring/rank_callers.py tests/test_rank_callers.py
git commit -m "feat(rank_callers): precision, staleness check, markdown report + CLI"
```

---

### Task 4: The `compare-callers` skill

**Files:**
- Create: `.claude/skills/compare-callers/SKILL.md`

**Step 1: Author SKILL.md** — REQUIRED SUB-SKILL: @superpowers:writing-skills (correct frontmatter `name`/`description`, imperative body).

Body must instruct Claude to:
1. From the repo root, run `pixi run --manifest-path env/benchmark/pixi.toml python scoring/rank_callers.py` (fall back to `python3.12 scoring/rank_callers.py` if pixi/env unavailable).
2. If the helper prints the STALE warning, surface it prominently and offer to run `bash pipeline/aggregate.sh` before continuing.
3. Present the ranked report in chat (headline composite first, then per-metric overall, then the three breakdowns), with a 2-4 sentence narrative: who wins overall, notable trade-offs (e.g. recall ties vs status-accuracy gaps), and behavior at low coverage / low somatic fraction.
4. State which callers are present and explicitly note any expected-but-absent variant (e.g. bowtie2 if disabled).
5. Point the user to the saved `reports/caller_ranking_<date>.md`.

`description` must include trigger phrases: "rank callers", "compare callers", "benchmark status report", "which caller is best".

**Step 2: Smoke test the skill**

Invoke the skill (or `Skill` tool `compare-callers`). Expected: helper runs, chat shows ranked tables + narrative, `reports/caller_ranking_<date>.md` exists.

**Step 3: Commit**

```bash
git add .claude/skills/compare-callers/SKILL.md
git commit -m "feat(skill): compare-callers benchmark ranking skill"
```

---

## Final verification
- `pixi run --manifest-path env/benchmark/pixi.toml python -m pytest tests/test_rank_callers.py -v` → all PASS.
- Skill invocation produces chat report + saved markdown over the live 3-caller `reports/`.
- Re-run is idempotent (overwrites same-date file); no re-scoring occurs.
