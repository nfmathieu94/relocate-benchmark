# Report plots expansion — progress

Date/time: 2026-07-16 America/Los_Angeles

## Purpose

Add diagnostic + publication figures to the RelocaTE2-vs-RelocaTE3 benchmark
report, for both development ("where/why does RelocaTE3 underperform") and the
eventual paper. Design: `docs/plans/2026-07-16-benchmark-report-plots-design.md`.
Plan: `docs/plans/2026-07-16-benchmark-report-plots.md`.

## Current status: DONE (on branch `feat/report-plots-expansion`)

`scoring/make_report.R` now renders a 13-page PDF and 3 standalone figures.
Plot builders live in the sourced `scoring/report_lib.R`; a dependency-free
`tests/smoke_report.R` asserts each builder returns a ggplot from the committed
`reports/` data.

Report page order: Headline (recall, status accuracy, precision+FP, somatic
recall, **B1 LOD50, B2 precision-recall, B3 dumbbell, B4 F1**) -> Diagnostics
(**A1 confusion, A2 breakpoint, A3 intersection, A4 missed-profile**) ->
Resources (wall time, RSS).

New builders in `report_lib.R`:
- A1 `plot_confusion` — truth-class x called-status heatmap per caller (called
  axis is data-driven; nothing dropped; rows sum to 100%).
- A2 `plot_breakpoint` — ECDF of `distance_bp` for matched events (uses
  `coord_cartesian`, not scale limits, so the denominator is not truncated).
- A3 `plot_intersection` — per-event caller agreement (Both / <caller>-only /
  Neither).
- A4 `plot_missed_profile` — recall by strand and TSD ambiguity, bars labelled
  with distinct-event counts.
- B1 `plot_lod` — recall vs expected VAF, logistic fit per caller x coverage
  (LOD50 concept).
- B2 `plot_pr`, B4 `plot_f1` — share one `cond_metrics(corr, prec)` helper so
  they never disagree on recall/precision.
- B3 `plot_dumbbell` — RT2-vs-RT3 head-to-head recall.

## Commands

```bash
module load R
cd <repo-root>

# Full report (writes reports/benchmark_report.pdf + reports/figures/*.{pdf,png})
Rscript scoring/make_report.R reports reports/benchmark_report.pdf

# Smoke-test all builders (asserts each returns a ggplot; no rendering)
Rscript tests/smoke_report.R

# Driven automatically by the pipeline after scoring:
bash pipeline/aggregate.sh   # calls make_report.R; no change needed
```

Standalone publication figures (`reports/figures/lod50`, `precision_recall`,
`confusion_matrix`, each `.pdf` + 600-DPI `.png`) are written at
`nature_double` size (183 mm). `reports/figures/` is gitignored (large,
regenerable); regenerate by running make_report.R.

## Findings (from the Chr1 somatic mPing panel)

- **Caller genotype-status vocabulary is richer than previously recorded.** Both
  callers emit `homozygous`, `heterozygous`, `homozygous/excision_no_footprint`,
  AND `somatic_insertion` (RT2: 249 somatic-status calls; RT3: 302). This
  CONTRADICTS the earlier note that callers only emit hom/het and never a
  "somatic" string. A1 shows the full vocabulary.
- **Detection: RelocaTE2 leads recall at every coverage/class.** Per-event
  agreement (A3, pooled over samples): Both 1994, RT2-only 825, RT3-only 135,
  Neither 1546 — RT2 recovers ~6x more events that RT3 misses than vice versa.
- **Somatic is the hard class.** Somatic truth events are mostly Missed
  (RT2 56%, RT3 75%); when detected they are usually called heterozygous.
- **RT3 breakpoint precision is competitive/slightly better** (A2): both callers
  place matched breakpoints within ~5 bp; RT3's ECDF is marginally steeper.
- **RT3 precision decreases with coverage** (B2): ~0.89 (5x) -> ~0.76 (15x) ->
  ~0.71 (30x); RT2 stays ~1.0. Worth investigating.
- **TSD-ambiguity stratification is uninformative on this panel** (A4): only
  1 of 500 truth events has an all-N TSD, and it is missed by both callers.
  A4 labels each bar with its distinct-event count so this reads as n=1, not a
  blank bar.

## Caveats carried into the figures

- `precision.tsv` precision uses a GLOBAL (all-calls) denominator, not per-class;
  B2/B4 inherit this and say so in their subtitles.
- B1's logistic fit is skipped (points only) for a caller x coverage group with
  <3 distinct VAF levels or all-0/all-1 recall. On this panel all 6 groups fit
  (5 VAF levels: 0.05, 0.1, 0.2, 0.5, 1.0).

## Failures / issues

- Bugs caught and fixed during review (all resolved): A1 dropped non-hom/het
  statuses to NA; A3 `apply()` char-coerced hit columns so every event was
  mislabelled "Both"; A2 `scale_x_continuous(limits=)` truncated the ECDF
  denominator. See git history on the branch.

## Next steps

- Optional: draw the LOD50 value as a labelled vline in B1 (currently curves
  only; numeric annotation deferred).
- Open a PR from `feat/report-plots-expansion` (when requested).
- Rerun the benchmark on any regenerated panel, then `make_report.R`.
