# Environment pinning (Phase 1) — design

Date/time: 2026-07-17 America/Los_Angeles

## Purpose

Freeze the three software stacks the benchmark depends on so a rerun reproduces,
and do it with a uniform, extensible mechanism that new TE callers can adopt by
convention. Phase 1 = pin only; containerization (Apptainer) and a workflow
engine (Nextflow) are deliberately deferred to later phases.

## Context / current state (verified 2026-07-17)

- Caller-adapter model already exists: `callers/<name>/{env.sh,run.sh,normalize.py}`
  emitting a shared `calls.normalized.tsv`. Caller registry is in
  `config/benchmark.toml` (`[callers.<name>]`) + `pipeline/config_env.py`. Adding
  a caller is already easy; the gap is environment *freezing*, which is uneven:
  - **RelocaTE2:** unpinned — rides `module load relocate2` (cluster module
    `relocate2/2.0.1`, itself a conda-built env) + PATH surgery + `module load
    bwa/0.7.19`. Nothing frozen.
  - **RelocaTE3:** mostly frozen — the RT3 repo has `pixi.toml` + `pixi.lock`,
    but `bcftools` is patched in via `module load bcftools` (unpinned), and RT3
    is installed editable from a live dev working tree.
  - **Benchmark:** unpinned — scoring/orchestration python is stdlib-only (needs
    only python >= 3.11 for `tomllib`); the report needs R + ggplot2/dplyr/tidyr/
    patchwork/scales (+forcats), currently via `module load R`.
- `pixi` 0.70.2 is on PATH. Cluster modules available: `apptainer/1.4.5`,
  `singularity-ce/4.3.2`, `nextflow` (for later phases).
- RT3 upstream: `git@github.com:stajichlab/RelocaTE3.git`, current working ref =
  commit `257e2ca791a9d761c2d2e9588e1589fbf953fd3b` (branch
  `fix-cmd-run-trim-thresholds`, tag `v0.1.0`).

## Decisions (approved 2026-07-17)

1. **Mechanism: pixi everywhere.** Channels `conda-forge` + `bioconda`. Each env
   gets a committed `pixi.lock`. Chosen for uniformity with RT3, cross-platform
   locks (conda + PyPI + git in one), and a clean path to containers later.
2. **Per-caller manifests.** Each caller ships its own frozen env under
   `callers/<name>/`. New callers follow the same convention.
3. **RT3 frozen by git ref, benchmark-owned.** The benchmark repo carries
   `callers/relocate3/pixi.toml` that installs RT3 from a pinned git commit +
   `bcftools` + runtime deps. No edits to the upstream RT3 repo. Bump the ref on
   purpose.

## Layout (manifests + locks tracked; `.pixi/` materialized dirs gitignored)

```
callers/relocate2/pixi.toml + pixi.lock   # relocate2=2.0.1, bwa=0.7.19 pin, (blat/samtools/bedtools pulled by relocate2)
callers/relocate3/pixi.toml + pixi.lock   # bcftools + minimap2/samtools/bedtools/pysam/biopython/pybedtools; RelocaTE3 from git rev 257e2ca
env/benchmark/pixi.toml   + pixi.lock     # python=3.12 + r-base + r-ggplot2/r-dplyr/r-tidyr/r-patchwork/r-scales/r-forcats
```

## `env.sh` contract (uniform thin activator)

Every caller's `env.sh` has the same shape:

```bash
# Prefer the caller's frozen pixi env; fall back to the cluster module (unpinned, warns).
if pixi available && manifest exists:
    eval "$(pixi shell-hook --manifest-path callers/<name>/pixi.toml)"
else:
    echo "WARN: pixi env unavailable; using unpinned module fallback" >&2
    module load <fallback>
# verify required tools on PATH -> exit 127 if missing (keep existing checks)
```

- **RT3:** keep the pixi shell-hook; move `bcftools` into the manifest → drop the
  `module load bcftools` line.
- **RT2:** replace `module load relocate2` + PATH-surgery + `module load
  bwa/0.7.19` with the pixi activation; keep the tool-presence checks.

## Run integration

- Report/scoring run under the benchmark env: `pipeline/aggregate.sh` and
  `pipeline/submit_benchmark.sh` invoke
  `pixi run --manifest-path env/benchmark/pixi.toml Rscript …` / `… python3 …`,
  each with the existing `module load R` / `python3.12` as a documented fallback.
- The caller-adapter contract (`env.sh` -> `run.sh` -> `normalize.py` ->
  `calls.normalized.tsv`) is unchanged.

## One-time provisioning

`pipeline/setup_envs.sh` runs `pixi install` for each caller manifest + the
benchmark env, so a fresh clone provisions all frozen stacks in one command.
Documented in the README.

## Extensibility convention (deliverable for future callers)

Documented "add a caller" recipe: drop
`callers/<name>/{pixi.toml,env.sh,run.sh,normalize.py}`, add `[callers.<name>]`
to `benchmark.toml`, and (if it needs extra env vars) one mapping line in
`config_env.py`. `env.sh` follows the shared activator template. A new caller is
a self-contained directory with its own frozen env; nothing else changes.

## Reproducibility / fallback policy

- Every `pixi.lock` is committed. The module fallback is an unpinned escape
  hatch that emits a warning, so a fresh checkout can still run before
  `pixi install`.
- Verify by re-running `tests/smoke_report.R` under the benchmark env and one
  sample per caller under its pixi env, confirming tools resolve and a run
  completes.

## Unknowns to resolve during implementation

- `relocate2` bioconda resolve — expected `2.0.1`; `pixi install` confirms. If it
  will not resolve, RT2 falls back to a documented pinned-module set (flag it).
- RT3 git fetch auth: `stajichlab/RelocaTE3` via pixi PyPI git dependency
  (`RelocaTE3 = { git = "https://github.com/stajichlab/RelocaTE3.git", rev =
  "257e2ca..." }`). If the repo is private, `pixi install` needs git auth
  (token/ssh) — confirm public vs private.

## Boundary

All changes in the `relocate-benchmark` repo; strictly the run+compare side. No
edits to the RT3 upstream repo or to `make_simulation_new`.

## Next steps

Turn this into a task-by-task implementation plan (writing-plans), then execute.
