# Fast development tier: RelocaTE3 replay + frozen RelocaTE2

Recorded: 2026-10-19, America/Los_Angeles. Branch `feat/dev-replay-tier`.
Status: design approved by maintainer; not yet implemented.

## Purpose

A full benchmark (`--dataset full`, 6 callers) is 432 tasks and about three days.
Most RelocaTE3 changes touch trimming, genome placement, insertion calling, or
characterization — not the BLAT TE search. The TE search is ~93% of a 30x
multi-TE run (riceTElib cov30x_rep1: 11 h 47 min of 12 h 42 min).

The development tier re-runs only the RelocaTE3 stages after the TE search, from
saved intermediates, and reuses RelocaTE2's frozen calls. It measures accuracy
only. The full tier remains the release gate and the only source of resource
numbers.

## Facts the design rests on

- Every checkpoint sample keeps its TE-search BAMs and genotyping BAM under
  `runs/checkpoint-213a0df/<dataset>/relocate3-blat-bwaaln/<sample>/raw/`:
  `<sample>.left.bam`, `<sample>.right.bam`, `<sample>.original_reads.sorted.bam`
  (+ `.bai`). 382 GB across 72 samples.
- `/bigdata` is 95% full. The cache is used in place (symlinks); never copied.
- `relocaTE3 run` = TE-library mapping, then `RelocaTE.write_trimmed_reads`.
  `relocaTE3 trim --bam L R --fastq R1 R2` calls the same function with the same
  arguments (`cli.py:cmd_trim`, `librelocate.py:identify_TE_reads`).
- The genotyping BAM is `minimap2 -a -x sr` of all reads, built by the adapter.
  No RelocaTE3 code is involved.
- RelocaTE2 (`relocate2`) reproduced its historical calls in 72/72 samples and is
  not under development.

## Approach

New benchmark adapters only. No RelocaTE3 change. Alternatives rejected: a
resume-from-stage feature inside RelocaTE3 (changes the tool; Nextflow will cache
stages later), and cloning old run directories (fragile on a near-full disk).

### 1. `callers/relocate3-replay/`

Same steps as `callers/relocate3/run.sh`, except:

- Before any work, run the cache guard (section 2).
- Symlink the cached `left.bam`/`right.bam` (+ `.bai`) into the new `raw/`, then
  `relocaTE3 trim --bam … --fastq R1 R2` with the same `--min-match`,
  `--min-trimmed`, `--mismatch` values. Replaces `relocaTE3 run`.
- `characterize -b` uses the cached `original_reads.sorted.bam` directly; the
  minimap2 rebuild is skipped.
- `align-genome`, `find-insertions` and `characterize` run live.
- `PYTHONPATH="$RT3_REPO/src"` first, and an assertion that the imported
  `RelocaTE3` package lives under `$RT3_REPO/src`.
- Never writes inside the cache directory.

Config keys (exported through `pipeline/config_env.py` and the allowlist in
`pipeline/run_benchmark_array.sh`): `replay_manifest` → `RT3_REPLAY_MANIFEST`.
(Revised during implementation: the run root, source caller and TE aligner
live in the manifest, so no separate root/caller keys are needed.)

### 2. Cache guard: `callers/relocate3-replay/check_cache.py`

Exit non-zero, before work, when any of these fail:

- `src/RelocaTE3/aligners.py` or `src/RelocaTE3/ReadLibrary.py` in `RT3_REPO`
  (working tree, including uncommitted edits) differs from the cache's source
  revision (`213a0df`). These define the BLAT, PSL→SAM and chunking behavior
  that produced the cached BAMs.
- The staged TE library's sha256 differs from the value recorded in the replay
  manifest for that dataset.
- A cached BAM or index is missing or empty, or the source sample lacks `.run_complete`.
- The replay caller's `te_aligner` differs from the TE aligner recorded in the
  manifest (added after code review).
- R1, R2 or the reference is newer than the source sample's `.run_complete`
  (mtime check, not content; added after code review).

Known blind spot: the mapping half of `librelocate.py` (`identify_TE_reads`)
cannot be guarded by file hash because the same file holds the trimming code
under development. Changes to TE search require the full tier.

The replay manifest (`config/replay/checkpoint-213a0df.json`) records the source
revision, run root, source caller, and per-dataset TE-library sha256. A
`register` mode of the same script writes it once.

### 3. `callers/frozen/`

`run.sh` copies `<FROZEN_SOURCE_ROOT>/<dataset>/<FROZEN_SOURCE_CALLER>/<sample>/calls.normalized.tsv`
into `OUTDIR`, requires the source `.run_complete`, and writes the sentinel.
`normalize.py` only checks the file is present. Scoring runs normally, so the
baseline is re-scored under the current scoring policy. Config keys:
`source_root` → `FROZEN_SOURCE_ROOT`, `source_caller` → `FROZEN_SOURCE_CALLER`.

### 4. `config/benchmark.dev.toml` and submission

- Datasets as in `benchmark.toml`, with `coordinate_policy = "tsd-interval"`
  to match the checkpoint.
- Callers: `relocate2-frozen` (frozen adapter, source `runs/checkpoint-213a0df`,
  caller `relocate2`) and `relocate3-replay`.
- `work_root = "runs/dev"`, `report_root = "reports/dev"`.
- Quick tier = existing filters, e.g. `--coverage 5,15 --replicate 1`.
- `submit_benchmark.sh --rt3-repo PATH` overrides the replay caller's `repo`
  (for feature worktrees) without editing the config.
- Resource tables in this tier are not comparable and are labeled as such.

## Acceptance gate (one run after the build)

Replay all 72 samples at RelocaTE3 `main` `95c8d68` (source identical to
`213a0df`). Pass only if:

- `relocate3-replay` normalized calls equal checkpoint `relocate3-blat-bwaaln`
  calls in 72/72 samples (caller column excluded), and
- `relocate2-frozen` per-sample precision tables equal the checkpoint's.

Record replay wall time per sample.

## Testing

Failing tests first, pytest:

- guard: passes when unchanged; fails when `aligners.py` is edited (committed
  or not); fails on TE-library sha256 mismatch; fails on a missing BAM/index or
  missing source `.run_complete`.
- `config_env.py` exports the new keys for both adapters; array allowlist
  includes them.
- frozen adapter copies the source calls, refuses an incomplete source, and is
  idempotent.
- replay adapter (stubbed `relocaTE3` on PATH): calls `trim` not `run`, passes
  the cached genotype BAM to `characterize`, and leaves the cache untouched.

Implementation and unit tests live in the worktree. The gate runs from the main
checkout after merge, because `runs/`, `cache/` and the pixi envs are gitignored
and exist only there.
