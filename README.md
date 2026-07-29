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
  (`config/benchmark.toml` → `[datasets.<key>].panel_root`). See
  [`docs/data_provenance.md`](docs/data_provenance.md) for where the data lives
  and how to regenerate it.
- External panels are read-only. Caller libraries are staged under
  `cache/te_libraries/<dataset>/` before aligner indexes are created.
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
- **RelocaTE2** — a **digest-pinned BioContainer** (portable), NOT pixi: its
  bioconda package is a dead python-2.7 build that no longer resolves.
  `relocaTE2.py`/`blat`/`samtools` come from a `relocate2` image and `bwa 0.7.19`
  from a separate `bwa` image, run via apptainer-exec shims that
  `callers/relocate2/env.sh` puts on PATH (run.sh unchanged). `setup_envs.sh`
  pulls both images (digest-pinned in `callers/relocate2/images.txt`; requires
  apptainer). The **pinned cluster modules**
  (`callers/relocate2/pinned-modules.txt`: `relocate2/2.0.1` + `bwa/0.7.19`) are
  an automatic fallback when the container path is unavailable. See
  [`docs/2026-07-17-rt2-container.md`](docs/2026-07-17-rt2-container.md).

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
├── truth/      normalized truth exported under truth/<dataset>/
├── reports/    independent combined reports under reports/datasets/<dataset>/
├── runs/       dataset × caller × sample outputs + alignments (GITIGNORED)
└── docs/       plans/ + data_provenance.md
```

## Quickstart

1. Edit `config/benchmark.toml` — set dataset paths and which callers are
   enabled (`[callers.<name>].enabled`).

2. Submit one dataset or the full suite:

   ```bash
   bash pipeline/submit_benchmark.sh --dataset mping
   bash pipeline/submit_benchmark.sh --dataset ricetelib
   bash pipeline/submit_benchmark.sh --dataset full
   ```

   This exports truth per dataset, submits the SLURM array (one task per
   dataset × caller × sample), and submits a
   dependent **aggregation job** that runs automatically once the array finishes
   — combining the reports and rendering the PDF. No manual step needed.

3. Read the results (written by the aggregation job):

   ```
   reports/datasets/<dataset>/correctness.tsv
   reports/datasets/<dataset>/precision.tsv
   reports/datasets/<dataset>/head_to_head.tsv
   reports/datasets/<dataset>/resources.tsv
   reports/datasets/<dataset>/benchmark_report.pdf
   ```

   To aggregate manually (e.g. after a `--no-aggregate` run):

   ```bash
   sbatch --export=ALL,DATASET_SELECTION=ricetelib pipeline/aggregate.sh
   ```

## Running a subset (troubleshooting)

Re-run only specific data groups by filtering on caller, coverage, sample, or
replicate — the task indices stay stable, so only the matching array tasks run:

```bash
bash pipeline/submit_benchmark.sh --dataset ricetelib --caller relocate2
bash pipeline/submit_benchmark.sh --dataset full --coverage 30
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

- **`reports/datasets/<dataset>/correctness.tsv`** — per caller · coverage · replicate · class ·
  `cellular_fraction`: recall, genotype-status accuracy, exact-TSD accuracy, and
  `class_call_share` (this class's true detections ÷ all of that caller's calls
  — a diagnostic, **not** a precision; see `precision.tsv` for precision).
  Somatic rows break out by cellular fraction (VAF tier).
- **`reports/datasets/<dataset>/precision.tsv`** — per caller × sample: `total_calls`,
  `matched_calls`, `overall_precision` (matched ÷ total), and
  `false_discovery_rate`. This is the trustworthy precision metric.
- **`reports/datasets/<dataset>/head_to_head.tsv`** — side-by-side per class · cellular_fraction ·
  coverage with per-caller recall + status accuracy and recall deltas. N-caller
  ready.
- **`reports/datasets/<dataset>/resources.tsv`** — runtime and memory per caller × sample, parsed
  from `/usr/bin/time -v`.
- **`reports/datasets/<dataset>/benchmark_report.pdf`** — multipage figures: recall by class,
  status accuracy, precision + false-positive counts, somatic recall by cellular
  fraction, and compute resources.

## Interactive dashboard

After aggregation, launch the read-only Streamlit dashboard from the repository
root:

```bash
bash pipeline/run_dashboard.sh
```

It reads the dataset manifest and provides Overview, Accuracy, Somatic, TE
groups, Resources, and Provenance pages with a dataset selector and data-driven
filters. It never runs
callers or recalculates authoritative benchmark metrics. To open a copied or
historical result set:

```bash
bash pipeline/run_dashboard.sh --report-dir results/history/run_2026_07_17
```

See [`docs/dashboard.md`](docs/dashboard.md) for metric interpretation, HPCC
port forwarding, and troubleshooting.

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
pixi run --manifest-path env/benchmark/pixi.toml \
  python -m unittest discover -s tests -v
```

## Multi-dataset design

See
[`docs/2026-07-28-multi-dataset-benchmark-integration.md`](docs/2026-07-28-multi-dataset-benchmark-integration.md)
for the output-isolation contract, full reference-TE annotation conversion,
TE-taxonomy scoring, TSD provenance, validation, and operational cautions.
