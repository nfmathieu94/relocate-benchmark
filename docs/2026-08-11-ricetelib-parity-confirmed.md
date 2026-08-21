# riceTElib R2/R3 parity — CONFIRMED after the BLAT revert

**Date:** 2026-08-11 15:43 PDT
**Array:** `27384890` + aggregate `27384908` (all 18 tasks COMPLETED)
**R3:** `6fe6d5d` (PR #41, BLAT-defaults revert)

## Status: PARITY ACHIEVED — RelocaTE3 ≥ RelocaTE2 on every metric, every coverage

### Pooled (9 samples, 4500 truth events)

| Caller | Recall | Precision | F1 | TSD exact | Status acc. | Calls | FP |
|---|---|---|---|---|---|---|---|
| relocate2 | 0.463 | 0.830 | 0.595 | **0.447** | 0.565 | 2512 | 427 |
| R3 blat-bwaaln (reverted) | **0.488** | **0.843** | **0.618** | 0.424 | **0.601** | 2608 | 410 |
| Δ (R3 − RT2) | +0.025 | +0.013 | +0.024 | −0.023 | +0.036 | | |

### Per coverage

| Coverage | Caller | Recall | Precision | F1 |
|---|---|---|---|---|
| 5x | relocate2 | 0.299 | 0.813 | 0.438 |
| | R3 reverted | 0.303 | 0.830 | **0.444** |
| 15x | relocate2 | 0.493 | 0.836 | 0.620 |
| | R3 reverted | 0.521 | 0.847 | **0.645** |
| 30x | relocate2 | 0.598 | 0.834 | 0.696 |
| | R3 reverted | 0.641 | 0.845 | **0.729** |

R3 wins recall, precision and F1 at all three coverages. The advantage grows with
depth (F1 +0.007 / +0.025 / +0.033).

### Reproduction check

The revert reproduces the pre-#40 archive essentially exactly:

| | recall | precision | F1 |
|---|---|---|---|
| R3 now (reverted, `6fe6d5d`) | 0.488 | 0.843 | 0.618 |
| R3 pre-#40 archive (2026-08-05) | 0.488 | 0.842 | 0.618 |

The only difference is a single false-positive call at 30x (176 vs 177 of ~1138),
i.e. run-to-run nondeterminism, not a behavioural change.

### Runtime restored

| Coverage | With PR #40 | After revert |
|---|---|---|
| 5x | 8h38m–8h46m | **13m21s** |
| 15x | ~29.7h | 37m–51m |
| 30x | ~50.9h | 1h10m–1h55m |

~27–40× faster. The 96h array wall limit is no longer needed for this variant,
but is harmless and still protects the sensitized-BLAT sweeps.

## Remaining gap: TSD exactness

The one metric where RelocaTE2 leads, consistently by ~0.02:

| Coverage | RT2 | R3 |
|---|---|---|
| 5x | 0.282 | 0.262 |
| 15x | 0.477 | 0.455 |
| 30x | 0.581 | 0.555 |

Small and stable, and R3 more than offsets it on status accuracy (+0.036). Not a
release blocker, but it is the obvious next accuracy target.

## Important: the pixi pin is a FALLBACK, not what runs

`callers/relocate3/env.sh:8` activates the **`RT3_REPO` dev checkout's own pixi
env** whenever `RT3_REPO` is set, which `config/benchmark.toml` does set (line
111) for every relocate3 variant. That env installs RelocaTE3 as
`{ path = ".", editable = true }`, so **the benchmark runs the dev repo's current
working tree, not `callers/relocate3/pixi.toml`'s pinned rev.**

This is how array `27384890` picked up the revert without any re-pin: the dev
repo had been merged to `main` at `6fe6d5d`.

Consequences:

- Re-pinning `callers/relocate3/pixi.toml` does **not** control what a run
  executes while `RT3_REPO` is set. Verify the *dev repo's* branch before
  submitting.
- The frozen pin only takes effect if `RT3_REPO` is unset or missing. It was
  still pointing at `50f939e` (the regression), so any fallback would have
  silently run the regressed code.

**Fixed:** pin updated to `6fe6d5d`, lock regenerated, and the fallback env
verified to emit BLAT at defaults (`version 0.1.0.post130+g6fe6d5d`).

For genuinely frozen runs, unset `repo` for the caller in `config/benchmark.toml`
so `env.sh` falls through to the pinned env.

## Next steps

1. **Cut the stable RelocaTE3 release.** The gate (R3 ≥ R2 on riceTElib with
   blat/bwaaln) is met.
2. Merge `chore/repin-rt3-blat-parity` to benchmark main.
3. Optional, post-release: close the ~0.02 TSD-exactness gap; port RelocaTE2's
   downstream short-TSD LINE/SINE filter (the only route to running sensitized
   BLAT without the precision collapse); resume the B/C aligner sweeps and the
   divergence panel.
