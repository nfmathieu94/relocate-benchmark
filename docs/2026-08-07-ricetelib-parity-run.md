# riceTElib R2/R3 BLAT parity run — status check

**Date:** 2026-08-07 07:47 PDT
**Branch:** `chore/repin-rt3-blat-parity`
**Array:** `27262453` (riceTElib, `relocate2` + `relocate3-blat-bwaaln`), aggregate `27262454`
**R3 pin:** `50f939e` (BLAT RelocaTE2-parity fix: `-minScore=10 -tileSize=7`)

## Purpose

Confirm RelocaTE3 `blat-bwaaln` reaches parity with RelocaTE2 on riceTElib before
cutting a stable R3 release.

## Current status: INCOMPLETE — will not finish under the old wall limit

| Tasks | Caller | State |
|---|---|---|
| 0–8 | `relocate2` | COMPLETED, ~9 s each (sentinel skip + re-normalize + re-score) |
| 18–20 | `relocate3-blat-bwaaln` cov5x ×3 | COMPLETED, 8h38m–8h46m |
| 21–26 | `relocate3-blat-bwaaln` cov15x/cov30x ×3 each | RUNNING at 13.6 h, **will hit the 24 h cap** |
| — | `aggregate.sh` | PENDING (dependency) |

RT2's fast-skip worked as designed: the caller stage was skipped via
`.run_complete`, but all 36 per-sample TSVs were regenerated, so both callers are
scored by the same current code.

## Failure: BLAT wall-time overrun

`relocate3-blat-bwaaln` spends ~99% of wall time in one monolithic,
single-threaded BLAT over the entire read set. From task 18 (cov5x_rep1):

```
18:06:53  run (map + trim)        <- BLAT
02:43:07  align-genome            <- 8h36m later
          total 8h43m             <- bwa aln genome stage is ~5 min
```

FASTQ sizes scale 1:3:6 across 5x/15x/30x, and BLAT scales linearly with query
volume, so:

| Coverage | Measured / projected BLAT wall |
|---|---|
| 5x | 8h44m (measured) |
| 15x | ~26 h (projected) |
| 30x | ~52 h (projected) |

Both exceed the old `--time=24:00:00`. Confirmed by inspection: after 13.4 h the
cov30x run dirs are still 1.0K (BLAT writes its PSL only at the end).

For scale: RT2 at 30x took 12.4 h *including* its mandatory full reads-to-genome
BAM. R3 is now ~4× slower than RT2. RT2 splits reads into 200k chunks and runs
BLAT in parallel; R3 does not. Chunking was previously assessed as
"performance-only, not correctness" — that is still true for correctness, but it
is load-bearing for feasibility at this scale.

### Change made

`pipeline/run_benchmark_array.sh`: `--time=24:00:00` → `96:00:00` (epyc allows 30
days), with a comment recording the measurements above.

Edited by write-new + atomic `mv` rather than in-place, because six live bash
processes were executing that script and bash reads scripts lazily by offset;
an in-place rewrite can make a running shell execute garbage. The `mv` swaps the
directory entry to a new inode and running jobs keep the old one.

Added `pipeline/clean_incomplete_runs.sh` — dry-run by default, `--apply` to
delete, and refuses to delete while any job of yours is RUNNING. It removes only
run dirs lacking `.run_complete`, which is exactly the state a timed-out task
leaves behind and which the adapters refuse to start into.

## Parity read (cov5x, 3 reps pooled — the only completed coverage)

| Caller | Recall | Precision | F1 | TSD exact | Status acc. |
|---|---|---|---|---|---|
| relocate2 | 0.299 | 0.813 | 0.438 | 0.282 | 0.677 |
| R3 blat-bwaaln **post**-fix | **0.332** | 0.635 | 0.436 | 0.287 | 0.699 |
| R3 blat-bwaaln **pre**-fix | 0.303 | **0.830** | **0.444** | 0.262 | 0.719 |

Calls (total / matched / FP): RT2 552/449/103 · R3post 784/498/286 · R3pre 548/455/93

**Verdict: parity is NOT achieved, and the BLAT fix is net-negative here.**

- R3 post-fix beats RT2 on recall (+0.033) but loses badly on precision
  (−0.178). F1 is a wash (0.436 vs 0.438) at ~8× the runtime.
- R3 **pre**-fix was already at F1 parity with RT2 (0.444 vs 0.438) — slightly
  better precision *and* marginally better recall. The premise that BLAT
  sensitivity was the recall gap does not hold on this dataset.

### Where the extra false positives come from

FP set overlap (cov5x pooled):

- R3 pre-fix FPs (93) are a near-exact subset of RT2's (103) — 93 shared. Pre-fix
  R3 essentially reproduced RT2's error profile.
- The fix added **195 new FPs** and removed 2.
- 73% of the new FPs are LINE (108) or SINE (34); next is MITE/Stow (28).
- New-FP TSD length: **median 3 bp** (mean 15) vs RT2's FP median of 16 bp.

So the added errors are short-TSD LINE/SINE calls.

**Key point:** RT2 runs the *same* `-minScore=10 -tileSize=7` and still holds
precision at 0.813. The permissive BLAT hits are therefore filtered downstream in
RT2 by something R3 lacks. That downstream filter — not the BLAT command line —
is the real parity gap.

### Per-TE-group detection recall (cov5x pooled, truth n=150 each)

| te_group | RT2 | R3 post | R3 pre | Δ (post−RT2) |
|---|---|---|---|---|
| CACTA | 0.33 | 0.33 | 0.31 | +0.00 |
| Helitron | 0.01 | 0.40 | 0.36 | **+0.39** |
| LINE | 0.11 | 0.10 | 0.09 | −0.01 |
| LTR_Copia | 0.40 | 0.40 | 0.37 | +0.00 |
| LTR_Gypsy | 0.37 | 0.37 | 0.32 | +0.00 |
| MULE | 0.41 | 0.41 | 0.39 | −0.01 |
| PIF_Harbinger | 0.43 | 0.42 | 0.39 | −0.01 |
| SINE | 0.15 | 0.14 | 0.13 | −0.01 |
| Tc1_Mariner | 0.37 | 0.35 | 0.32 | −0.02 |
| hAT | 0.41 | 0.41 | 0.36 | +0.00 |

R3 matches RT2 on every group except **Helitron**, where RT2 is effectively blind
(0.01) and R3 gets 0.40. R3's entire recall advantage is Helitron, and it already
had most of it before the fix.

Caveat: cov5x only. 15x/30x may shift these numbers.

## Decisions / logic

- Did not cancel anything (per instruction). The six in-flight tasks will time
  out around 18:07 PDT 2026-08-07; their partial output is not reusable.
- Did not revert the BLAT parity params — that is a call for you to make, and the
  supporting evidence is above.
- Did not submit anything.

## Next steps

1. After the six tasks time out, clean and resubmit 15x/30x:

   ```bash
   cd /rhome/nmath020/bigdata/github/github_tools/RelocaTE/relocate_benchmark/relocate-benchmark
   bash pipeline/clean_incomplete_runs.sh --dataset ricetelib --caller relocate3-blat-bwaaln --apply
   bash pipeline/submit_benchmark.sh --dataset ricetelib --caller relocate2,relocate3-blat-bwaaln
   ```

   The three completed cov5x runs and all nine relocate2 runs will skip on their
   sentinels; only the six missing tasks re-run, now under a 96 h limit.

2. Decide on the BLAT parity params. Reverting to defaults (30/11) restores F1
   parity with RT2 at ~1/8 the runtime; keeping them requires finding RT2's
   downstream filter first.

3. Find RT2's post-BLAT filter (`RelocaTE2/scripts/relocaTE2.py` and the
   downstream perl) that suppresses short-TSD LINE/SINE junctions. That is the
   actual parity gap and the path to "R3 ≥ R2 on both axes."

4. Cut the runtime: `pblat` (not currently on PATH; bioconda has it, and
   `callers/relocate3/blat-env` is already an isolated pixi env for exactly this
   kind of pin) or RelocaTE2-style chunked BLAT. Needed before the divergence
   dataset and the B/C aligner sweeps are affordable.

5. Hold the stable R3 release until 1–3 land.
