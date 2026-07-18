# RelocaTE2 Containerization (Phase 2) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give RelocaTE2 a portable, digest-pinned frozen environment via pulled BioContainers, with the cluster pinned-modules kept as an automatic fallback — closing the one gap Phase 1 left open.

**Architecture:** `callers/relocate2/env.sh` becomes container-first: it exposes `relocaTE2.py`/`blat`/`samtools` (from a `relocate2` BioContainer) and `bwa` (from a `bwa 0.7.19` BioContainer) as `apptainer exec` shim scripts on PATH, so `run.sh` is unchanged. Falls back to Phase 1 pinned modules, then errors. Images are pulled by digest (no local build — that's blocked on this cluster) into a gitignored dir.

**Tech Stack:** apptainer 1.4.5 (`module load apptainer`), quay.io BioContainers, SLURM. Design: `docs/plans/2026-07-17-rt2-container-design.md`.

---

## Conventions for every task

- Repo: `/rhome/nmath020/bigdata/github/github_tools/RelocaTE/relocate_benchmark/relocate-benchmark`, branch `feat/rt2-container`. Work from repo root.
- `module load apptainer` before any apptainer command. Set `APPTAINER_CACHEDIR`/`APPTAINER_TMPDIR` to `/scratch/$USER/...` (repo is on NFS).
- Commit only text (manifests, scripts, docs). NEVER commit `.sif` images (gitignored).
- Pinned image digests (verified 2026-07-17):
  - relocate2: `quay.io/biocontainers/relocate2@sha256:900d3dd35c324f03f328839ce134df937a9f5b0b4b122cbc4cd431eb66c7e109` (tag `2.0.1--hdfd78af_6`)
  - bwa: `quay.io/biocontainers/bwa@sha256:99a35e5ee4e9c329e8746c4689890b97a3ac5620cb36d374cba69ba52016e72a` (tag `0.7.19--h577a1d6_1`)

---

## Task 0: images manifest + gitignore

**Files:**
- Create: `callers/relocate2/images.txt`
- Modify: `.gitignore`

**Step 1:** Create `callers/relocate2/images.txt`:
```
# BioContainer images for the RelocaTE2 adapter, pinned by digest (immutable).
# Format per line: <sifname> <apptainer-pull-ref>
# Pulled by pipeline/setup_envs.sh into callers/relocate2/images/<sifname>.sif
# relocate2 tag 2.0.1--hdfd78af_6 (same build as cluster module relocate2/2.0.1)
relocate2 docker://quay.io/biocontainers/relocate2@sha256:900d3dd35c324f03f328839ce134df937a9f5b0b4b122cbc4cd431eb66c7e109
# bwa tag 0.7.19--h577a1d6_1 (modern bwa for the adapter's `bwa mem` step)
bwa docker://quay.io/biocontainers/bwa@sha256:99a35e5ee4e9c329e8746c4689890b97a3ac5620cb36d374cba69ba52016e72a
```

**Step 2:** Add to `.gitignore`:
```
# RelocaTE2 BioContainer images (large; regenerable from callers/relocate2/images.txt)
callers/relocate2/images/
```

**Step 3:** Commit:
```bash
git add callers/relocate2/images.txt .gitignore
git commit -m "chore: RT2 image manifest (digest-pinned BioContainers) + gitignore images/"
```

---

## Task 1: env.sh — container-first with shims + module fallback

**Files:** Modify `callers/relocate2/env.sh` (READ the current pinned-module version first; keep its `pinned-modules.txt` reading logic as the fallback).

**Step 1:** Rewrite `callers/relocate2/env.sh`:
```bash
#!/usr/bin/bash -l
# RelocaTE2 environment for the caller adapter (sourced by run.sh, not executed).
#
# Container-first: expose relocaTE2.py/blat/samtools (from a relocate2
# BioContainer) and bwa (from a bwa 0.7.19 BioContainer) as apptainer-exec shims
# on PATH, so run.sh is unchanged. RelocaTE2 cannot be a pixi env (dead py2.7
# bioconda package), and this cluster cannot build images locally, so we PULL
# digest-pinned BioContainers (see images.txt). Fallback: Phase 1 pinned cluster
# modules (pinned-modules.txt); then error.
set -euo pipefail
_here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
_img_dir="$_here/images"
_relocate2_sif="$_img_dir/relocate2.sif"
_bwa_sif="$_img_dir/bwa.sif"

_setup_container_env() {
  if ! command -v apptainer >/dev/null 2>&1; then
    command -v module >/dev/null 2>&1 && module load apptainer >/dev/null 2>&1 || true
  fi
  command -v apptainer >/dev/null 2>&1 || return 1
  [[ -f "$_relocate2_sif" && -f "$_bwa_sif" ]] || return 1

  # Bind data + repo + scratch roots so containers see reference/reads/OUTDIR.
  export APPTAINER_BIND="/bigdata,/rhome,/scratch${APPTAINER_BIND:+,$APPTAINER_BIND}"
  export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-/scratch/$USER/apptainer-cache}"

  # Task-scoped shim bin dir: each tool execs its image.
  _shim_bin="$(mktemp -d "${TMPDIR:-/scratch/$USER}/rt2-shims.XXXXXX")"
  local t
  for t in relocaTE2.py blat samtools; do
    printf '#!/usr/bin/bash\nexec apptainer exec %q %s "$@"\n' "$_relocate2_sif" "$t" > "$_shim_bin/$t"
    chmod +x "$_shim_bin/$t"
  done
  printf '#!/usr/bin/bash\nexec apptainer exec %q bwa "$@"\n' "$_bwa_sif" > "$_shim_bin/bwa"
  chmod +x "$_shim_bin/bwa"
  export PATH="$_shim_bin:$PATH"
  return 0
}

_setup_module_env() {
  local pins="$_here/pinned-modules.txt"
  command -v module >/dev/null 2>&1 || return 1
  [[ -f "$pins" ]] || return 1
  local r2 bw pkg
  r2="$(grep -E '^[[:space:]]*relocate2/' "$pins" | head -1 | tr -d '[:space:]')"
  bw="$(grep -E '^[[:space:]]*bwa/' "$pins" | head -1 | tr -d '[:space:]')"
  [[ -n "$r2" && -n "$bw" ]] || return 1
  module load "$r2" || return 1
  if command -v relocaTE2.py >/dev/null 2>&1; then
    pkg="$(dirname "$(dirname "$(command -v relocaTE2.py)")")"
    [[ -d "$pkg/bin" ]] && export PATH="$pkg/bin:$PATH"
  fi
  module load "$bw" || return 1
  return 0
}

if _setup_container_env; then
  :
else
  echo "WARN: RT2 container env unavailable; falling back to UNPINNED pinned cluster modules" >&2
  _setup_module_env || {
    echo "ERROR: could not set up a RelocaTE2 environment (no containers, no modules)" >&2
    exit 1
  }
fi

# Verify every required tool is present; exit 127 if not.
for tool in relocaTE2.py blat bwa samtools; do
  command -v "$tool" >/dev/null 2>&1 || {
    echo "ERROR: $tool not available after RelocaTE2 env setup" >&2
    exit 127
  }
done
```

**Step 2: Verify the fallback path still works** (images not pulled yet, so this exercises the module fallback and the tool checks):
```bash
bash -c 'set -e; source callers/relocate2/env.sh; for t in relocaTE2.py blat bwa samtools; do echo "$t -> $(command -v $t)"; done; bwa 2>&1 | grep -i ^Version | head -1'
```
Expected: with no images present, it WARNs and falls back to modules; all four tools resolve; bwa 0.7.19. (The container path is verified in Task 3 after images exist.)

**Step 3: Commit** `feat: RT2 env.sh container-first with apptainer shims (module fallback)`.

---

## Task 2: setup_envs.sh — pull RT2 images

**Files:** Modify `pipeline/setup_envs.sh` (READ it first; it currently pixi-installs relocate3 + benchmark).

**Step 1:** Add an idempotent apptainer-pull step for the RT2 images. Append after the pixi loop:
```bash
# --- RelocaTE2 BioContainer images (pulled, digest-pinned) ---
RT2_IMG_MANIFEST="callers/relocate2/images.txt"
RT2_IMG_DIR="callers/relocate2/images"
if [[ -f "$RT2_IMG_MANIFEST" ]]; then
  if ! command -v apptainer >/dev/null 2>&1; then
    command -v module >/dev/null 2>&1 && module load apptainer >/dev/null 2>&1 || true
  fi
  if command -v apptainer >/dev/null 2>&1; then
    mkdir -p "$RT2_IMG_DIR"
    export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-/scratch/$USER/apptainer-cache}"
    export APPTAINER_TMPDIR="${APPTAINER_TMPDIR:-/scratch/$USER/apptainer-tmp}"
    mkdir -p "$APPTAINER_CACHEDIR" "$APPTAINER_TMPDIR"
    while read -r _name _ref; do
      [[ -z "$_name" || "$_name" == \#* ]] && continue
      _sif="$RT2_IMG_DIR/$_name.sif"
      if [[ -f "$_sif" ]]; then
        echo "== RT2 image present: $_sif (skip) =="
      else
        echo "== pulling RT2 image: $_name <- $_ref =="
        apptainer pull "$_sif" "$_ref"
      fi
    done < "$RT2_IMG_MANIFEST"
  else
    echo "WARN: apptainer unavailable; skipping RT2 image pulls (env.sh will fall back to modules)" >&2
  fi
fi
```
Update the script's closing note to mention RT2 images are pulled here.

**Step 2: Verify** `bash -n pipeline/setup_envs.sh` parses.

**Step 3: Commit** `feat: setup_envs.sh pulls RT2 BioContainer images`.

---

## Task 3: Provision images + verify containerized tools (no commit)

**Files:** none committed (`.sif` gitignored). This is a provisioning + verification task.

**Step 1: Pull the images.**
```bash
module load apptainer
export APPTAINER_CACHEDIR=/scratch/$USER/apptainer-cache APPTAINER_TMPDIR=/scratch/$USER/apptainer-tmp
bash pipeline/setup_envs.sh 2>&1 | tail -30
ls -lh callers/relocate2/images/
```
Expected: `callers/relocate2/images/relocate2.sif` and `bwa.sif` present. (relocate2 image may be ~hundreds of MB; pull takes minutes.)

**Step 2: Verify tools run THROUGH the containers via the shims.**
```bash
bash -c 'set -e; source callers/relocate2/env.sh
  for t in relocaTE2.py blat bwa samtools; do echo "$t -> $(command -v $t)"; done   # should be the shim bin dir
  relocaTE2.py -h >/dev/null 2>&1 && echo "relocaTE2.py -h OK (container)" || { echo "relocaTE2.py FAILED"; relocaTE2.py -h 2>&1 | tail; }
  echo "bwa: $(bwa 2>&1 | grep -i ^Version | head -1)"     # expect 0.7.19
  echo "samtools: $(samtools --version 2>/dev/null | head -1)"
'
```
Expected: the four tools resolve to the task-scoped shim bin dir (NOT modules); `relocaTE2.py -h OK (container)`; bwa reports 0.7.19; samtools reports a version. If the container can't see input paths in a later real run, revisit the `APPTAINER_BIND` roots.

**Step 3:** Report results (no commit). If the relocate2 image lacks `relocaTE2.py` on PATH or a tool is missing, STOP and report — do not fabricate a fix.

---

## Task 4: Acceptance — real cov5 RelocaTE2 run under the container (controller/user step)

**Not a subagent task** (long SLURM run). Procedure:

**Step 1: Clear the cov5 RelocaTE2 outputs** (rerun hygiene — callers skip on `.run_complete`, and score_calls refuses non-empty report dirs):
```bash
rm -rf runs/relocate2/cov5x_rep* reports/per_sample/relocate2/cov5x_rep*
```

**Step 2: Submit just RelocaTE2 cov5** (the aggregate will run after; or use `--no-aggregate`):
```bash
bash pipeline/submit_benchmark.sh --caller relocate2 --coverage 5
```

**Step 3: When it finishes, confirm success + result parity.** Tasks COMPLETED (sacct), and the per-sample correctness is identical to the committed (pinned-module/Jul-15) baseline:
```bash
git diff --stat -- reports/correctness.tsv    # expect NO change (identical results)
diff <(git show HEAD:reports/correctness.tsv | awk -F'\t' '$1=="relocate2"&&$3==5') \
     <(awk -F'\t' '$1=="relocate2"&&$3==5' reports/correctness.tsv) && echo "cov5 RT2 IDENTICAL under container"
```
Expected: identical. Confirms the container reproduces the pinned-module results.
Revert incidental `resources.tsv`/PDF afterward (`git checkout -- reports/resources.tsv reports/benchmark_report.pdf`).

---

## Task 5: Docs + README

**Files:** Create `docs/2026-07-17-rt2-container.md`; modify `README.md`.

**Step 1: docs note** (repo policy: date/time, purpose, status, commands, decisions, next steps): the container-first RT2 env, the two pinned BioContainer digests, `env.sh` shim mechanism + bind roots, the container→modules fallback chain, how to bump an image (edit digest in `images.txt`, rm the stale `.sif`, `bash pipeline/setup_envs.sh`), and the acceptance result.

**Step 2: README** — update the RelocaTE2 bullet in the "Setup / environments" section: RT2 is now a digest-pinned BioContainer (portable), with the pinned cluster modules as fallback; `setup_envs.sh` pulls the images. Note apptainer is required for the container path.

**Step 3: Commit** `docs: RT2 containerization notes + README`.

---

## Risks / notes

- **No local build** on this cluster (fakeroot/subuid disabled) — hence pulled BioContainers, not built images. Verified pull+exec work.
- **Bind coverage:** containers must see the reference/reads/OUTDIR. Plan binds `/bigdata,/rhome,/scratch`; if a real run can't read an input, widen binds. Task 4's real run is the true test.
- **Behavior parity:** relocaTE2.py inside the container uses the container's own blat/samtools (and old bwa 0.6.2 if it ever calls bwa internally); the adapter's `bwa mem` uses the 0.7.19 image via shim. Task 4's identical-results check validates parity.
- **Digest availability:** if quay ever drops a digest, `setup_envs.sh` pull fails loudly; bump the digest in `images.txt`.
- RT3/benchmark unchanged (pixi). CI→GHCR to containerize those too is a documented future option.
