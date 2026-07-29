# 2026-07-29 — Dashboard: two datasets, info page, plot fixes

## Purpose
Make the Streamlit dashboard show both benchmark datasets (mPing + riceTElib)
independently, add a self-contained metrics/dataset glossary, and fix two
confusing plots. Branch: `feat/dashboard-two-dataset-and-info`.

## Current status
Done. 93/93 tests pass (`python3 -m unittest discover -s tests`). All 7 pages
render without exception against the real reports for both datasets.

## What changed
1. **Both datasets exposed.** The suite only loaded datasets in
   `reports/datasets.tsv`, which listed riceTElib alone. mPing predates the
   multi-dataset migration: its aggregated reports sit at the flat report root
   (`reports/*.tsv`) and its `truth/`+`per_sample/` were never moved, so
   `aggregate.sh` cannot re-aggregate it. Added
   `scripts/migrate_legacy_mping_reports.sh` (idempotent) to copy the canonical
   root TSVs into `reports/datasets/mping/` and rebuild the manifest. The
   sidebar `Benchmark dataset` selector now offers both; only one shows at a
   time (never mixed).
2. **Information page** (`dashboard/pages/01_information.py`): plain-language
   guide to both datasets, the ±10 bp match rule, every metric (recall, somatic
   recall, status/exact-TSD accuracy given detected, precision, FDR, FP counts,
   the FPR caveat, the Helitron/no-TSD Simpson's-paradox trap), and how to read
   each plot. Static page, no data filters.
3. **TE-groups y-axis** (`dashboard/plots/accuracy.py`): faceted line plots were
   overprinting a y-title per facet. Added `_use_shared_y_title` — one shared
   rotated title, mirroring the shared "Coverage (x)" x-title.
4. **Head-to-head bars**: `px.bar` was summing the per-slice recall rows so bars
   clipped near 100 % while the label read the true (small) value. Now aggregated
   to the mean per bar before plotting.

## Commands
```bash
# Populate reports/datasets/mping/ (needed once per machine; dir is gitignored)
bash scripts/migrate_legacy_mping_reports.sh

# Run dashboard
pixi run --manifest-path env/benchmark/pixi.toml \
  streamlit run dashboard/app.py

# Tests
pixi run --manifest-path env/benchmark/pixi.toml \
  python3 -m unittest discover -s tests -p "test_*.py"
```

## Notes / caveats
- `reports/datasets/` is gitignored (regenerable artifacts). On a fresh checkout
  run the migration script to make mPing appear; riceTElib comes from a normal
  benchmark run. The committed `datasets.tsv` references both dataset dirs,
  consistent with the prior riceTElib-only convention.
- Full mPing parity in the new layout (so `aggregate.sh --dataset mping` works)
  would require migrating `truth/mping` + `reports/datasets/mping/per_sample`;
  out of scope here since the dashboard reads only the four aggregated TSVs.

## Next steps
- Push branch and open PR into `main`.
