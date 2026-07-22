---
name: compare-callers
description: Use when the user wants to compare callers, rank callers, see a benchmark status report, ask which caller is best, or get the caller ranking across the RelocaTE benchmark datasets. Ranks every enabled benchmark caller/aligner variant on a composite correctly-genotyped-recall metric plus per-metric and per-condition breakdowns, and produces a saved status report.
---

# Compare Callers

## Overview

Thin, read-only wrapper around `scoring/rank_callers.py`. It reads the aggregated
benchmark report tables and produces a ranked markdown status report comparing all
enabled callers/aligner variants (composite metric = detection recall x genotype-status
accuracy). This skill only runs the ranking and presents it. Do NOT re-run callers or
re-score anything.

## Steps

1. **Run the ranker from the repo root:**
   ```
   python3.12 scoring/rank_callers.py --reports-dir reports
   ```
   It is stdlib-only (no special environment). If `python3.12` is not found, fall back to
   `python3`. The script prints the report and writes it to `reports/caller_ranking_<date>.md`
   (a `[saved] <path>` line confirms).

2. **Handle staleness / missing tables first:**
   - If the output contains a `WARNING: ... STALE ...` line, surface it **prominently at the
     top** of your response and offer to run `bash pipeline/aggregate.sh` before the user
     trusts the ranking.
   - If the output is the `ERROR: ... not found` (missing `reports/correctness.tsv`) case,
     tell the user to run the benchmark aggregation first (`bash pipeline/aggregate.sh`) and
     **stop** — there is nothing to rank.

3. **Present the report in chat, in this order:**
   1. Headline composite ranking (correctly-genotyped recall).
   2. Overall per-metric rankings: detection recall, genotype-status accuracy,
      precision / false positives.
   3. The three breakdowns: by coverage, by biological class, by somatic cellular fraction.

   Keep the tables readable (preserve the markdown tables from the script output).

4. **Add a short narrative (2-4 sentences):** who wins overall on the composite, notable
   trade-offs (e.g. callers that tie on recall but differ on genotyping accuracy), and
   behavior in the hard cases (low coverage, low somatic cellular fraction). Do NOT overstate
   near-ties — the report marks them `≈tie`; call those effectively even.

5. **State which callers are included**, read straight from the report's "Callers ranked"
   line. Then note any expected-but-absent variant: check `config/benchmark.toml` and if a
   RelocaTE3 aligner variant (e.g. `relocate3-bowtie2-bwa`) has `enabled = false`, say
   explicitly that it is disabled and therefore not part of this comparison.

6. **Point the user to the saved file:** `reports/caller_ranking_<date>.md` (use the exact
   path from the `[saved]` line).

## Notes

- Read-only in spirit: this skill never re-runs callers, re-aligns, or re-scores. It ranks
  whatever is already in `reports/`.
- The metric set is N-caller / variant-safe: it ranks exactly the callers present in the
  tables, so the roster changes automatically as variants are enabled/disabled in
  `config/benchmark.toml`.
