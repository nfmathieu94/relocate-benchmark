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

## Layout

```
relocate-benchmark/
├── config/     benchmark.toml — dataset paths, caller registry, scoring params
├── callers/    per-caller adapters: relocate2/, relocate3/ {env.sh, run.sh, normalize.py}
├── scoring/    export_truth, score_calls, combine_reports, compare_callers, parse_time_v
├── pipeline/   submit_benchmark.sh, run_benchmark_array.sh, config_env.py
├── lib/        config.py (stdlib TOML + ${section.key} interpolation), calls.py (schema)
├── truth/      normalized truth exported from the panel (small, TRACKED)
├── reports/    combined summary tables (TRACKED); per_sample/ + resources/ gitignored
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

   This exports truth from the panel and submits the SLURM array (one task per
   caller × sample; currently 2 callers × 9 samples = 18 tasks).

3. After **all** array tasks finish, aggregate:

   ```bash
   python3.12 scoring/combine_reports.py --report-root reports --samples truth/samples.tsv
   python3.12 scoring/compare_callers.py --correctness reports/correctness.tsv --outdir reports
   ```

4. Read the results:

   ```
   reports/correctness.tsv
   reports/resources.tsv
   reports/head_to_head.tsv
   ```

## Outputs

- **`reports/correctness.tsv`** — per caller · coverage · replicate · class:
  recall, precision, status accuracy, and exact-TSD accuracy.
- **`reports/resources.tsv`** — runtime and memory per caller × sample, parsed
  from `/usr/bin/time -v`.
- **`reports/head_to_head.tsv`** — side-by-side per class · coverage with
  per-caller metrics and recall deltas (which caller wins, and events each
  caller uniquely detected or missed). N-caller ready.

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
