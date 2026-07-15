# relocate-benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a git-tracked repo that runs RelocaTE2 and RelocaTE3 live on the simulated Chr1 mPing panel and scores/compares each caller against known truth.

**Architecture:** Caller-adapter plugin model. Simulated data is read via config paths (lives outside the repo). Each caller has a self-contained adapter (`env.sh` + `run.sh` + `normalize.py`) that runs in its own environment and emits a common normalized calls TSV. Pure-Python-stdlib scoring code (`scoring/`) is caller-agnostic and compares normalized calls to truth. Large caller outputs live under `runs/` inside the repo but are gitignored.

**Tech Stack:** Bash (`#!/usr/bin/bash -l`, `set -euo pipefail`), Python 3 stdlib only (`tomllib`, `csv`, `argparse`, `unittest` for tests — NO third-party deps), SLURM array jobs. RelocaTE2 via `module load relocate2`; RelocaTE3 via pixi in its repo.

**Repo root:** `/rhome/nmath020/bigdata/github/github_tools/RelocaTE/relocate_benchmark/relocate-benchmark`
All paths below are relative to this root. Run tests with `python3 -m unittest discover -s tests -v`.

---

## Key grounded facts (verified before planning)

- **Both callers emit an identical 8-column characterized TXT:**
  `strain  TE  TSD  chrom:start..end  strand  avg_flankers  spanners  status`
  - RelocaTE2 path: `<caller_outdir>/<sample>/repeat/results/ALL.all_nonref_insert.characTErized.txt`
  - RelocaTE3 path: `<caller_outdir>/<sample>/results/ALL.mPing.all_nonref_insert.characTErized.txt`
  - `status` is the genotype string (e.g. `homozygous`/`heterozygous`/`somatic`); compared to truth `biological_class` after normalization (lowercase, strip `_`, map `somaticinsertion`→`somatic`).
- **Truth** (`panel_root/truth_events.tsv`) columns include: `event_id, chrom, position, te_id, te_family, biological_class, cellular_fraction, expected_vaf, strand, tsd, tsd_length, ...`. `position` = 1-based reference anchor immediately before the insertion. 500 events (100 each: homozygous, heterozygous, somatic@0.1/0.2/0.4).
- **Panel manifest** (`panel_root/panel_manifest.tsv`) columns: `sample, coverage, replicate, r1, r2, control_r1, control_r2` (paths relative to `panel_root`). 9 samples: cov{5,15,30}x_rep{1,2,3}.
- **RelocaTE3 run sequence** (from working prototype `make_simulation_new/relocate3_benchmark/scripts/run_relocate3_sample.sh`): `index-genome` → `run` → `align-genome` → `find-insertions` → build full-reads BAM (minimap2) → `characterize`.
- **RelocaTE2 run** (from `RelocaTE3_jason/validation_data/real_rice/example_relocate2_pipeline/01_relocate_native_cram.sh`): `relocaTE2.py --te_fasta <te> --reference_ins <RM.out> --genome_fasta <ref> --fq_dir <dir with R1/R2> --mate_1_id _R1 --mate_2_id _R2 --outdir <out> --sample <name> --bam <bamdir> --split --run --size 250 --step 1234567 --mismatch 2 --cpu N --aligner blat`. Needs a reads-to-genome BAM directory (`--bam`); step 7 (in `1234567`) is the characterizer that writes the characTErized.txt.

**Reference files to adapt (read them, do not re-invent):**
- `make_simulation_new/relocate3_benchmark/scripts/run_relocate3_sample.sh` (RelocaTE3 run)
- `make_simulation_new/relocate3_benchmark/scripts/score_relocate3.py` (scoring logic)
- `make_simulation_new/relocate3_benchmark/scripts/parse_time_v.py` (resource parsing)
- `RelocaTE3_jason/RelocaTE3/validation/real_rice/normalize_relocate2_char.py` (characterized TXT parser)
- `RelocaTE3_jason/RelocaTE3/validation/real_rice/_config.py` (TOML `${a.b}` interpolation)
- `RelocaTE3_jason/validation_data/real_rice/example_relocate2_pipeline/01_relocate_native_cram.sh` (RelocaTE2 invocation)

---

## Common normalized calls schema

Every adapter's `normalize.py` writes `<caller_outdir>/<sample>/calls.normalized.tsv` with header:

```
chrom	position	te_family	tsd	strand	status	caller	sample
```

- `position` = `start` of the `chrom:start..end` span from the characterized TXT (matching to truth uses `[scoring].match_window`, so exact anchor convention is not critical).
- One row per non-reference insertion call.

---

## Phase 0 — Scaffolding

### Task 0.1: Directory skeleton + .gitignore

**Files:**
- Create: `.gitignore`
- Create (empty, tracked dirs): `callers/`, `scoring/`, `pipeline/`, `lib/`, `config/`, `truth/.gitkeep`, `reports/.gitkeep`, `tests/.gitkeep`, `runs/.gitkeep`, `logs/.gitkeep`

**Step 1:** Create directories:
```bash
cd /rhome/nmath020/bigdata/github/github_tools/RelocaTE/relocate_benchmark/relocate-benchmark
mkdir -p callers/relocate2 callers/relocate3 scoring pipeline lib config truth reports/per_sample tests runs logs
touch truth/.gitkeep reports/.gitkeep tests/.gitkeep runs/.gitkeep logs/.gitkeep
```

**Step 2:** Write `.gitignore`:
```gitignore
# Large caller run outputs and alignments (regenerable)
runs/*
!runs/.gitkeep

# Logs
logs/*
!logs/.gitkeep
*.log

# Large per-sample match tables
reports/per_sample/*
!reports/.gitkeep

# Truth completion sentinel (data itself is small + tracked)
truth/.complete

# Python
__pycache__/
*.pyc
.pytest_cache/
```

**Step 3: Commit**
```bash
git add -A && git commit -m "chore: scaffold relocate-benchmark directory skeleton"
```

---

### Task 0.2: Master config `config/benchmark.toml`

**Files:** Create `config/benchmark.toml`

**Step 1:** Write the config (absolute dataset paths point OUTSIDE the repo; `work_root` is inside, gitignored):
```toml
# relocate-benchmark master config.
# Dataset paths point to simulated data generated in make_simulation_new
# (outside this repo). Caller run outputs go under [run].work_root (gitignored).
# ${section.key} references are expanded by lib/config.py.

[dataset]
panel_root   = "/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/results/somatic_mping_panel_chr1"
reference    = "/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/input/ref_genome/MSU_r7.fa"
te_library   = "/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/input/TE_lib/mping_superfam_header.fa"
repeatmasker = "/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/input/repeatmasker/MSU_r7.fa.out"
te_name      = "mPing"

[run]
work_root = "runs"     # inside repo, gitignored
threads   = 8

[scoring]
match_window = 10

[callers.relocate2]
enabled  = true
adapter  = "callers/relocate2"
aligner  = "blat"
size     = 250
mismatch = 2

[callers.relocate3]
enabled = true
adapter = "callers/relocate3"
repo    = "/rhome/nmath020/bigdata/github/github_tools/RelocaTE/RelocaTE3_jason/RelocaTE3"
tsd     = "..."   # 3-bp wildcard; known RT3 limitation vs 4-5 bp truth
```

**Step 2:** Sanity-check paths exist:
```bash
python3 - <<'PY'
import tomllib
c = tomllib.load(open("config/benchmark.toml","rb"))
import os
for k,v in c["dataset"].items():
    if str(v).startswith("/"):
        print(("OK " if os.path.exists(v) else "MISSING "), k, v)
PY
```
Expected: `OK` for panel_root, reference, te_library, repeatmasker.

**Step 3: Commit**
```bash
git add config/benchmark.toml && git commit -m "feat: add master benchmark config"
```

---

### Task 0.3: `lib/config.py` — TOML loader with `${a.b}` interpolation

**Files:**
- Create: `lib/config.py`, `lib/__init__.py`
- Test: `tests/test_config.py`

**Step 1: Write the failing test** `tests/test_config.py`:
```python
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.config import load_config


class TestConfig(unittest.TestCase):
    def test_interpolation(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write('[dataset]\nroot = "/data"\nref = "${dataset.root}/ref.fa"\n')
            path = fh.name
        cfg = load_config(path)
        self.assertEqual(cfg["dataset"]["ref"], "/data/ref.fa")

    def test_nested_and_plain(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write('[a]\nx = "1"\n[b]\ny = "${a.x}-${a.x}"\nz = "plain"\n')
            path = fh.name
        cfg = load_config(path)
        self.assertEqual(cfg["b"]["y"], "1-1")
        self.assertEqual(cfg["b"]["z"], "plain")


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**
Run: `python3 -m unittest tests.test_config -v`
Expected: FAIL (`ModuleNotFoundError: lib.config`).

**Step 3: Write implementation** `lib/__init__.py` (empty) and `lib/config.py`:
```python
"""Load a TOML config and expand ${section.key} string references."""
from __future__ import annotations

import re
import tomllib
from pathlib import Path

_REF = re.compile(r"\$\{([^}]+)\}")


def _lookup(cfg: dict, dotted: str) -> str:
    node = cfg
    for part in dotted.split("."):
        node = node[part]
    return str(node)


def _expand(value: str, cfg: dict) -> str:
    prev = None
    while prev != value:
        prev = value
        value = _REF.sub(lambda m: _lookup(cfg, m.group(1).strip()), value)
    return value


def _walk(node, cfg):
    if isinstance(node, dict):
        return {k: _walk(v, cfg) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk(v, cfg) for v in node]
    if isinstance(node, str):
        return _expand(node, cfg)
    return node


def load_config(path: str | Path) -> dict:
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    return _walk(raw, raw)
```

**Step 4: Run test to verify it passes**
Run: `python3 -m unittest tests.test_config -v`
Expected: PASS (2 tests).

**Step 5: Commit**
```bash
git add lib/ tests/test_config.py && git commit -m "feat: add config loader with variable interpolation"
```

---

## Phase 1 — Shared calls parsing + scoring core

### Task 1.1: `lib/calls.py` — shared characterized-TXT parser + normalized writer

**Files:**
- Create: `lib/calls.py`
- Test: `tests/test_calls.py`

**Step 1: Write the failing test** `tests/test_calls.py`:
```python
import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.calls import parse_characterized_txt, NORMALIZED_HEADER


class TestCalls(unittest.TestCase):
    def test_parse(self):
        text = (
            "strain\tTE\tTSD\tchromosome.pos\tstrand\tavg_flankers\tspanners\tstatus\n"
            "S1\tmPing\tTTA\tChr1:1000..1002\t+\t5\t2\thomozygous\n"
            "S1\tmPing\tTAA\tChr1:2000..2002\t-\t3\t0\tsomatic\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(text); path = fh.name
        rows = list(parse_characterized_txt(path, caller="relocate3", sample="S1"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["chrom"], "Chr1")
        self.assertEqual(rows[0]["position"], 1000)
        self.assertEqual(rows[0]["te_family"], "mPing")
        self.assertEqual(rows[0]["status"], "homozygous")
        self.assertEqual(rows[0]["caller"], "relocate3")
        self.assertEqual(rows[1]["position"], 2000)

    def test_header_constant(self):
        self.assertEqual(
            NORMALIZED_HEADER,
            ["chrom", "position", "te_family", "tsd", "strand", "status", "caller", "sample"],
        )


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**
Run: `python3 -m unittest tests.test_calls -v` → FAIL (`ModuleNotFoundError`).

**Step 3: Write implementation** `lib/calls.py`:
```python
"""Parse the caller-shared characterized insertion TXT into the common schema.

RelocaTE2 and RelocaTE3 both write an identical 8-column table:
    strain  TE  TSD  chrom:start..end  strand  avg_flankers  spanners  status
"""
from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Iterator

NORMALIZED_HEADER = ["chrom", "position", "te_family", "tsd", "strand", "status", "caller", "sample"]
_COORD = re.compile(r"^([^:]+):(\d+)\.\.(\d+)$")


def parse_characterized_txt(path: str | Path, caller: str, sample: str) -> Iterator[dict]:
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            if not line or line.startswith("#") or line.lower().startswith("strain"):
                continue
            f = line.split("\t")
            if len(f) < 8:
                continue
            _strain, te, tsd, chrom_pos, strand, _flank, _span, status = f[:8]
            m = _COORD.match(chrom_pos)
            if not m:
                continue
            yield {
                "chrom": m.group(1),
                "position": int(m.group(2)),
                "te_family": te,
                "tsd": tsd,
                "strand": strand,
                "status": status,
                "caller": caller,
                "sample": sample,
            }


def write_normalized(rows: list[dict], out_path: str | Path) -> None:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=NORMALIZED_HEADER, delimiter="\t")
        writer.writeheader()
        writer.writerows(rows)
```

**Step 4:** Run: `python3 -m unittest tests.test_calls -v` → PASS.

**Step 5: Commit**
```bash
git add lib/calls.py tests/test_calls.py && git commit -m "feat: add shared characterized-TXT parser and normalized writer"
```

---

### Task 1.2: `scoring/score_calls.py` — score one normalized calls file vs truth

**Files:**
- Create: `scoring/score_calls.py`, `scoring/__init__.py`
- Test: `tests/test_score_calls.py`

Adapt the matching logic from `make_simulation_new/relocate3_benchmark/scripts/score_relocate3.py` (greedy one-to-one within window, same TE family) but consume the **normalized** schema and normalize `status` vs truth `biological_class`.

**Step 1: Write the failing test** `tests/test_score_calls.py`:
```python
import csv, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scoring.score_calls import score


def _write(path, header, rows):
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=header, delimiter="\t")
        w.writeheader(); w.writerows(rows)


class TestScore(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())
        self.truth = self.d / "truth.tsv"
        self.calls = self.d / "calls.tsv"
        _write(self.truth,
               ["event_id","chrom","position","te_family","biological_class","tsd"],
               [{"event_id":"E1","chrom":"Chr1","position":1000,"te_family":"mPing","biological_class":"homozygous","tsd":"TTA"},
                {"event_id":"E2","chrom":"Chr1","position":5000,"te_family":"mPing","biological_class":"somatic_insertion","tsd":"TAA"}])
        _write(self.calls,
               ["chrom","position","te_family","tsd","strand","status","caller","sample"],
               [{"chrom":"Chr1","position":1003,"te_family":"mPing","tsd":"TTA","strand":"+","status":"homozygous","caller":"relocate3","sample":"S1"},
                {"chrom":"Chr1","position":9999,"te_family":"mPing","tsd":"XX","strand":"+","status":"homozygous","caller":"relocate3","sample":"S1"}])

    def test_score(self):
        summary, matches, fps = score(self.truth, self.calls, sample="S1", caller="relocate3", window=10)
        by_class = {r["biological_class"]: r for r in summary}
        self.assertEqual(by_class["homozygous"]["detected_events"], 1)      # E1 matched (dist 3)
        self.assertEqual(by_class["homozygous"]["status_correct_events"], 1)
        self.assertEqual(by_class["homozygous"]["tsd_exact_events"], 1)
        self.assertEqual(by_class["somatic_insertion"]["detected_events"], 0)  # E2 missed
        self.assertEqual(len(fps), 1)   # position 9999 unmatched


if __name__ == "__main__":
    unittest.main()
```

**Step 2:** Run: `python3 -m unittest tests.test_score_calls -v` → FAIL.

**Step 3: Write implementation** `scoring/__init__.py` (empty) and `scoring/score_calls.py`:
```python
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
```

**Step 4:** Run: `python3 -m unittest tests.test_score_calls -v` → PASS.
Note: after writing, also run the full suite: `python3 -m unittest discover -s tests -v`.

**Step 5: Commit**
```bash
git add scoring/score_calls.py scoring/__init__.py tests/test_score_calls.py && git commit -m "feat: add caller-agnostic scoring vs truth"
```

---

### Task 1.3: `scoring/export_truth.py` — normalize panel truth

**Files:**
- Create: `scoring/export_truth.py`
- Test: `tests/test_export_truth.py`

Adapt `make_simulation_new/relocate3_benchmark/scripts/export_truth.py`: read `panel_root/truth_events.tsv` + `panel_root/panel_manifest.tsv`, write `truth/truth.tsv`, `truth/truth.bed`, `truth/samples.tsv`, and a `.complete` sentinel. Refuse to overwrite a non-empty outdir unless `--force`.

**Step 1: Write failing test** `tests/test_export_truth.py`: create a tiny `panel_root` with `truth_events.tsv` (2 rows) + `panel_manifest.tsv` (1 row), call `export_truth.main([...])`, assert `truth/truth.tsv` has 2 data rows and `truth/truth.bed` has 2 lines with `anchor-1, anchor` coordinates.

**Step 2:** Run → FAIL.

**Step 3:** Implement `export_truth.py` (argparse: `--panel-root`, `--outdir`, `--force`). Copy truth rows through; BED row = `(chrom, position-1, position, event_id, te_family, tsd, strand, biological_class, cellular_fraction, expected_vaf)`; copy manifest → `samples.tsv`; `touch .complete`.

**Step 4:** Run → PASS.

**Step 5: Commit**
```bash
git add scoring/export_truth.py tests/test_export_truth.py && git commit -m "feat: add truth export"
```

---

## Phase 2 — RelocaTE3 adapter

### Task 2.1: `callers/relocate3/env.sh`

**Files:** Create `callers/relocate3/env.sh`

Activation helper sourced by `run.sh`. Uses pixi from the RelocaTE3 repo (`[callers.relocate3].repo`). Defines a `RELOCATE3` command wrapper.
```bash
#!/usr/bin/bash -l
# Sourced by run.sh. Requires RT3_REPO (from config [callers.relocate3].repo).
: "${RT3_REPO:?RT3_REPO must be set}"
RELOCATE3=(pixi run --manifest-path "$RT3_REPO/pyproject.toml" relocaTE3)
export RT3_REPO
```
Verify (Step): `bash -c 'RT3_REPO=/rhome/nmath020/bigdata/github/github_tools/RelocaTE/RelocaTE3_jason/RelocaTE3; source callers/relocate3/env.sh; "${RELOCATE3[@]}" --help | head'` → prints RelocaTE3 help.
**Commit:** `git add callers/relocate3/env.sh && git commit -m "feat: add relocate3 env helper"`

### Task 2.2: `callers/relocate3/run.sh`

**Files:** Create `callers/relocate3/run.sh` (adapt prototype `run_relocate3_sample.sh`).

Contract inputs (env vars): `SAMPLE R1 R2 REFERENCE TE_LIBRARY REPEATMASKER OUTDIR THREADS` + `RT3_REPO TSD_PATTERN TE_NAME`. Steps: validate inputs exist; idempotent `.complete` guard; refuse non-empty incomplete `OUTDIR`; `command -v minimap2 samtools`; source `env.sh`; then `index-genome` → `run` (writes into `OUTDIR/raw`) → gather flanking FASTQs → `align-genome` → `find-insertions --tsd "$TSD_PATTERN" --te-name "$TE_NAME" --reference-ins "$REPEATMASKER" --min-mapq 1` → build full-reads BAM via minimap2 → `characterize` → assert `OUTDIR/raw/results/ALL.<TE_NAME>.all_nonref_insert.characTErized.txt` exists → `date > OUTDIR/.run_complete`.

Note: point RelocaTE3 `--outdir` at `$OUTDIR/raw` so normalized output can live at `$OUTDIR/calls.normalized.tsv`.

**Verify (Task 2.4)** rather than unit test (needs real tools + reads).
**Commit:** `git add callers/relocate3/run.sh && git commit -m "feat: add relocate3 run adapter"`

### Task 2.3: `callers/relocate3/normalize.py`

**Files:** Create `callers/relocate3/normalize.py`
```python
#!/usr/bin/env python3
"""Normalize RelocaTE3 characterized output → calls.normalized.tsv."""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from lib.calls import parse_characterized_txt, write_normalized


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--outdir", required=True, type=Path)   # the caller OUTDIR
    ap.add_argument("--sample", required=True)
    ap.add_argument("--te-name", default="mPing")
    args = ap.parse_args()
    txt = args.outdir / "raw" / "results" / f"ALL.{args.te_name}.all_nonref_insert.characTErized.txt"
    if not txt.is_file():
        raise FileNotFoundError(f"RelocaTE3 characterized TXT missing: {txt}")
    rows = list(parse_characterized_txt(txt, caller="relocate3", sample=args.sample))
    write_normalized(rows, args.outdir / "calls.normalized.tsv")
    print(f"relocate3 {args.sample}: {len(rows)} calls", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```
**Commit:** `git add callers/relocate3/normalize.py && git commit -m "feat: add relocate3 normalizer"`

### Task 2.4: Verify RelocaTE3 adapter on the smallest sample

Run interactively (login node OK for 5x? prefer a short `srun`/sbatch). Using `cov5x_rep1`:
```bash
python3 - <<'PY'
from lib.config import load_config
c = load_config("config/benchmark.toml"); print(c["dataset"]["panel_root"])
PY
```
Then drive `run.sh` with env vars for `cov5x_rep1` (R1/R2 from `panel_root/reads/cov5x_rep1/`), `OUTDIR=runs/relocate3/cov5x_rep1`, then `normalize.py`. Confirm `runs/relocate3/cov5x_rep1/calls.normalized.tsv` has the 8-col header and >0 rows. **This is the moment to confirm RelocaTE3's actual `status` vocabulary** — inspect distinct `status` values and confirm `score_calls._norm` maps them onto truth classes; adjust `_norm` if needed (and its test).

**Commit** any fixes: `git commit -am "fix: align relocate3 status normalization with observed output"`

---

## Phase 3 — RelocaTE2 adapter

### Task 3.1: `callers/relocate2/env.sh`

**Files:** Create `callers/relocate2/env.sh`
```bash
#!/usr/bin/bash -l
# Sourced by run.sh. Prefer the cluster module; fall back to conda env.
if module load relocate2 2>/dev/null; then
    :
else
    source activate RelocaTE2 2>/dev/null || conda activate RelocaTE2
fi
module load samtools 2>/dev/null || true
command -v relocaTE2.py >/dev/null || { echo "ERROR: relocaTE2.py unavailable" >&2; exit 127; }
```
**Verify:** `bash -c 'source callers/relocate2/env.sh; relocaTE2.py --help | head'` → prints RelocaTE2 usage.
**Commit:** `git add callers/relocate2/env.sh && git commit -m "feat: add relocate2 env helper"`

### Task 3.2: `callers/relocate2/run.sh`

**Files:** Create `callers/relocate2/run.sh` (adapt `example_relocate2_pipeline/01_relocate_native_cram.sh`).

Contract inputs (env vars): `SAMPLE R1 R2 REFERENCE TE_LIBRARY REPEATMASKER OUTDIR THREADS` + `RT2_ALIGNER RT2_SIZE RT2_MISMATCH`. Steps:
1. Validate inputs; idempotent `.run_complete` guard; refuse non-empty incomplete `OUTDIR`.
2. Source `env.sh`.
3. Build the reads-to-genome BAM RelocaTE2 needs: stage R1/R2 into `$OUTDIR/fq/` as `${SAMPLE}_R1.fastq` / `${SAMPLE}_R2.fastq` (symlink); `mkdir -p $OUTDIR/bam`; align with `bwa mem` (RelocaTE2's default aligner stack) → `samtools sort` → `$OUTDIR/bam/${SAMPLE}.bam` + index. (Reference must be `bwa index`ed; if `$REFERENCE.bwt` missing, run `bwa index` once — the MSU7 ref already has `.bwt` per data listing.)
4. Run:
```bash
relocaTE2.py \
  --te_fasta "$TE_LIBRARY" --reference_ins "$REPEATMASKER" \
  --genome_fasta "$REFERENCE" --fq_dir "$OUTDIR/fq" \
  --mate_1_id _R1 --mate_2_id _R2 \
  --outdir "$OUTDIR/raw" --sample "$SAMPLE" \
  --bam "$OUTDIR/bam" --split --run \
  --size "$RT2_SIZE" --step 1234567 --mismatch "$RT2_MISMATCH" \
  --cpu "$THREADS" --aligner "$RT2_ALIGNER" --verbose 4
```
5. Assert `$OUTDIR/raw/${SAMPLE}/repeat/results/ALL.all_nonref_insert.characTErized.txt` exists; `date > $OUTDIR/.run_complete`.

**Verify in Task 3.4.**
**Commit:** `git add callers/relocate2/run.sh && git commit -m "feat: add relocate2 run adapter"`

### Task 3.3: `callers/relocate2/normalize.py`

**Files:** Create `callers/relocate2/normalize.py` — same as RelocaTE3's but the TXT path is `raw/<sample>/repeat/results/ALL.all_nonref_insert.characTErized.txt` and `caller="relocate2"`.
**Commit:** `git add callers/relocate2/normalize.py && git commit -m "feat: add relocate2 normalizer"`

### Task 3.4: Verify RelocaTE2 adapter on the smallest sample

Submit a short SLURM job (RelocaTE2 is heavier; do NOT run on login node) for `cov5x_rep1`, `OUTDIR=runs/relocate2/cov5x_rep1`. Confirm the characterized TXT is produced and `normalize.py` yields `calls.normalized.tsv` with >0 rows. **Confirm RelocaTE2's `status` vocabulary here** and reconcile with `score_calls._norm` (extend the mapping + its unit test if RelocaTE2 uses different genotype strings). This is the known-unknown flagged in the plan header.

**Commit** any fixes: `git commit -am "fix: reconcile relocate2 status vocabulary in scoring"`

---

## Phase 4 — Reporting

### Task 4.1: `scoring/parse_time_v.py`
Copy/adapt `make_simulation_new/relocate3_benchmark/scripts/parse_time_v.py` (parses `/usr/bin/time -v` → one-row TSV). Add `--caller` column. Add `tests/test_parse_time_v.py` with a captured sample `time -v` block asserting wall-time + max-RSS extraction. TDD steps as in Phase 1. **Commit.**

### Task 4.2: `scoring/combine_reports.py`
Read all `reports/per_sample/<caller>/<sample>/correctness.tsv` + `runs/<caller>/<sample>` resource TSVs → `reports/correctness.tsv` and `reports/resources.tsv` (join coverage/replicate from `truth/samples.tsv`). Add `tests/test_combine_reports.py` (two fake per-sample dirs → combined row count). TDD. **Commit.**

### Task 4.3: `scoring/compare_callers.py`
Read combined `reports/correctness.tsv` (all callers) → `reports/head_to_head.tsv`: one row per (coverage, replicate, biological_class) with columns `relocate2_recall, relocate3_recall, recall_delta, relocate2_precision, relocate3_precision, ...`. Also emit `reports/uniquely_detected.tsv` from per-sample `matches.tsv` (events matched by one caller but missed by the other). N-caller-safe: pivot on the `caller` column rather than hardcoding two names. Add `tests/test_compare_callers.py`. TDD. **Commit.**

---

## Phase 5 — SLURM pipeline

### Task 5.1: `pipeline/run_benchmark_array.sh`
**Files:** Create `pipeline/run_benchmark_array.sh` (SLURM array header: `-p epyc --mem=64gb --cpus-per-task=8 --time=24:00:00 -o logs/benchmark.%A_%a.log`).
Logic: `set -euo pipefail`; `cd "${SLURM_SUBMIT_DIR:-$(pwd)}"`; load `config/benchmark.toml` via a tiny inline `python3` that prints shell `KEY=VALUE` assignments (dataset paths, work_root, threads, enabled callers, per-caller knobs). Build the task list as the cross product of **enabled callers × manifest samples**; index by `SLURM_ARRAY_TASK_ID`. For the selected (caller, sample): set contract env vars (resolve R1/R2 from `panel_root` + manifest); `mkdir -p runs/<caller>/<sample>`; `/usr/bin/time -v -o runs/<caller>/<sample>/time-v.txt bash callers/<caller>/run.sh`; `python3 callers/<caller>/normalize.py ...`; `python3 scoring/score_calls.py --truth truth/truth.tsv --calls runs/<caller>/<sample>/calls.normalized.tsv --caller <caller> --sample <sample> --window <w> --outdir reports/per_sample/<caller>/<sample>`; `python3 scoring/parse_time_v.py ...`.
**Commit.**

### Task 5.2: `pipeline/submit_benchmark.sh`
**Files:** Create `pipeline/submit_benchmark.sh`.
Logic: `set -euo pipefail`; ensure `truth/.complete` (else run `scoring/export_truth.py --panel-root <panel_root> --outdir truth`); compute `N = enabled_callers * manifest_sample_count` via inline python; `mkdir -p logs`; `sbatch --array=0-$((N-1)) pipeline/run_benchmark_array.sh`; print submitted array id + task count. Document that `combine_reports.py` + `compare_callers.py` are run after the array completes (or add a `--dependency=afterok` aggregation job as a stretch).
**Commit.**

---

## Phase 6 — Docs + end-to-end

### Task 6.1: `docs/data_provenance.md`
Record: where the simulated panel lives (`panel_root`), that it was generated by `simulate-data te-benchmark-panel` in `make_simulation_new` (config `somatic_mping_panel_chr1.toml`, seed 916, Chr1, 100 events/class, cov 5/15/30×, 3 reps), the `run_metadata.json` checksums, and the exact commands to regenerate (pointing at `make_simulation_new/pipeline/submit_somatic_panel_chr1.sh`). No datagen scripts are copied here by design. **Commit.**

### Task 6.2: `README.md`
Sections: purpose; the make_simulation_new ↔ relocate-benchmark separation; quickstart (`edit config/benchmark.toml` → `bash pipeline/submit_benchmark.sh` → after array: `combine_reports.py` + `compare_callers.py`); how to add a new caller (drop `callers/<name>/{env.sh,run.sh,normalize.py}` emitting `calls.normalized.tsv`, register in config); git policy; known TSD limitation. Use readme-writer skill. **Commit.**

### Task 6.3: End-to-end smoke on `cov5x_rep1` (both callers)
Run `scoring/export_truth.py`, then the single-sample path for each caller (reuse Task 2.4 / 3.4 outputs if present), then `combine_reports.py` + `compare_callers.py` restricted to that sample. Confirm `reports/head_to_head.tsv` shows RelocaTE2 vs RelocaTE3 recall per class. Fix any integration gaps. **Commit** `docs/2026-07-15-first-benchmark-smoke.md` with results + issues.

---

## Notes for the executor
- Run the full unit suite after each Python task: `python3 -m unittest discover -s tests -v`.
- Never run RelocaTE2/RelocaTE3 on the login node — use `sbatch`/`srun`.
- All scripts: `#!/usr/bin/bash -l` + `set -euo pipefail`; quote expansions; validate inputs before compute; use `.complete`/`.run_complete` sentinels; refuse to overwrite non-empty incomplete output dirs.
- The two known-unknowns (RelocaTE2 and RelocaTE3 `status` vocabularies) are resolved empirically in Tasks 2.4 and 3.4 — do not guess them earlier; keep `score_calls._norm` in sync with what the tools actually emit.
```
