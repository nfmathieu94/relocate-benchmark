# Environment Pinning (Phase 1) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Freeze the three software stacks (RelocaTE2, RelocaTE3, benchmark report/scoring) as committed pixi environments with lockfiles, behind a uniform `env.sh` activator, so reruns reproduce and future callers slot in by convention.

**Architecture:** pixi everywhere (channels conda-forge + bioconda). Each caller carries `callers/<name>/pixi.toml` + `pixi.lock`; the benchmark carries `env/benchmark/pixi.toml` + `pixi.lock`. `env.sh` becomes a thin activator (`pixi shell-hook`) with a documented unpinned module fallback. RT3 is benchmark-owned and pinned to a git commit. The caller-adapter contract (`env.sh` -> `run.sh` -> `normalize.py` -> `calls.normalized.tsv`) is unchanged.

**Tech Stack:** pixi 0.70.2, conda-forge + bioconda, SLURM cluster (Rocky 8). Design: `docs/plans/2026-07-17-env-pinning-design.md`.

---

## Conventions for every task

- Repo: `/rhome/nmath020/bigdata/github/github_tools/RelocaTE/relocate_benchmark/relocate-benchmark`, branch `feat/env-pinning`. Work from repo root.
- pixi is on PATH (`pixi --version` -> 0.70.2). Each manifest materializes a `.pixi/` env dir next to it (gitignored).
- Commit manifests + lockfiles only; never commit `.pixi/`.
- Keep every `env.sh`'s existing tool-presence checks (exit 127 if a required tool is missing).

---

## Task 0: Preflight + gitignore + env/ scaffolding

**Files:**
- Modify: `.gitignore`
- Create: `env/.gitkeep`

**Step 1: Preflight — verify pixi can reach channels and RT3 git.** This gates the whole plan; an earlier `conda search` timed out, so confirm outbound network works from this node before building envs.

Run:
```bash
pixi --version
# channel reachability (small, fast resolve in a temp dir):
tmp=$(mktemp -d); cd "$tmp"; pixi init --channel conda-forge --channel bioconda . >/dev/null
timeout 180 pixi add samtools 2>&1 | tail -5; cd - >/dev/null; rm -rf "$tmp"
# RT3 git reachability + public/private (HTTPS, no prompt):
GIT_TERMINAL_PROMPT=0 timeout 30 git ls-remote https://github.com/stajichlab/RelocaTE3.git HEAD 2>&1 | head -3
```
Expected: `pixi add samtools` resolves and writes a lock (channels reachable); `git ls-remote` prints a SHA (RT3 fetchable over HTTPS → public). 

**If channels are unreachable or slow:** STOP and report — env provisioning must run on a node with outbound network (or configure a proxy). Do not proceed.
**If RT3 `ls-remote` needs auth (private):** report and ask the user how pixi should authenticate the git fetch (token vs ssh) before Task 1.

**Step 2: gitignore the materialized envs.** Add to `.gitignore`:
```
# pixi materialized environments (regenerable from committed pixi.lock)
.pixi/
**/.pixi/
```

**Step 3: scaffold env/ dir.** `mkdir -p env && touch env/.gitkeep`.

**Step 4: Commit.**
```bash
git add .gitignore env/.gitkeep
git commit -m "chore: gitignore pixi envs + env/ scaffold"
```

---

## Task 1: RelocaTE3 benchmark-owned pixi env

**Files:**
- Create: `callers/relocate3/pixi.toml`
- Create (generated): `callers/relocate3/pixi.lock`

**Step 1: Write `callers/relocate3/pixi.toml`.** Mirror RT3's runtime conda deps (from its upstream `pixi.toml`), ADD `bcftools`, and install RelocaTE3 from the pinned git commit instead of an editable path.

```toml
[workspace]
name = "relocate3-benchmark-env"
description = "Frozen RelocaTE3 runtime for the benchmark (pinned git rev)"
channels = ["conda-forge", "bioconda"]
platforms = ["linux-64"]

[dependencies]
python = ">=3.10"
minimap2 = ">=2.24"
samtools = ">=1.17"
bcftools = ">=1.17"     # was patched via `module load bcftools`; now pinned here
bedtools = ">=2.30"
pysam = ">=0.20"
biopython = ">=1.81"
pybedtools = "*"

[pypi-dependencies]
RelocaTE3 = { git = "https://github.com/stajichlab/RelocaTE3.git", rev = "257e2ca791a9d761c2d2e9588e1589fbf953fd3b" }
```
Notes: reconcile the conda dep set against RT3's current upstream `pixi.toml` `[dependencies]` at
`/rhome/nmath020/bigdata/github/github_tools/RelocaTE/RelocaTE3_jason/RelocaTE3/pixi.toml` — include anything `relocaTE3`/`characterize` imports at runtime (pandas/matplotlib were in RT3's manifest; add them if the run needs them). Drop pure dev/test/docs deps (pytest, sphinx, seaborn, matplotlib-venn) unless a run fails without them.

**Step 2: Resolve + lock.**
```bash
cd callers/relocate3 && pixi install 2>&1 | tail -20; cd - >/dev/null
```
Expected: resolves, writes `callers/relocate3/pixi.lock`. If RelocaTE3's git build fails (missing build backend), check RT3's `pyproject.toml`/build system and adjust; report specifics rather than guessing.

**Step 3: Verify tools resolve under the env.**
```bash
eval "$(pixi shell-hook --manifest-path callers/relocate3/pixi.toml)"
for t in relocaTE3 minimap2 samtools bcftools; do command -v "$t" || echo "MISSING: $t"; done
relocaTE3 --help >/dev/null 2>&1 && echo "relocaTE3 runs" || echo "relocaTE3 --help FAILED"
```
Expected: all four present; `relocaTE3 runs`.

**Step 4: Commit.**
```bash
git add callers/relocate3/pixi.toml callers/relocate3/pixi.lock
git commit -m "feat: frozen RelocaTE3 pixi env (git rev 257e2ca + bcftools)"
```

---

## Task 2: RelocaTE3 env.sh -> thin pixi activator

**Files:** Modify `callers/relocate3/env.sh`

**Step 1: Rewrite env.sh** to prefer the pixi env and drop the `module load bcftools` patch (bcftools is now in the manifest). Preserve the required-tool checks and add an unpinned module fallback.

```bash
#!/usr/bin/bash -l
# Activate the frozen RelocaTE3 pixi env for the caller adapter (sourced by run.sh).
set -euo pipefail
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_manifest="$_here/pixi.toml"

if command -v pixi >/dev/null 2>&1 && [[ -f "$_manifest" ]]; then
  eval "$(pixi shell-hook --manifest-path "$_manifest")"
else
  echo "WARN: pixi env unavailable; falling back to UNPINNED modules" >&2
  command -v module >/dev/null 2>&1 && { module load bcftools || true; }
  : "${RT3_REPO:?RT3_REPO must be set for the module fallback}"
  # (legacy fallback path: activate RT3's own manifest if present)
  if command -v pixi >/dev/null 2>&1 && [[ -f "$RT3_REPO/pixi.toml" ]]; then
    eval "$(pixi shell-hook --manifest-path "$RT3_REPO/pixi.toml")"
  fi
fi

for tool in relocaTE3 minimap2 samtools bcftools; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after activating RelocaTE3 env" >&2
    exit 127
  }
done
```

**Step 2: Verify** — `bash -c 'set -e; source callers/relocate3/env.sh; command -v relocaTE3 bcftools'` resolves both.

**Step 3: Commit** `refactor: RelocaTE3 env.sh uses frozen pixi env`.

---

## Task 3: RelocaTE2 pixi env

> **REVISED 2026-07-17 (done):** RT2 CANNOT be a pixi env — `relocate2 2.0.1` is a
> dead Python-2.7 bioconda package whose closure no longer resolves (and it
> hard-pins bwa 0.6.2). Per user decision, RT2 is instead frozen via a
> **pinned-module manifest** (`callers/relocate2/pinned-modules.txt` →
> `relocate2/2.0.1` + `bwa/0.7.19`); `env.sh` reads the pins and keeps the
> pkg-bin-before-modern-bwa load order. Portable freeze deferred to the Phase 2
> Apptainer image. Tasks 3 and 4 were completed together as this pinned-module
> change (commit 85754c8). The pixi manifest below is retained for historical
> context only.

**Files:**
- Create: `callers/relocate2/pixi.toml`
- Create (generated): `callers/relocate2/pixi.lock`

**Step 1: Write `callers/relocate2/pixi.toml`.** Pin `relocate2=2.0.1` (the cluster module version, conda-built) + `bwa=0.7.19` (env.sh currently loads bwa/0.7.19 because RT2's bundled bwa is too old for `bwa mem`).

```toml
[workspace]
name = "relocate2-benchmark-env"
description = "Frozen RelocaTE2 runtime for the benchmark"
channels = ["conda-forge", "bioconda"]
platforms = ["linux-64"]

[dependencies]
relocate2 = "2.0.1"
bwa = "0.7.19"          # relocaTE2 adapter builds the BAM with `bwa mem`
```
Note: `relocate2` should pull blat/bowtie2/samtools/bedtools/bcftools as deps (the cluster 2.0.1 env has them). If any required tool is missing after install, add it explicitly.

**Step 2: Resolve + lock.**
```bash
cd callers/relocate2 && pixi install 2>&1 | tail -20; cd - >/dev/null
```
Expected: resolves, writes `callers/relocate2/pixi.lock`.
**If `relocate2=2.0.1` will not resolve from bioconda:** STOP, report the resolver error, and fall back to the documented pinned-module approach for RT2 (record exact module versions in a `callers/relocate2/PINNED_MODULES.md` and keep a module-based env.sh) — flag this deviation to the user.

**Step 3: Verify tools + bwa version.**
```bash
eval "$(pixi shell-hook --manifest-path callers/relocate2/pixi.toml)"
for t in relocaTE2.py blat bwa samtools; do command -v "$t" || echo "MISSING: $t"; done
bwa 2>&1 | grep -i version | head -1     # expect 0.7.19
```
Expected: all four present; bwa reports 0.7.19.

**Step 4: Commit** `feat: frozen RelocaTE2 pixi env (relocate2=2.0.1 + bwa=0.7.19)`.

---

## Task 4: RelocaTE2 env.sh -> thin pixi activator

> **REVISED 2026-07-17 (done in Task 3's commit 85754c8):** since RT2 uses pinned
> modules (not pixi), `env.sh` was rewritten to read `pinned-modules.txt` and load
> the pinned modules in order, not to activate a pixi env. See the Task 3 revision
> note. The pixi-activator template below does not apply to RT2.

**Files:** Modify `callers/relocate2/env.sh`

**Step 1: Rewrite env.sh** to activate the pixi env, removing the module load + PATH-derivation surgery + `module load bwa/0.7.19`. Keep the required-tool checks; add an unpinned module fallback that reproduces the old behavior.

```bash
#!/usr/bin/bash -l
# Activate the frozen RelocaTE2 pixi env for the caller adapter (sourced by run.sh).
set -euo pipefail
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_manifest="$_here/pixi.toml"

if command -v pixi >/dev/null 2>&1 && [[ -f "$_manifest" ]]; then
  eval "$(pixi shell-hook --manifest-path "$_manifest")"
else
  echo "WARN: pixi env unavailable; falling back to UNPINNED relocate2 module" >&2
  if command -v module >/dev/null 2>&1; then
    module load relocate2 || true
    if command -v relocaTE2.py >/dev/null 2>&1; then
      _pkg="$(dirname "$(dirname "$(command -v relocaTE2.py)")")"
      [[ -d "$_pkg/bin" ]] && export PATH="$_pkg/bin:$PATH"
    fi
    module load bwa/0.7.19 || true
  fi
fi

for tool in relocaTE2.py blat bwa samtools; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after activating RelocaTE2 env" >&2
    exit 127
  }
done
```

**Step 2: Verify** — `bash -c 'set -e; source callers/relocate2/env.sh; command -v relocaTE2.py blat bwa samtools'` resolves all.

**Step 3: Commit** `refactor: RelocaTE2 env.sh uses frozen pixi env`.

---

## Task 5: Benchmark env (python + R report stack)

**Files:**
- Create: `env/benchmark/pixi.toml`
- Create (generated): `env/benchmark/pixi.lock`

**Step 1: Write `env/benchmark/pixi.toml`.** Python for stdlib scoring/orchestration (>=3.11 for tomllib) + R and the report packages.

```toml
[workspace]
name = "relocate-benchmark-env"
description = "Frozen python + R stack for benchmark scoring and reporting"
channels = ["conda-forge", "bioconda"]
platforms = ["linux-64"]

[dependencies]
python = "3.12.*"
r-base = ">=4.3"
r-ggplot2 = "*"
r-dplyr = "*"
r-tidyr = "*"
r-patchwork = "*"
r-scales = "*"
r-forcats = "*"
```

**Step 2: Resolve + lock.** `cd env/benchmark && pixi install 2>&1 | tail -20; cd - >/dev/null`.

**Step 3: Verify R packages + the smoke test run under this env.**
```bash
pixi run --manifest-path env/benchmark/pixi.toml Rscript -e 'library(ggplot2);library(dplyr);library(tidyr);library(patchwork);library(scales);library(forcats);cat("R deps OK\n")'
pixi run --manifest-path env/benchmark/pixi.toml Rscript tests/smoke_report.R 2>&1 | grep smoke:
pixi run --manifest-path env/benchmark/pixi.toml python3 -c 'import tomllib,sys;print("py",sys.version.split()[0])'
```
Expected: `R deps OK`; all 8 smoke checks OK; python >= 3.11.
Note: the report also sources the external ggplot-figures skill helpers (`~/.claude/skills/...`); those are NOT packaged here and the report already falls back gracefully if absent — that's expected, not a failure.

**Step 4: Commit** `feat: frozen benchmark env (python 3.12 + R report stack)`.

---

## Task 6: Wire orchestration to the benchmark env

**Files:** Modify `pipeline/aggregate.sh`, `pipeline/submit_benchmark.sh`

**Step 1: aggregate.sh report step.** Replace the `module load R || true; Rscript scoring/make_report.R ...` block with a pixi-run that falls back to the module:
```bash
BENCH_ENV="env/benchmark/pixi.toml"
if command -v pixi >/dev/null 2>&1 && [[ -f "$BENCH_ENV" ]]; then
  RUN_R=(pixi run --manifest-path "$BENCH_ENV" Rscript)
else
  echo "WARN: benchmark pixi env unavailable; using module R" >&2
  module load R || true
  RUN_R=(Rscript)
fi
if ! "${RUN_R[@]}" scoring/make_report.R reports "$PDF"; then ... ; fi
```

**Step 2: submit_benchmark.sh python.** Where it sets `PY=python3.12`, prefer the benchmark env's python with a fallback:
```bash
if command -v pixi >/dev/null 2>&1 && [[ -f env/benchmark/pixi.toml ]]; then
  PY=(pixi run --manifest-path env/benchmark/pixi.toml python3)
else
  PY=(python3.12)
fi
```
Update call sites to use `"${PY[@]}"`.

**Step 3: Verify** — run the report step path once: `bash -c '. /dev/stdin' <<<'...'` is overkill; instead directly test `pixi run --manifest-path env/benchmark/pixi.toml Rscript scoring/make_report.R reports /tmp/env_report.pdf` prints `Wrote ... (13 pages)`, and `config_env.py` runs under the env: `pixi run --manifest-path env/benchmark/pixi.toml python3 pipeline/config_env.py callers`.

**Step 4: Commit** `feat: run report+scoring under the frozen benchmark env`.

---

## Task 7: Provisioning script + docs

**Files:**
- Create: `pipeline/setup_envs.sh`
- Modify: `README.md`
- Create: `docs/2026-07-17-env-pinning.md`

**Step 1: `pipeline/setup_envs.sh`** — idempotent provisioning of every frozen env:
```bash
#!/usr/bin/bash -l
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
echo "[$(date)] provisioning frozen pixi environments"
for m in callers/relocate2 callers/relocate3 env/benchmark; do
  echo "== pixi install: $m =="
  ( cd "$m" && pixi install )
done
echo "[$(date)] done. Envs materialized under each dir's .pixi/ (gitignored)."
```
`chmod +x pipeline/setup_envs.sh`.

**Step 2: README** — add a "Setup" section: `bash pipeline/setup_envs.sh` before first run; note pixi is required; module fallbacks are unpinned escape hatches.

**Step 3: docs note** `docs/2026-07-17-env-pinning.md` (per repo policy): date/time, what was pinned (RT2=2.0.1, RT3 git rev, benchmark py+R), the "add a caller" recipe (callers/<name>/{pixi.toml,env.sh,run.sh,normalize.py} + benchmark.toml table + config_env.py mapping + env.sh activator template), fallback policy, and how to bump the RT3 rev (edit pixi.toml `rev`, `pixi install`, commit lock).

**Step 4: Commit** `docs: setup_envs.sh + env pinning docs and add-a-caller recipe`.

---

## Task 8: End-to-end verification

**Files:** none (verification), then update `docs/2026-07-17-env-pinning.md` with results.

**Step 1: Fresh-provision smoke.** From a clean state (`.pixi/` dirs may be removed to simulate a fresh clone), run `bash pipeline/setup_envs.sh` and confirm all three envs materialize.

**Step 2: One sample per caller under its frozen env** (gated — this is the ~real run, minutes each). Pick the smallest sample (e.g. cov5x_rep1). For each caller, source its env.sh and run the adapter on that one sample via the existing run path (or `pipeline/submit_benchmark.sh --caller <name> --coverage 5 --sample ...` filtered to one task). Confirm the run completes and emits `calls.normalized.tsv`.
If full runs are too costly here, substitute a lighter proof: under each caller env, `relocaTE2.py -h` / `relocaTE3 --help` succeed and all required tools report versions — and record that the full one-sample run is deferred to a SLURM submission. State clearly which was done.

**Step 3: Report parity.** `pixi run --manifest-path env/benchmark/pixi.toml Rscript scoring/make_report.R reports /tmp/env_report.pdf` → 13 pages, no errors; smoke 8/8.

**Step 4:** Record outcomes (versions resolved, what was run vs deferred) in the docs note. Commit `docs: env pinning verification results`.

**Step 5 (handoff):** Open a PR from `feat/env-pinning` (only when the user asks).

---

## Risks / notes

- **Network:** conda channel access is required for every `pixi install`; an earlier `conda search` timed out. Task 0 gates on reachability. If blocked, provisioning must run on a networked node.
- **RT3 git auth:** if `stajichlab/RelocaTE3` is private, pixi's git fetch needs auth — resolved in Task 0 before Task 1.
- **relocate2 resolve:** if `relocate2=2.0.1` is not on bioconda, Task 3 falls back to a documented pinned-module set (flagged to the user).
- **Behavior parity:** pinning aims to reproduce today's behavior; the RT2 `bwa=0.7.19` pin and RT3 git rev 257e2ca are chosen to match what the last benchmark actually ran.
- The caller-adapter contract and `benchmark.toml`/`config_env.py` registry are unchanged; this plan only swaps how each env is provisioned + activated.
