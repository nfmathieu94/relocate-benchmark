# relocate-benchmark repo — design

Date/time: 2026-07-15 America/Los_Angeles

## Purpose

A dedicated, git-tracked repository for **running and comparing transposable
element (TE) insertion callers on simulated rice data with known truth**. Its
job is to serve as the gold-standard measure of whether RelocaTE3 outperforms
RelocaTE2 (and, later, other TE callers).

The repo runs the callers and scores/compares their output. It does **not**
generate the simulated data and does **not** store the large simulated reads.

## Separation of concerns (hard boundary)

- `make_simulation_new/` (elsewhere) — **only** the code that generates the
  simulated data (wraps the external `simulate-data` package). No benchmarking
  code lives there.
- `relocate-benchmark/` (this repo) — **only** running callers + comparison.
  It never writes into `make_simulation_new`; it reads the simulated data via
  **config path variables**.
- Simulated reads/truth/genomes live **outside** this repo (in
  `make_simulation_new/results/...`), referenced by config.
- Large caller outputs and alignments live **inside** this repo under `runs/`
  but are **gitignored**. Only small summary tables + scripts/config/docs are
  tracked.

## Location

`/rhome/nmath020/bigdata/github/github_tools/RelocaTE/relocate_benchmark/relocate-benchmark`

## Architecture (caller-adapter plugin model)

```
Simulated data (produced in make_simulation_new; lives OUTSIDE this repo)
   panel_root/ : reads/<sample>/{R1,R2}.fastq, truth_events.tsv, panel_manifest.tsv
        │  (config: [dataset].panel_root)
        ▼
Caller adapters (callers/<name>/ — each runs in its OWN environment)
   relocate2/run.sh  → module load relocate2 / conda RelocaTE2 → relocaTE2.py + CallPing.py
   relocate3/run.sh  → pixi env in the RelocaTE3 repo → run / align-genome /
                        find-insertions / characterize
        │  each emits raw output, then normalize.py → calls.normalized.tsv (common schema)
        ▼
Scoring & comparison (scoring/ — pure Python stdlib, caller-agnostic)
   score_calls.py    per (caller × sample): one-to-one match vs truth →
                     recall / precision / status-accuracy / exact-TSD by class
   combine_reports.py → reports/correctness.tsv, reports/resources.tsv
   compare_callers.py → reports/head_to_head.tsv (N-caller ready)
        │  small summary TSVs tracked in git; runs/, logs/, per_sample/ gitignored
```

## Design decisions (resolved during brainstorming)

1. **Run callers live** (not consume pre-computed output). RelocaTE2 and
   RelocaTE3 are both executed from raw reads inside the repo.
2. **Per-caller adapters + pure-stdlib glue.** Each caller activates its own
   environment; the benchmark's own scoring/comparison code uses Python stdlib
   only (no heavy deps), matching the existing prototypes.
3. **Hybrid plugin structure (approach C).** `callers/<name>/` are drop-in
   adapters against a fixed contract; `datagen` is out of scope; `scoring/`
   and `config/` are shared and caller-agnostic. Adding a caller = drop a new
   `callers/<name>/` folder + register it in config.
4. **Data outside, outputs inside-but-gitignored.** Reads/truth referenced by
   config path; caller run outputs + alignments under `runs/` (gitignored).
5. **Datagen stays in `make_simulation_new`.** This repo documents provenance
   and regeneration in `docs/data_provenance.md` rather than duplicating the
   generation scripts.

## Directory layout

```
relocate-benchmark/                 ← git repo; the benchmark is RUN from here
├── README.md
├── .gitignore
├── config/
│   └── benchmark.toml              # dataset paths → make_simulation_new; caller registry; scoring
├── callers/                        # extension point
│   ├── relocate2/ { env.sh, run.sh, normalize.py }
│   └── relocate3/ { env.sh, run.sh, normalize.py }
├── scoring/ { export_truth.py, score_calls.py, combine_reports.py, compare_callers.py, parse_time_v.py }
├── pipeline/ { run_benchmark_array.sh, submit_benchmark.sh }
├── lib/ config.py                  # stdlib TOML + ${section.key} interpolation
├── truth/                          # normalized truth exported from panel (small, TRACKED)
├── runs/                           # GITIGNORED — per-caller × per-sample outputs + alignments
├── reports/
│   ├── per_sample/                 # GITIGNORED (large per-sample match tables)
│   ├── correctness.tsv             # TRACKED
│   ├── resources.tsv               # TRACKED
│   └── head_to_head.tsv            # TRACKED
├── logs/                           # GITIGNORED
└── docs/
    ├── plans/                      # this design doc + progress notes
    └── data_provenance.md          # where sim data lives + how to regenerate (→ make_simulation_new)
```

## Config schema (`config/benchmark.toml`)

TOML (stdlib `tomllib`) with `${section.key}` interpolation resolved by
`lib/config.py` (adapted from the RelocaTE3 real_rice `_config.py`).

```toml
[dataset]   # all OUTSIDE the repo, in make_simulation_new
panel_root   = "/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/results/somatic_mping_panel_chr1"
reference    = "/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/input/ref_genome/MSU_r7.fa"
te_library   = "/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/input/TE_lib/mping_superfam_header.fa"
repeatmasker = "/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/input/repeatmasker/MSU_r7.fa.out"
te_name      = "mPing"

[run]
work_root = "runs"     # INSIDE repo, gitignored
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
tsd     = "..."       # 3-bp wildcard (known RT3 limitation vs 4-5 bp truth)
```

## Caller-adapter contract

Every `callers/<name>/run.sh` receives the **same fixed inputs** (env vars from
the pipeline): `SAMPLE, R1, R2, REFERENCE, TE_LIBRARY, REPEATMASKER, OUTDIR,
THREADS` plus its own `[callers.<name>]` config block. It must:

1. Activate its own environment via `env.sh`.
2. Produce raw caller output under `$OUTDIR/raw/`.
3. Emit **`$OUTDIR/calls.normalized.tsv`** (via its `normalize.py`) with the
   common schema:

   ```
   chrom  position  te_family  tsd  strand  status  caller  sample
   ```

   - `position` = 1-based reference anchor immediately before the insertion
     (matches the panel truth `position`).
   - `status` ∈ {homozygous, heterozygous, somatic} to align with truth's
     `biological_class`.

That single normalized file is all `scoring/` consumes, so scoring is identical
for every caller and adding a caller requires no scoring changes.

### Grounding for the two adapters

- **RelocaTE2**: `relocaTE2.py --te_fasta ... --reference_ins <RM.out>
  --genome_fasta ... --fq_dir ... --bam <dir> --split --run --size 250
  --step 1234567 --mismatch 2 --aligner blat --cpu N`, then `CallPing.py
  --input <result_dir>` for mPing genotyping. Needs a reads-to-genome BAM
  (align step in `run.sh`). Env: `module load relocate2` or conda `RelocaTE2`.
- **RelocaTE3**: mirrors the existing prototype `run_relocate3_sample.sh`:
  `index-genome` → `run` → `align-genome` → `find-insertions` → build a
  full-reads BAM (minimap2) → `characterize`. Env: pixi in the RelocaTE3 repo.

## Scoring & comparison

- `score_calls.py` (generalized from prototype `score_relocate3.py`): greedy
  one-to-one match within `match_window`, same TE family → per-class recall,
  precision, status accuracy, exact-TSD accuracy. Runs per (caller × sample).
- `export_truth.py`: panel `truth_events.tsv` → normalized `truth/truth.tsv`
  and `truth/truth.bed`.
- `combine_reports.py` → `reports/correctness.tsv` (caller · coverage ·
  replicate · class) and `reports/resources.tsv` (from `/usr/bin/time -v`).
- `compare_callers.py` → `reports/head_to_head.tsv`: side-by-side per class ·
  coverage (recall / precision / status / TSD) + events each caller uniquely
  detected or missed.

## Pipeline (SLURM)

- `pipeline/run_benchmark_array.sh`: array task per (caller × sample) from the
  panel manifest × enabled callers → run adapter → normalize → score. Wraps the
  caller run in `/usr/bin/time -v`. Idempotent via `.complete` sentinels;
  refuses to overwrite non-empty incomplete run dirs.
- `pipeline/submit_benchmark.sh`: orchestrator that exports truth, then submits
  the array sized from `panel_manifest.tsv` × enabled callers.

## Git policy

- **Tracked:** `callers/`, `scoring/`, `pipeline/`, `lib/`, `config/`,
  `truth/` (small normalized truth), README, docs, and the three combined
  summary TSVs (`reports/correctness.tsv`, `reports/resources.tsv`,
  `reports/head_to_head.tsv`).
- **Gitignored:** `runs/`, `logs/`, `reports/per_sample/`, large alignments/
  BAMs — all under the benchmark repo. Simulated FASTQs are never in-repo.

## Scope

- **Build now:** layout, `benchmark.toml` + `lib/config.py`, both caller
  adapters (relocate2, relocate3), `scoring/*`, the SLURM array pipeline,
  README, `docs/data_provenance.md`, wired to the already-generated Chr1 panel
  (`somatic_mping_panel_chr1`, 500 truth events, coverage 5/15/30×, 3 reps).
- **Design-for-later (not built):** additional callers (TEPID/TELR/etc.),
  long-read panels, additional cultivars.

## Known limitation to track

RelocaTE3 currently supports fixed-length wildcard TSD patterns only; scoring
uses `tsd = "..."` (3-bp) while truth includes 4-5 bp TSDs. Exact-TSD accuracy
is reported with this caveat.
