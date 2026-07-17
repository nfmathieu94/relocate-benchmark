# Benchmark report plots — expansion design

Date/time: 2026-07-16 America/Los_Angeles

## Purpose

Extend `scoring/make_report.R` with diagnostic and publication-grade figures
for the RelocaTE2-vs-RelocaTE3 benchmark. These plots serve two audiences:

- **Development:** locate *why* and *where* RelocaTE3 underperforms so the tool
  can be improved.
- **Publication:** produce paper-ready comparison figures once RelocaTE3 is
  competitive.

The current report (`make_report.R`) has 5 pages: detection recall, genotype
status accuracy, precision + false positives, somatic recall by cellular
fraction, and compute resources. It reads only the aggregate tables
(`correctness.tsv`, `precision.tsv`, `resources.tsv`) and ignores the per-event
`matches.tsv` files, which carry the richest signal.

## Current status

- Design approved 2026-07-16. Scope: all 8 new pages + standalone figures.
- Not yet implemented.

## Environment (verified 2026-07-16)

- R 4.5.2 (`Rscript`); `make_report.R` invoked from `pipeline/aggregate.sh`
  after `module load R`.
- Available packages: `ggplot2, dplyr, tidyr, patchwork, scales, UpSetR,
  forcats`. **Not** available: `ggupset`.
- 18 `matches.tsv` files at `reports/per_sample/<caller>/<sample>/matches.tsv`
  (2 callers x 9 samples), one row per truth/called event.
- Lab styling helpers sourced from `~/.claude/skills/ggplot-figures/R/`
  (`theme_lab.R`, `palettes.R`, `figure_sizes.R`, `save_figure.R`).

## Data layer (new; enables all pages below)

Add a loader that concatenates every
`reports/per_sample/<caller>/<sample>/matches.tsv` into one tidy per-event
frame, tagging `caller`, `coverage`, `replicate` parsed from the path, and
reads `truth/truth.tsv`. All new pages are `dplyr` transforms of these two
frames. No new package dependencies.

Key columns used from `matches.tsv`: `biological_class`, `call_status`,
`matched`, `distance_bp`, `tsd_exact`, `strand`, `tsd`, `event_id`,
`expected_vaf`, `cellular_fraction`.

## Pages — cluster A (diagnostics)

- **A1 Genotype/detection confusion matrix.** Heatmap per caller. Rows = truth
  class {homozygous, heterozygous, somatic}; columns = called status {hom, het,
  **missed**}. Cells = count and row %. A missed column folds detection failure
  and genotype confusion into one figure; directly shows the somatic -> hom/het
  collapse (callers emit no `somatic` status word).
- **A2 Breakpoint accuracy.** ECDF (+ compact violin) of `distance_bp` per
  caller x coverage. Distinguishes a systematic TSD-length offset from random
  positional scatter.
- **A3 Missed-event intersection.** Bar of event counts in RT2-only /
  RT3-only / both / neither. Rendered as an on-theme ggplot intersection bar
  (not base-graphics `UpSetR`) so it composes with `theme_lab` and the cairo
  PDF device. Pinpoints the specific events RT3 loses that RT2 recovers.
- **A4 Missed-event profile.** For each caller's misses, recall stratified by
  strand and by ambiguous TSD (`NNNNN`). Converts "RT3 is worse" into "RT3 is
  worse at X".

## Pages — cluster B (publication)

- **B1 Recall vs VAF with LOD50.** Pool hom (VAF 1.0), het (0.5) and somatic
  fractions onto a continuous VAF axis; logistic fit per caller x coverage;
  annotate the VAF at 50% detection (limit of detection). Headline sensitivity
  figure for both audiences.
- **B2 Precision-recall operating points.** One point per class, faceted by
  coverage, colored by caller. Canonical TE-benchmark figure.
- **B3 Dumbbell RT2 vs RT3.** Per class x coverage, from `head_to_head.tsv`
  deltas. "Who wins where" at a glance; honest about ties.
- **B4 F1 tile heatmap.** caller x (coverage x class); F1 combines detection
  recall and genotype accuracy.

## Output structure

- Keep the single multipage `reports/benchmark_report.pdf`, reordered into
  labeled sections: Headline (existing p1-4 + B1-B4) -> Diagnostics (A1-A4) ->
  Resources.
- Additionally emit standalone publication figures (B1, B2, A1) into
  `reports/figures/` at publication DPI via the sourced `save_figure.R` helper.

## Constraints / decisions

- Only installed packages; no `ggupset`; no base-graphics UpSet inside the
  ggplot/cairo pipeline.
- Deterministic: sorted/explicit factor levels, no random ordering.
- Robustness: guard empty/NA groups (e.g., a caller with zero matches at 5x)
  so the multipage PDF never crashes mid-render, mirroring the existing
  optional-`resources` pattern.
- Caller-agnostic: color/label by whatever callers are present, as the current
  script already does.

## Failures / issues

- None yet (not implemented).

## Next steps

1. Create the implementation plan (writing-plans skill).
2. Implement the data loader, then pages A1-A4 and B1-B4, then `reports/figures/`
   exports.
3. Regenerate the report from existing `reports/` data and eyeball each page.
