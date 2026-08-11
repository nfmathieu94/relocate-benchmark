# riceTElib R2/R3 BLAT parity run — final results

**Date:** 2026-08-10 20:56 PDT
**Branch:** `chore/repin-rt3-blat-parity`
**Arrays:** `27262453` (cov5x only; 15x/30x cancelled on the 24h cap), `27293494` + aggregate `27293495` (completed under the 96h cap)
**R3 pin:** `50f939e` (BLAT RelocaTE2-parity fix: `-minScore=10 -tileSize=7`)

## Status: COMPLETE

All 18 tasks COMPLETED. Runtimes confirmed the earlier projections and the need
for the 96h limit:

| Coverage | Wall time | Prior projection |
|---|---|---|
| 5x | 8h38m–8h46m | 8h44m (measured) |
| 15x | 1d04h58m–1d05h42m (~29.7h) | ~26h |
| 30x | 2d01h02m–2d04h22m (~50.9h) | ~52h |

## Verdict: parity NOT achieved. The BLAT fix (PR #40) is a regression — revert it.

### All coverages pooled (9 samples, 4500 truth events)

| Caller | Recall | Precision | F1 | TSD exact | Status acc. | Calls | FP |
|---|---|---|---|---|---|---|---|
| relocate2 | 0.463 | **0.830** | **0.595** | 0.447 | 0.565 | 2512 | 427 |
| R3 blat-bwaaln post-fix | **0.517** | 0.325 | 0.399 | 0.451 | 0.571 | 7156 | 4828 |
| Δ (R3 − RT2) | +0.054 | **−0.505** | **−0.195** | +0.004 | +0.006 | | |

### Per coverage — the precision collapse scales with depth

| Coverage | | recall | precision | F1 | calls | FP |
|---|---|---|---|---|---|---|
| 5x | relocate2 | 0.299 | 0.813 | 0.438 | 552 | 103 |
| | R3 **post**-fix | 0.332 | 0.635 | 0.436 | 784 | 286 |
| | R3 **pre**-fix | 0.303 | 0.830 | **0.444** | 548 | 93 |
| 15x | relocate2 | 0.493 | 0.836 | 0.620 | 884 | 145 |
| | R3 **post**-fix | 0.556 | 0.406 | 0.469 | 2056 | 1222 |
| | R3 **pre**-fix | 0.521 | 0.847 | **0.645** | 922 | 141 |
| 30x | relocate2 | 0.598 | 0.834 | 0.696 | 1076 | 179 |
| | R3 **post**-fix | 0.664 | 0.231 | 0.343 | 4316 | 3320 |
| | R3 **pre**-fix | 0.641 | 0.844 | **0.729** | 1138 | 177 |

**R3 pre-fix beats RelocaTE2 on F1 at every coverage** (0.444/0.645/0.729 vs
0.438/0.620/0.696), with higher recall *and* higher precision. The parity goal
was already met before PR #40.

Post-fix, precision degrades monotonically with depth — 0.635 → 0.406 → 0.231 —
because false positives grow superlinearly with read depth while true detections
do not:

| FP count | 5x | 15x | 30x |
|---|---|---|---|
| relocate2 | 103 | 145 | 179 |
| R3 pre-fix | 93 | 141 | 177 |
| R3 post-fix | 286 | 1222 | 3320 |

RT2 and R3-pre-fix hold FP roughly flat as coverage rises 6×; R3 post-fix grows
its FP count 36×. At 30x, 3320 of R3's 4316 calls are false.

### Validity control

The pre-fix numbers come from the 2026-08-05 archive, scored by older code. To
rule out a scoring-code confound, `relocate2` was compared between the archive
and today's re-score: **byte-identical** (truth=4500, det=2085, calls=2512,
matched=2085, FP=427). The pre/post comparison is sound.

### Character of the added false positives

The fix added 195 / 1084 / 3146 FPs at 5x / 15x / 30x (and removed ~2). They are
consistently:

- **Median TSD length 3 bp** (RT2's FP median is 16 bp)
- Dominated by `unknown` families — LINE/SINE — (142 / 764 / 2256), then
  MITE/Stow (28 / 156 / 475)

R3 pre-fix's FPs were largely a subset of RT2's (84/93, 114/141, 144/177),
i.e. pre-fix R3 reproduced RT2's error profile closely.

**Root cause:** RelocaTE2 runs the *same* `-minScore=10 -tileSize=7` yet holds
precision at 0.83 across all depths. The permissive BLAT hits are therefore
suppressed downstream in RT2 by a filter R3 does not have. The BLAT command line
was never the parity gap.

### Per-TE-group detection recall (all coverages pooled, truth n=450 each)

| te_group | RT2 | R3 post-fix | Δ |
|---|---|---|---|
| CACTA | 0.56 | 0.57 | +0.01 |
| Helitron | 0.02 | 0.59 | **+0.58** |
| LINE | 0.15 | 0.15 | +0.00 |
| LTR_Copia | 0.60 | 0.62 | +0.02 |
| LTR_Gypsy | 0.59 | 0.59 | +0.00 |
| MULE | 0.63 | 0.63 | +0.00 |
| PIF_Harbinger | 0.62 | 0.58 | −0.04 |
| SINE | 0.23 | 0.22 | −0.00 |
| Tc1_Mariner | 0.62 | 0.58 | −0.04 |
| hAT | 0.62 | 0.63 | +0.01 |

R3's entire recall advantage is **Helitron**, where RT2 is effectively blind
(0.02 vs 0.59). Every other group is within ±0.04. This holds pre-fix too, so it
is a genuine R3 capability and not a product of PR #40.

## Decisions / logic

- Runtime cost of the fix is ~8× (BLAT is ~99% of wall time), on top of the
  accuracy regression. There is no axis on which it wins.
- Helitron detection is R3's real differentiator versus RT2 and is independent of
  the BLAT params.

## Next steps

1. **Revert the BLAT sensitivity params in R3** (`_blat_cmd` in
   `src/RelocaTE3/aligners.py`, back to BLAT defaults 30/11). Keep the per-stage
   `te_opts`/`genome_opts` passthrough and the CLI `--te-opts`/`--genome-opts`
   flags from PR #40 — those are independently useful and not implicated. The
   sensitized params remain reachable via `--te-opts` for anyone who wants them.
2. Re-pin `callers/relocate3/pixi.toml` to the revert commit and re-run riceTElib
   to confirm R3 ≥ RT2 (expected: F1 0.444/0.645/0.729). Cheap — ~1h/task.
3. Only then cut the stable R3 release.
4. Optional follow-up, not a release blocker: find RT2's downstream short-TSD
   LINE/SINE filter. Porting it would let R3 run sensitized BLAT *and* keep
   precision — the only route to beating RT2 on recall by more than Helitron.
5. `pblat` / chunked BLAT stays deferred — reverting to default BLAT params
   removes the runtime pressure that motivated it.
