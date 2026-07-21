# Multi-Aligner Benchmark Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Run RelocaTE3 in the benchmark under multiple `(te-aligner, genome-aligner)` combinations, each a registered caller, and have every plot + the dashboard label them `RelocaTE3-<te>/<genome>`.

**Architecture:** The benchmark is already data-driven (tasks = enabled callers × samples; scoring/plots are N-caller-safe). We register per-variant caller entries sharing one adapter (`callers/relocate3`), generalize the config→env bridge to pass the two aligner names, make the array runner resolve the adapter from config, split the adapter's aligner env, and teach the label renderers the `RelocaTE3-<te>/<genome>` form.

**Tech Stack:** python3.12 (stdlib glue), bash + SLURM, pixi (relocate3 caller env), R/ggplot2 (PDF), Streamlit (dashboard).

**Prerequisite:** RelocaTE3 multi-aligner support merged (its plan: `plans/2026-07-20-multi-aligner-plan.md` in the RelocaTE3 repo). This plan assumes `relocaTE3 run --te-aligner X` and `relocaTE3 align-genome --genome-aligner Y` work.

**Design:** Section D of the canonical design doc, which lives in the RelocaTE3 repo at `plans/2026-07-20-multi-aligner-design.md` (RelocaTE3_jason/RelocaTE3). This plan is self-contained; consult the design doc for rationale.

---

## Conventions

- Caller **key** is filesystem-safe: `relocate3-<te>-<genome>` (e.g. `relocate3-bwa-bwa`, `relocate3-blat-bwa`). It is the directory name under `runs/` and `reports/per_sample/`.
- Caller **label** (display) is `RelocaTE3-<te>/<genome>`, derived deterministically from the key. `relocate2` → `RelocaTE2`; `relocate3-minimap2-minimap2` → `RelocaTE3-minimap2/minimap2`.
- Run glue with `python3.12`; unit tests: `pixi run --manifest-path env/benchmark/pixi.toml python -m unittest`.

---

## Task 1: Register aligner-variant callers in config

**Files:** Modify `config/benchmark.toml`.

**Step 1:** Replace the single `[callers.relocate3]` with per-variant entries. Keep `relocate2` unchanged. Default-enable four:

```toml
[callers.relocate3-minimap2-minimap2]
enabled       = true
adapter       = "callers/relocate3"
repo          = "/rhome/nmath020/bigdata/github/github_tools/RelocaTE/RelocaTE3_jason/RelocaTE3"
tsd           = "..."
te_aligner    = "minimap2"
genome_aligner = "minimap2"
label         = "RelocaTE3-minimap2/minimap2"

[callers.relocate3-bwa-bwa]
enabled = true
adapter = "callers/relocate3"
repo    = "${callers.relocate3-minimap2-minimap2.repo}"
tsd     = "..."
te_aligner = "bwa"
genome_aligner = "bwa"
label   = "RelocaTE3-bwa/bwa"

[callers.relocate3-bowtie2-bwa]   # enabled = true; te=bowtie2 genome=bwa; label "RelocaTE3-bowtie2/bwa"
[callers.relocate3-blat-bwa]      # enabled = true; te=blat  genome=bwa; label "RelocaTE3-blat/bwa"
# opt-in extras (enabled=false): relocate3-bwamem2-bwamem2, relocate3-bowtie2-bowtie2, ...
```

**Step 2 (verify):** `python3.12 pipeline/config_env.py --config config/benchmark.toml callers` lists relocate2 + the four relocate3 variants. (Will still be missing env wiring — next tasks.)

**Step 3: Commit** `feat(config): register RelocaTE3 aligner-variant callers`.

---

## Task 2: Generalize the config→env bridge (adapter-based) + label command

**Files:** Modify `pipeline/config_env.py`. Test: `tests/test_config_env.py` (add cases).

**Step 1: Failing test** — assert `caller-env relocate3-bwa-bwa` emits `RT3_REPO`, `TSD_PATTERN`, `RT3_TE_ALIGNER='bwa'`, `RT3_GENOME_ALIGNER='bwa'`; assert a new `adapter relocate3-bwa-bwa` command prints `callers/relocate3`; assert `labels` prints `relocate3-bwa-bwa\tRelocaTE3-bwa/bwa`.

**Step 2: Implement**
- Replace name-keyed `CALLER_ENV_MAP` with an **adapter-keyed** map, resolving each caller's `adapter` (basename) to its env mapping:
  ```python
  ADAPTER_ENV_MAP = {
      "relocate3": {"repo": "RT3_REPO", "tsd": "TSD_PATTERN",
                    "te_aligner": "RT3_TE_ALIGNER", "genome_aligner": "RT3_GENOME_ALIGNER"},
      "relocate2": {"aligner": "RT2_ALIGNER", "size": "RT2_SIZE", "mismatch": "RT2_MISMATCH"},
  }
  def _adapter_key(tbl): return Path(tbl.get("adapter", "")).name or None
  ```
  `_caller_env` looks up `ADAPTER_ENV_MAP[_adapter_key(tbl)]` (fallback: legacy name key for `relocate2` which has no explicit adapter — set `adapter="callers/relocate2"` in config too, or keep a name fallback).
- Add subcommands: `adapter <caller>` → prints the caller's `adapter` (default `callers/<caller>`); `labels` → prints `key\tlabel` for enabled callers, deriving the label from config `label` or, if absent, from the key via the shared convention.
- Add a `pretty_caller(key)` helper in this module (the Python twin used by the dashboard, Task 5) so key→label lives in one Python place.

**Step 3: Run** `pixi run --manifest-path env/benchmark/pixi.toml python -m unittest tests.test_config_env -v` → PASS.
**Step 4: Commit** `feat(config_env): adapter-based env map + RT3 aligner env + labels/adapter cmds`.

---

## Task 3: Array runner resolves adapter + exports aligner env

**Files:** Modify `pipeline/run_benchmark_array.sh`.

**Step 1:** Replace hardcoded `callers/$CALLER` with the configured adapter:
```bash
ADAPTER="$("$PY" pipeline/config_env.py --config "$CONFIG" adapter "$CALLER")"
# ...
bash "$ADAPTER/run.sh"
"$PY" "$ADAPTER/normalize.py" --outdir "$OUTDIR" --sample "$SAMPLE" --te-name "$TE_NAME" --target ALL
```

**Step 2:** Add the two new vars to the exported caller-env list:
```bash
for v in RT3_REPO TSD_PATTERN RT3_TE_ALIGNER RT3_GENOME_ALIGNER RT2_ALIGNER RT2_SIZE RT2_MISMATCH; do
  [[ -n "${!v:-}" ]] && export "${v?}"
done
```
`OUTDIR`/`REPORT_DIR`/`RES_DIR` already use `$CALLER` (the key) — correct, keeps variants isolated.

**Step 3 (verify):** dry-run one task index for a relocate3 variant: confirm it resolves `callers/relocate3/run.sh` and the env has `RT3_TE_ALIGNER`/`RT3_GENOME_ALIGNER`. (Full run in Task 6.)

**Step 4: Commit** `feat(runner): resolve adapter from config; export RT3 aligner env`.

---

## Task 4: Split the RelocaTE3 adapter's aligner env

**Files:** Modify `callers/relocate3/run.sh`.

**Step 1:** Replace `RT3_ALIGNER` with two vars and wire them to the staged CLI:
```bash
RT3_TE_ALIGNER="${RT3_TE_ALIGNER:-minimap2}"
RT3_GENOME_ALIGNER="${RT3_GENOME_ALIGNER:-minimap2}"
# ...
relocaTE3 run ... --te-aligner "$RT3_TE_ALIGNER" --min-match "$RT3_MIN_MATCH" --min-trimmed "$RT3_MIN_TRIMMED" --mismatch "$RT3_MISMATCH"
relocaTE3 align-genome ... --genome-aligner "$RT3_GENOME_ALIGNER"
```
Keep the full-reads-BAM build on minimap2 (genotyping depth; isolates the variable — per design). Update the echo banner to print both aligners. Keep the `.run_complete` skip guard.

**Step 2 (verify):** `bash -n callers/relocate3/run.sh` (syntax) and a `--help`-level check that the flags exist in the installed `relocaTE3`.

**Step 3: Commit** `feat(adapter): RT3 te/genome aligner split (run --te-aligner, align-genome --genome-aligner)`.

---

## Task 5: Label rendering in plots + dashboard

**Files:** Modify `scoring/report_lib.R` (`pretty_caller`), `dashboard/` (add/patch a `pretty_caller`), and wherever the dashboard displays caller names. Optionally `scoring/combine_reports.py` if carrying a `caller_label` column.

**Step 1: R `pretty_caller`** — extend to render the two-part form:
```r
pretty_caller <- function(x) {
  x <- ifelse(grepl("^relocate3-", x),
              sub("^relocate3-([^-]+)-(.+)$", "RelocaTE3-\\1/\\2", x), x)
  ifelse(grepl("^relocate", x, ignore.case = TRUE),
         sub("relocate", "RelocaTE", x, ignore.case = TRUE), x)
}
```
Confirm the palette scales to N callers (make_report.R "colours by whatever callers appear") — if it uses a fixed manual scale, switch to a qualitative scale (e.g. `scale_colour_brewer(palette="Set2")` or `hue_pal`) sized to the caller count.

**Step 2: Python twin** — add `pretty_caller(key)` to the dashboard (import the one from `pipeline/config_env.py` if importable, else a small local copy) and apply it wherever caller names render (app metric list, filters, accuracy page legends). The dashboard already lists callers dynamically, so only the *display* string changes; filter values stay the keys.

**Step 3 (verify):** rebuild the PDF on existing reports and eyeball labels: `module load R && Rscript scoring/make_report.R reports reports/benchmark_report.pdf`. Launch dashboard, confirm `RelocaTE3-<te>/<genome>` appears.

**Step 4: Commit** `feat(report,dashboard): render RelocaTE3-<te>/<genome> labels`.

---

## Task 6: Pin aligner tools + one-variant end-to-end smoke

**Files:** `callers/relocate3/pixi.toml` (+ lock); docs.

**Step 1:** Add `bwa`, `bwa-mem2`, `bowtie2`, `blat` to the relocate3 caller pixi env; `bash pipeline/setup_envs.sh` (or `pixi install` on that manifest). Bump the RelocaTE3 pin to the multi-aligner commit via `pipeline/update_relocate3.sh`.

**Step 2: Smoke one variant on one sample** (no full array): run `relocate3-bwa-bwa` on `cov30x_rep1` through the adapter (reuse `submit_benchmark.sh --caller relocate3-bwa-bwa --sample cov30x_rep1 --no-aggregate`, or a local adapter run). Assert `runs/relocate3-bwa-bwa/cov30x_rep1/raw/results/*.characTErized.txt` is non-empty and scores (precision/recall present). This validates the whole chain before scaling.

**Step 3: Commit** `chore(env): pin bwa/bwa-mem2/bowtie2/blat; docs for aligner variants`.

---

## Task 7: Full multi-aligner run + docs

**Files:** none (run); `README.md`, `docs/data_provenance.md`.

- Submit the full matrix: `bash pipeline/submit_benchmark.sh` (enabled callers × 9 samples → array + dependent aggregation). Mind the maintenance-reservation walltime lesson (lower `--time` if a shutdown reservation blocks scheduling).
- After aggregation: confirm `reports/head_to_head.tsv` has per-variant recall columns, `precision.tsv` per variant, the PDF and dashboard show all `RelocaTE3-<te>/<genome>` labels.
- Update `README.md` (add-a-variant recipe: register `[callers.relocate3-<te>-<genome>]`, no scoring changes) and `docs/data_provenance.md` (which aligner combos were run).
- Commit `docs: multi-aligner benchmark results + add-a-variant recipe`.

---

## Verification (end of plan)

- `config_env.py callers` lists all enabled variants; `caller-env`/`adapter`/`labels` correct (unit tests green).
- One-variant smoke produces scored output before the full run.
- Full run: every plot + dashboard shows `RelocaTE2` and each `RelocaTE3-<te>/<genome>`; per-variant precision/recall in the combined tables.
- No scoring-logic changes were needed (only registry, plumbing, labels) — confirming the caller-agnostic design held.
