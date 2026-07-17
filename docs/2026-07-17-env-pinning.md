# Environment pinning — provisioning, activation, and add-a-caller recipe

Date/time: 2026-07-17

## Purpose

Freeze every benchmark toolchain so runs are reproducible, and document how to
provision the envs, activate them, run the report, add a new caller, and bump
the RelocaTE3 pin.

## What was pinned

- **RelocaTE3** — pixi env (`callers/relocate3/pixi.toml` + `pixi.lock`).
  RelocaTE3 pinned to git rev `257e2ca791a9d761c2d2e9588e1589fbf953fd3b`, plus
  conda deps (minimap2, samtools, **bcftools**, bedtools, pysam, biopython,
  pybedtools). No `module load bcftools` patch needed.
- **benchmark** — pixi env (`env/benchmark/pixi.toml` + `pixi.lock`): python
  3.12 + R stack (r-base, ggplot2, dplyr, tidyr, patchwork, scales, forcats) for
  scoring and the PDF report.
- **RelocaTE2** — pinned cluster modules (`callers/relocate2/pinned-modules.txt`:
  `relocate2/2.0.1` + `bwa/0.7.19`), NOT pixi. Its bioconda package (relocate2
  2.0.1) is a dead python-2.7 build whose dependency closure (python 2.7,
  samtools 1.3, ncurses 5.9, bedtools 2.26, pysam 0.9, blat 35, ...) no longer
  resolves on current conda-forge/bioconda. The cluster `relocate2/2.0.1` module
  is the one working immutable install, so it is the freeze. A portable freeze
  is deferred to a Phase 2 Apptainer image.

## Current status

Done. Both pixi manifests + locks committed; RT2 pinned-modules manifest +
env.sh committed. `pipeline/setup_envs.sh` provisions the two pixi envs
idempotently. Materialized envs live in gitignored `.pixi/` dirs.

## Commands

Provision the frozen pixi envs (idempotent; RT2 excluded — no pixi env):

```bash
bash pipeline/setup_envs.sh
```

How each env activates (env.sh is *sourced* by the caller's run.sh):

- **RT3** — `callers/relocate3/env.sh` runs
  `eval "$(pixi shell-hook --manifest-path callers/relocate3/pixi.toml)"`, then
  verifies `relocaTE3 minimap2 samtools bcftools` on PATH (exit 127 if missing).
- **RT2** — `callers/relocate2/env.sh` reads `pinned-modules.txt` and
  `module load`s `relocate2/2.0.1` then `bwa/0.7.19` (order matters so modern
  `bwa mem` wins over the bundled bwa 0.6.2), then verifies
  `relocaTE2.py blat bwa samtools`.

Run the report under the benchmark pixi env:

```bash
pixi run --manifest-path env/benchmark/pixi.toml \
  Rscript scoring/make_report.R reports reports/benchmark_report.pdf
```

## Decisions / logic

- Two freeze mechanisms by necessity: pixi for conda/pip-installable tools;
  pinned cluster modules for RT2 (unresolvable on current channels).
- Every `env.sh` follows a uniform pattern: activate frozen env → verify
  required tools on PATH → `exit 127` if missing.
- **Fallback policy**: every `env.sh` has an UNPINNED fallback that emits a
  `WARN` and uses whatever module/system tools it can find. It is an escape
  hatch for when the frozen env is unavailable, never the intended path.

## Add-a-caller recipe

To add caller `<name>`, create the adapter dir `callers/<name>/` with three
scripts plus its frozen env, then register it in config.

1. **Scripts** — `callers/<name>/{env.sh, run.sh, normalize.py}`. `run.sh`
   consumes the fixed env-var contract (`SAMPLE, R1, R2, REFERENCE, TE_LIBRARY,
   REPEATMASKER, OUTDIR, THREADS` plus its `[callers.<name>]` block), runs the
   caller, and produces `<OUTDIR>/calls.normalized.tsv` via `normalize.py` using
   the common `lib/calls.py` schema
   (`chrom position te_family tsd strand status caller sample`).

2. **Frozen env** — pick ONE:
   - **conda/pip-installable tool** → add `callers/<name>/pixi.toml` + commit its
     `pixi.lock`, and add `callers/<name>` to the loop in
     `pipeline/setup_envs.sh` so it is provisioned. `env.sh` activates it with a
     `pixi shell-hook`.
   - **NOT installable on current channels** (like RT2) → add
     `callers/<name>/pinned-modules.txt` listing the exact cluster module
     versions. `env.sh` loads them; do NOT add it to `setup_envs.sh`.

3. **`env.sh` — pixi-activator template** (uniform pattern; adapt tool list):

   ```bash
   #!/usr/bin/bash -l
   set -euo pipefail
   _here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
   _manifest="$_here/pixi.toml"
   if command -v pixi >/dev/null 2>&1 && [[ -f "$_manifest" ]]; then
     eval "$(pixi shell-hook --manifest-path "$_manifest")"
   else
     echo "WARN: frozen pixi env unavailable; falling back to UNPINNED environment" >&2
     # ... best-effort module/system fallback here ...
   fi
   for tool in <required tools>; do
     command -v "$tool" >/dev/null 2>&1 || {
       echo "ERROR: $tool not available after activating <name> env" >&2
       exit 127
     }
   done
   ```

   **Pinned-modules variant** (RT2 style): instead of the `pixi shell-hook`,
   read `pinned-modules.txt` and `module load` each pinned `module/version` in
   order, then run the same verify-tools-on-PATH-or-exit-127 loop. See
   `callers/relocate2/env.sh` for the reference implementation.

4. **Register** — add a `[callers.<name>]` table to `config/benchmark.toml` with
   `enabled = true` and `adapter = "callers/<name>"` plus any caller params.

5. **Extra env vars** — if the caller needs params passed as env vars, add one
   mapping entry to `CALLER_ENV_MAP` in `pipeline/config_env.py`
   (e.g. `"<name>": {"<config_key>": "<ENV_VAR>"}`). No scoring changes needed.

## Bump the RelocaTE3 pin

```bash
# edit rev in callers/relocate3/pixi.toml -> [pypi-dependencies].RelocaTE3.rev
cd callers/relocate3 && pixi install     # resolves + updates pixi.lock
# commit the updated pixi.toml + pixi.lock
```

## Verification (2026-07-17)

End-to-end checks, all green:

- `bash pipeline/setup_envs.sh` provisions both pixi envs idempotently (RT2
  correctly skipped).
- **RT3 env** — `source callers/relocate3/env.sh` resolves `relocaTE3` and
  `bcftools` from `callers/relocate3/.pixi/envs/default/bin/`; `relocaTE3 --help`
  OK. Resolved samtools/bcftools 1.24, minimap2 2.31.
- **RT2 env** — `source callers/relocate2/env.sh` resolves `relocaTE2.py` from
  `relocate2/2.0.1`, `bwa 0.7.19-r1273` (modern bwa wins), `blat`/`samtools 1.9`
  from the module; `relocaTE2.py -h` OK.
- **Benchmark env** — `pixi run --manifest-path env/benchmark/pixi.toml Rscript
  tests/smoke_report.R` → all 8 builder checks OK; full report renders 13 pages.
  Resolved R 4.5.3, python 3.12.13.

Deferred acceptance: a full one-sample-per-caller benchmark run under the frozen
envs (produces `calls.normalized.tsv`) is a ~28-min SLURM job per caller and was
not run inline. Launch it as final acceptance via
`bash pipeline/submit_benchmark.sh --coverage 5` (or a single filtered task)
and confirm both callers still produce matching results.

## Next steps

- Run the deferred one-sample-per-caller SLURM acceptance (above).
- Phase 2: build an Apptainer image so RelocaTE2 (and the whole stack) is
  portable off-cluster, replacing the pinned-modules freeze.
