# 2026-07-22 — `compare-callers` benchmark-ranking skill (design)

## Purpose
A project skill the user invokes to get a **status report + ranking** of every
caller/variant that ran on the benchmark, across datasets. Presented in chat and
saved to a file. Read-only over the already-aggregated report tables.

## Approach
Thin SKILL.md wrapping a deterministic helper `scoring/rank_callers.py`, so the
numbers are reproducible (not hand-computed) and testable, matching the repo's
`scoring/` convention.

## Inputs (existing report tables, no re-scoring)
- `reports/correctness.tsv` — per caller × sample × class (recall, status accuracy).
- `reports/precision.tsv` — per caller × sample (precision, false positives).
- `reports/resources.tsv` — per caller × sample (wall time, RSS) — optional.

N-caller/variant-safe: whatever callers appear in the tables are ranked, so new
aligners / re-enabled variants (e.g. bowtie2) show up with no code change.

## Metrics & ranking
For each breakdown, rank callers on:
- **detection recall** = Σdetected / Σtruth (event-weighted)
- **status accuracy | detected** = Σstatus_correct / Σdetected
- **precision** (mean over samples) and **total false positives** — guardrail,
  reported but not folded into the headline (≈saturated here).
- **Composite headline = correctly-genotyped recall = recall × status-accuracy** —
  fraction of truth events both detected AND correctly genotyped.

Near-ties (callers within ~1 pp on a metric) are flagged so tiny gaps
(62.6 vs 62.5) are not over-read.

## Breakdowns ("across datasets")
1. Overall (all data pooled) — headline table.
2. By coverage (5×/15×/30×).
3. By biological class (heterozygous / homozygous / somatic_insertion).
4. By somatic cellular fraction (within somatic; the LOD view).

## Behavior when invoked
1. **Freshness check**: if any `reports/per_sample/*/.complete` is newer than
   `reports/correctness.tsv`, warn that combined tables are stale and suggest
   `bash pipeline/aggregate.sh` before trusting the ranking. Does NOT auto-aggregate.
2. Run `scoring/rank_callers.py` → writes `reports/caller_ranking_<date>.md` and
   prints tables.
3. Claude presents the report in chat (ranked by composite), with a short
   narrative (who wins where, trade-offs) and a caveats line naming which callers
   are present (so a disabled variant is explicitly noted as absent).

## Location
Project-scoped: `.claude/skills/compare-callers/SKILL.md` (version-controlled,
shared on clone). Helper: `scoring/rank_callers.py`.

## Out of scope (YAGNI)
No re-running callers, no plots (dashboard + make_report.R own visuals), no
significance testing beyond the near-tie flag, no weight-tuning UI.

## Testing
- `rank_callers.py` unit-runnable on the current `reports/` (3 callers) — verify
  it ranks, computes composite, handles the somatic-fraction breakdown, and the
  freshness warning fires when correctness.tsv is older than a per_sample marker.
- Skill smoke test: invoke, confirm chat report + saved `reports/caller_ranking_*.md`.
