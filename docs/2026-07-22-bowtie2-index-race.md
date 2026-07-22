# 2026-07-22 — bowtie2 TE-library index race (DependencyNeverSatisfied)

## Purpose
Fix aggregate job stuck in `DependencyNeverSatisfied` after a benchmark run.

## Current status
FIXED (durable) + rerun submitted.
- Durable fix: pre-flight index build added to `pipeline/submit_benchmark.sh` (section 2b).
- Rerun: array `26574464_[9-17]` (relocate3-bowtie2-bwa) + dependent aggregate `26574465`.

## Symptom
`scontrol show job <agg>` → `Reason=DependencyNeverSatisfied Dependency=afterok:<array>_*(failed)`.
Aggregate is submitted `--dependency=afterok:<array>` (submit_benchmark.sh), so ANY
failed array task makes the dependency permanently unsatisfiable.

## Root cause
All 9 failed tasks were the `relocate3-bowtie2-bwa` variant (only that variant).
RelocaTE3 builds its TE-library index INSIDE `relocaTE3 run` with an unlocked
check-then-build (TOCTOU) in `src/RelocaTE3/aligners.py`:

    if force or not Path(f"{reference}.1.bt2").exists():
        subprocess.run(["bowtie2-build","--quiet",str(reference),str(reference)], check=True)

All 9 tasks launched together, all saw no `.1.bt2`, all ran `bowtie2-build` into the
SAME prefix in the shared `input/TE_lib/` dir → mutual clobbering. Two symptoms, one race:
- bowtie2 self-check trip: "Index is corrupt ... should have been 4194677 but is actually 0".
- partial index read → ~0.02% alignment → empty `all_nonref_insert.txt` → adapter fails.
bwa (`.bwt`) and minimap2 (`.mmi`) TE indexes pre-existed, so those variants never raced.

## Fix (decisions / logic)
Pre-build every shared TE-library index ONCE, serially, before the array fans out
(same pattern as the pre-built genome `.fai`/`.mmi`). Added to submit_benchmark.sh:
enumerate enabled RelocaTE3 callers' `te_aligner`s and build any missing index using
the exact RT3 commands (verified from source):
- bowtie2 → sentinel `.1.bt2`, `bowtie2-build --quiet <ref> <ref>`
- bwa     → sentinel `.bwt`,   `bwa index <ref>`
- minimap2→ sentinel `.mmi`,   `minimap2 -d <ref>.mmi <ref>`
Genome indexes are pre-built out-of-band and already present; not rebuilt here (avoid
heavy compute on the submit node).

## Commands (rerun)
    scancel <dead-aggregate>
    rm -rf runs/relocate3-bowtie2-bwa/cov{5,15,30}x_rep{1,2,3}   # clear failed partials
    bash pipeline/submit_benchmark.sh --caller relocate3-bowtie2-bwa

## Failures / issues
Adapter (callers/relocate3/run.sh) refuses non-empty run dirs without `.run_complete`,
so failed run dirs must be cleared before rerun.

## Next steps
- Commit the submit_benchmark.sh pre-flight change.

---

# Second bug (same day): bowtie2 backend finds 0 insertions

## Symptom
After the index-race fix, the reran bowtie2 tasks STILL failed with
"expected non-reference insertion table not produced" -- `all_nonref_insert.txt`
is 0 bytes for every sample. (This failure was already hitting 6 of the 9
bowtie2 tasks in the original run; the index race masked it on the other 3.)

## Root cause (proven)
RelocaTE3 `Bowtie2Backend.map_te_library` (src/RelocaTE3/aligners.py) maps reads
to the TE library in bowtie2's DEFAULT end-to-end mode (no `--local`). End-to-end
requires a read to align over its full length, so TE-junction reads (part TE,
part genomic flank) -- the reads carrying the insertion signal -- align 0 times
and yield no soft-clipped flank. Result: 0 non-reference insertions.

Measured on a 500k-read subset vs the mPing TE library:
    bwa mem -a            : 559 aligned, 267 soft-clipped
    bowtie2 -k20 (e2e)    : 353 aligned,   0 soft-clipped   <- broken
    bowtie2 -k20 --local  : 559 aligned, 276 soft-clipped   <- matches bwa
Insertion tables: bwa/minimap2 = 295-468 rows/sample; bowtie2 = 0 rows.

## Resolution (decision: disable now, patch RT3 next)
- Benchmark: `config/benchmark.toml` sets `relocate3-bowtie2-bwa` `enabled = false`.
  Enabled callers now: relocate2, relocate3-bwa-bwa, relocate3-minimap2-minimap2
  (27 tasks).
- RelocaTE3: one-line fix prepared on branch `fix-bowtie2-te-local` (commit
  5d839be, off pinned rev 3bac13d) in the RelocaTE3 repo -- adds `--local` to the
  bowtie2 TE-library mapping. NOT pushed; local checkout left on
  feat-selectable-outputs.

## To re-enable bowtie2 later
1. Review/push branch `fix-bowtie2-te-local`; merge to stajichlab/RelocaTE3.
2. Re-pin `callers/relocate3/pixi.toml` `rev` to the merged commit; rebuild env.
3. Validate end-to-end on one sample (expect a non-empty insertion table).
4. Set `relocate3-bowtie2-bwa` `enabled = true`; clear its 9 empty run dirs; rerun.

---

# Third bug (same day): scoring step not rerun-safe

## Symptom
Re-running `submit_benchmark.sh` after `reports/per_sample/` was populated ->
ALL array tasks FAILED fast at the scoring step (aggregate again stuck on
DependencyNeverSatisfied). run adapter skipped (idempotent), normalize ran, then:
    score_calls.py:107 FileExistsError: Refusing non-empty report dir:
    reports/per_sample/<caller>/<sample>

## Root cause
`scoring/score_calls.py` unconditionally refused a non-empty --outdir, even its
OWN completed output (it writes a `.complete` marker but never checked it). So any
rerun failed once per-sample reports existed. Not caused by the earlier fixes.

## Fix
score_calls.py: if --outdir is non-empty AND has `.complete`, treat as this step's
own completed output and replace it (shutil.rmtree + recreate); a non-empty dir
WITHOUT `.complete` is foreign/partial -> still refuse. Verified both paths.

## Fourth bug (same day): PDF report generator hardcoded 2 callers (FIXED)
`scoring/report_lib.R` `plot_dumbbell` hardcoded `relocate2_detection_recall` /
`relocate3_detection_recall`, which no longer exist now that callers are per-variant
(`relocate3-bwa-bwa_detection_recall`, ...). PDF render failed at that page.
Fix: pivot every `ends_with("_detection_recall")` column instead -> caller-agnostic
connected dot plot for any N callers. Verified: `make_report.R` now renders 13 pages
+ standalone figures. `reports/benchmark_report.pdf` current (Jul 22).

## Final state (2026-07-22)
- 3 enabled callers fully scored; reports/*.tsv regenerated over them (no bowtie2).
- No SLURM jobs queued. All stuck aggregates cancelled.
- Run adapter, TE-index pre-build, and scoring are now all rerun-safe.
