# relocate-benchmark

A benchmark harness that runs transposable-element (TE) insertion callers —
RelocaTE2, RelocaTE3, and future callers — on simulated rice data with known
truth, then scores and compares them. It is the gold-standard measure of
whether RelocaTE3 outperforms RelocaTE2 (and, later, other TE callers): every
caller is run from raw reads through a fixed adapter contract, normalized to a
common schema, and scored identically so the comparison is apples-to-apples.

## Separation of concerns

This repo runs **callers + comparison only**. It does not generate simulated
data.

- Simulated reads, truth, and genomes are generated elsewhere (in the
  `make_simulation_new` project) and referenced by config path
  (`config/benchmark.toml` → `[dataset].panel_root`). See
  [`docs/data_provenance.md`](docs/data_provenance.md) for where the data lives
  and how to regenerate it.
- Large caller outputs and alignments (BAMs, raw caller results) live inside
  this repo under `runs/`, which is **gitignored**. Only scripts, config, docs,
  small normalized truth, and the three combined summary tables under `reports/`
  are tracked.

## Requirements

- **Python ≥ 3.11** for the glue code. The repo standardizes on `python3.12`
  because the default cluster `python3` is 3.9 and lacks `tomllib`. Glue is
  pure stdlib (no external Python deps).
- **RelocaTE2** via `module load relocate2` (bundles bwa / blat / bowtie2 /
  samtools).
- **RelocaTE3** via its pixi environment, located at the repo path in
  `config/benchmark.toml` → `[callers.relocate3].repo`.
- **SLURM** for running the benchmark array.
- **R** (`module load R`) with `ggplot2` for the multipage PDF report
  (`scoring/make_report.R`). Optional — the numeric TSV reports do not need R.

## Setup / environments

Provision the frozen pixi environments once before first use (requires `pixi`
on PATH):

```bash
bash pipeline/setup_envs.sh
```

This installs the two committed pixi manifests into gitignored `.pixi/` dirs.
The benchmark uses three frozen stacks:

- **RelocaTE3** — a pixi env (`callers/relocate3/pixi.toml` + lock) pinned to a
  RelocaTE3 git rev, plus bcftools/minimap2/samtools. Activated by
  `callers/relocate3/env.sh` via `pixi shell-hook`.
- **benchmark** — a pixi env (`env/benchmark/pixi.toml` + lock) with python 3.12
  and the R report stack. Runs scoring/reporting.
- **RelocaTE2** — frozen via **pinned cluster modules**
  (`callers/relocate2/pinned-modules.txt`: `relocate2/2.0.1` + `bwa/0.7.19`), NOT
  pixi: its bioconda package is a dead python-2.7 build that no longer resolves.
  It is cluster-only until a Phase 2 Apptainer image; `setup_envs.sh` does not
  touch it.

Each `env.sh` also has an **UNPINNED fallback** (module/system tools) that warns
when the frozen env is unavailable — an escape hatch, not the intended path.

See [`docs/2026-07-17-env-pinning.md`](docs/2026-07-17-env-pinning.md) for the
add-a-caller recipe and how to bump the RelocaTE3 pin.

## Layout

```
relocate-benchmark/
├── config/     benchmark.toml — dataset paths, caller registry, scoring params
├── callers/    per-caller adapters: relocate2/, relocate3/ {env.sh, run.sh, normalize.py}
├── scoring/    export_truth, score_calls, combine_reports, compare_callers, parse_time_v, make_report.R
├── pipeline/   submit_benchmark.sh, run_benchmark_array.sh, aggregate.sh, update_relocate3.sh, config_env.py
├── lib/        config.py (stdlib TOML + ${section.key} interpolation), calls.py (schema)
├── truth/      normalized truth exported from the panel (small, TRACKED)
├── reports/    combined summary tables + benchmark_report.pdf (TRACKED); per_sample/ + resources/ gitignored
├── runs/       per-caller × per-sample outputs + alignments (GITIGNORED)
└── docs/       plans/ + data_provenance.md
```

## Quickstart

1. Edit `config/benchmark.toml` — set dataset paths and which callers are
   enabled (`[callers.<name>].enabled`).

2. Submit the benchmark:

   ```bash
   bash pipeline/submit_benchmark.sh
   ```

   This exports truth from the panel, submits the SLURM array (one task per
   caller × sample; currently 2 callers × 9 samples = 18 tasks), and submits a
   dependent **aggregation job** that runs automatically once the array finishes
   — combining the reports and rendering the PDF. No manual step needed.

3. Read the results (written by the aggregation job):

   ```
   reports/correctness.tsv        per caller·coverage·replicate·class·cellular_fraction
   reports/precision.tsv          per caller·sample overall precision + false-discovery rate
   reports/head_to_head.tsv       RelocaTE2 vs RelocaTE3 (recall, status accuracy, deltas)
   reports/resources.tsv          wall time + peak RSS
   reports/benchmark_report.pdf   multipage figure report
   ```

   To aggregate manually (e.g. after a `--no-aggregate` run):

   ```bash
   python3.12 scoring/combine_reports.py --report-root reports --samples truth/samples.tsv
   python3.12 scoring/compare_callers.py --correctness reports/correctness.tsv --outdir reports
   module load R && Rscript scoring/make_report.R reports reports/benchmark_report.pdf
   ```

## Running a subset (troubleshooting)

Re-run only specific data groups by filtering on caller, coverage, sample, or
replicate — the task indices stay stable, so only the matching array tasks run:

```bash
bash pipeline/submit_benchmark.sh --caller relocate3            # only RelocaTE3
bash pipeline/submit_benchmark.sh --coverage 30                 # only 30x samples
bash pipeline/submit_benchmark.sh --sample cov30x_rep1          # one sample, both callers
bash pipeline/submit_benchmark.sh --caller relocate3 --coverage 5,15   # combine filters
```

Add `--no-aggregate` to skip the dependent aggregation job.

## Updating RelocaTE3 between runs

RelocaTE3 is installed *editable* in its pixi env, so code edits in its dev repo
are live on the next benchmark run. To sync the environment (after dependency or
entry-point changes) and optionally pull/test:

```bash
bash pipeline/update_relocate3.sh              # pixi install (sync env)
bash pipeline/update_relocate3.sh --pull       # git pull origin first
bash pipeline/update_relocate3.sh --pull --test  # then run RelocaTE3's unit tests
```

It prints the resolved RelocaTE3 git commit so you know which version the next
benchmark will use.

## Outputs

- **`reports/correctness.tsv`** — per caller · coverage · replicate · class ·
  `cellular_fraction`: recall, genotype-status accuracy, exact-TSD accuracy, and
  `class_call_share` (this class's true detections ÷ all of that caller's calls
  — a diagnostic, **not** a precision; see `precision.tsv` for precision).
  Somatic rows break out by cellular fraction (VAF tier).
- **`reports/precision.tsv`** — per caller × sample: `total_calls`,
  `matched_calls`, `overall_precision` (matched ÷ total), and
  `false_discovery_rate`. This is the trustworthy precision metric.
- **`reports/head_to_head.tsv`** — side-by-side per class · cellular_fraction ·
  coverage with per-caller recall + status accuracy and recall deltas. N-caller
  ready.
- **`reports/resources.tsv`** — runtime and memory per caller × sample, parsed
  from `/usr/bin/time -v`.
- **`reports/benchmark_report.pdf`** — multipage figures: recall by class,
  status accuracy, precision + false-positive counts, somatic recall by cellular
  fraction, and compute resources.

## Adding a new caller

No scoring changes are required. To add caller `<name>`:

1. Drop `callers/<name>/{env.sh, run.sh, normalize.py}`. `run.sh` consumes the
   fixed env-var contract (`SAMPLE, R1, R2, REFERENCE, TE_LIBRARY,
   REPEATMASKER, OUTDIR, THREADS` plus its `[callers.<name>]` block), runs the
   caller, and produces `<OUTDIR>/calls.normalized.tsv` via its `normalize.py`
   using `lib/calls.py` (common schema:
   `chrom position te_family tsd strand status caller sample`).
2. Register it under `[callers.<name>]` in `config/benchmark.toml` with
   `enabled = true`.
3. If it needs extra env vars, extend `CALLER_ENV_MAP` in
   `pipeline/config_env.py`.

## Testing

```bash
python3.12 -m unittest discover -s tests -v
```

## Known limitation

RelocaTE3 currently supports fixed-length wildcard TSD patterns only. Scoring
uses `tsd = "..."` (3-bp) while the truth panel contains 4–5 bp TSDs, so
exact-TSD accuracy is reported with that caveat.
