# Fast development tier (RelocaTE3 replay + frozen RelocaTE2)

Recorded: 2026-10-19, America/Los_Angeles.
Benchmark branch: `feat/dev-replay-tier`.
Status: implemented and unit-tested; acceptance gate not yet run.
Design: [plans/2026-10-19-dev-replay-tier-design.md](plans/2026-10-19-dev-replay-tier-design.md).
Plan: [plans/2026-10-19-dev-replay-tier.md](plans/2026-10-19-dev-replay-tier.md).

## Purpose

Benchmark a RelocaTE3 change without rerunning BLAT (about 93% of a 30x
multi-TE run) when the change is downstream of the TE search (trim, genome placement, insertion finding,
characterization). Accuracy only; release evidence still needs the full tier.

## What it does

- `config/benchmark.dev.toml` defines two callers: `relocate3-replay` and
  `relocate2-frozen`. Outputs go to `runs/dev/` and `reports/dev/`.
- `relocate3-replay` runs the standard RelocaTE3 adapter with
  `RT3_REPLAY_MANIFEST` set. It reuses the checkpoint's cached TE-search BAMs
  (`<sample>.left/right.bam`) and all-read genotyping BAM, and reruns trim,
  align-genome, find-insertions and characterize from the RelocaTE3 checkout.
- `relocate2-frozen` copies RelocaTE2's stored normalized calls from the
  checkpoint (no RelocaTE2 run).
- Cache: `runs/checkpoint-213a0df`, registered by
  `config/replay/checkpoint-213a0df.json` (RelocaTE3 `213a0df`, TE aligner
  `blat`). `callers/relocate3-replay/check_cache.py check` guards every sample.

## Commands

Run from the benchmark root (main checkout, where `runs/` and `cache/` live).

```bash
# Full dev run: 72 frozen copies + 72 replays
CONFIG=config/benchmark.dev.toml bash pipeline/submit_benchmark.sh --dataset full

# Quick tier: subset of coverages, one replicate
CONFIG=config/benchmark.dev.toml bash pipeline/submit_benchmark.sh \
  --dataset full --coverage 5,15 --replicate 1

# Test a RelocaTE3 worktree instead of the configured checkout
CONFIG=config/benchmark.dev.toml bash pipeline/submit_benchmark.sh \
  --dataset full --rt3-repo ../../RelocaTE3_jason/<worktree>

# Acceptance gate (after aggregation; needs a complete 72-sample dev run)
python3.12 scripts/compare_replay_gate.py --out reports/dev/replay_gate.tsv

# Before testing a different RelocaTE3 tree: move the previous dev run aside
mv runs/dev runs/dev-<label>
mv reports/dev reports/dev-<label>
```

## Reruns and stale results

Each replay writes `runs/dev/<ds>/relocate3-replay/<sample>/replay_source.txt`:
`<HEAD sha> <sha256>` from `check_cache.py identity`, where the digest covers
`git diff HEAD -- src` plus every untracked file under `src/` (bytecode caches
ignored). A completed replay is skipped only when the current `--rt3-repo` tree
has the same identity. Any other tree (new commit, uncommitted edit, new file,
different checkout) exits 1 with "holds replay results from a different
RelocaTE3 tree" and leaves the old outputs untouched.

So move `runs/dev` and `reports/dev` aside between dev runs of different trees.
The `relocate2-frozen` copies do not depend on RelocaTE3; they may be kept
(move only `runs/dev/*/relocate3-replay`) or moved with the rest. The full tier
is unchanged (no identity check).

## When replay is refused

`check_cache.py check` exits non-zero and the sample fails (no silent fallback)
when any of these hold:

- `src/RelocaTE3/aligners.py` or `src/RelocaTE3/ReadLibrary.py` differs from
  `213a0df`, including uncommitted working-tree edits. Paths are anchored at the
  repo top level, so running from a subdirectory cannot match nothing.
- The TE library sha256 differs from the manifest's value for that dataset.
- The replay caller's TE aligner is not the manifest's `blat`.
- The R1, R2 or reference file is newer than the cached `.run_complete`.
- A cached left/right/original-reads BAM or its `.bai` is missing or empty.
- The source run has no `.run_complete`.

Fix: revert the change, or use the full tier (`config/benchmark.toml`).

## Caveats

- (a) Accuracy only. `resources.tsv` under `reports/dev` measures replays and
  file copies, not real runs.
- (b) Blind spot: the mapping half of `librelocate.py` (`identify_TE_reads`) is
  not guarded. Any TE-search change needs the full tier.
- (c) `aligners.py` also holds the genome-placement backends. Editing them trips
  the guard and forces the full tier even though replay would be valid.
- (d) The mtime check is not a content check. `cp -p` or `touch -d` evades it.
- (e) Replay run dirs have no `original_reads.sorted.bam` (the genotyping BAM is
  read from the cache, read-only). A replay run cannot itself be registered as a
  cache.
- (f) A relative `--rt3-repo` path resolves from the benchmark root.
- (g) Frozen baseline copies are not refreshed on rerun. Delete
  `runs/dev/<ds>/relocate2-frozen/<sample>` to refresh. A run that died
  mid-copy leaves a non-empty incomplete dir that must be removed by hand
  (same as the other adapters).
- (h) The gate script expects a complete 72-sample dev run. Quick-tier subsets
  report the unrun samples as "missing".
- (i) Before the first `--rt3-repo` run against a new RelocaTE3 worktree,
  install that worktree's pixi environment once (`pixi install` in the worktree,
  on a compute node). Every array task activates `$RT3_REPO/pixi.toml`; without
  a prebuilt environment, concurrent tasks would each try to create it, so
  `submit_benchmark.sh` refuses a `--rt3-repo` without
  `.pixi/envs/default/bin/relocaTE3`. It also refuses `--rt3-repo` with any
  `benchmark.checkpoint-*.toml` profile, which is pinned to its RelocaTE3 revision.
- (j) The cache lives in `runs/checkpoint-213a0df` (382 GB). Do not delete it
  while the dev tier is in use. `/bigdata` was 95% full on 2026-10-19.
- (k) `relocate2-frozen` copies the checkpoint's stored `calls.normalized.tsv`
  and does not re-normalize, so it keeps the checkpoint-era RelocaTE2
  normalizer. Only scoring-policy updates (`scoring/`, `lib/`) propagate to it;
  a later change to `callers/relocate2/normalize.py` does not.
- (l) Cosmetic: PDF report labels show `relocate3-replay` unprettified
  (`pretty_caller` in `scoring/report_lib.R` expects `relocate3-<te>-<genome>`);
  `relocate2-frozen` shows as `RelocaTE2-frozen`.

## Checkpoint source guard re-pin

`config/checkpoint-213a0df.source.json` pins benchmark files that this branch
edits: `pipeline/config_env.py`, `pipeline/run_benchmark_array.sh` and
`pipeline/submit_benchmark.sh` (no other pinned file changed; `callers/relocate3/run.sh`
is not pinned). Their hashes were refreshed; the RelocaTE3 `revision` and
`source_sha256` entries are unchanged, and the previous manifest is preserved as
`config/checkpoint-213a0df.pre-dev-replay.source.json` (same precedent as
`pre-r2-recovery`). Checkpoint behavior is unchanged:

- `config_env.py` adds new keys (`replay_manifest`, `frozen.*`) the checkpoint
  config never sets; `RT3_REPO` is overridden only by `--rt3-repo`, which
  `submit_benchmark.sh` now refuses for `benchmark.checkpoint-*.toml`.
- `run_benchmark_array.sh` clears caller variables before `caller-env`; the
  checkpoint config sets every one its callers read (`repo`, `tsd`,
  `te_aligner`, `genome_aligner`, `require_both_junctions`; RelocaTE2
  `aligner`, `size`, `mismatch`).
- `submit_benchmark.sh` changes only `--rt3-repo` handling and skips env
  activation for blat-only selections; the checkpoint profile's bowtie2/bwa/
  minimap2 TE-index preparation is unchanged.

`tests/test_checkpoint_source_manifest.py` recomputes every pinned benchmark
hash, so a future edit without a re-pin fails at test time, not in every
checkpoint task.

## Acceptance gate

Results: TBD. Procedure (maintainer runs it, in the main checkout, after merge):

1. `git pull`.
2. Submit the full dev run (144 tasks: 72 frozen copies + 72 replays):
   `CONFIG=config/benchmark.dev.toml bash pipeline/submit_benchmark.sh --dataset full`.
   RelocaTE3 must be `main` `95c8d68` or any revision whose `aligners.py` and
   `ReadLibrary.py` equal `213a0df`.
3. After aggregation:
   `python3.12 scripts/compare_replay_gate.py --out reports/dev/replay_gate.tsv`.
   Expect exit 0 and every row `identical` (144 calls rows + 144 precision rows).
4. Record per-sample replay wall time (the first measurement of the speedup) from `reports/dev/datasets/*/resources.tsv`
   (relocate3-replay rows) here, then remove the worktree
   (`git worktree remove ../relocate-benchmark-dev-replay`).

## Next steps

- Code review, PR to `main`, maintainer merge.
- Run the acceptance gate and fill in the results above.
