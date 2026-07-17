# Benchmark Report Plots Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add 8 diagnostic + publication figures (per-event confusion matrix, breakpoint accuracy, missed-event intersection/profile, LOD50 recall-vs-VAF, precision-recall, dumbbell, F1 heatmap) to the RelocaTE benchmark report, plus standalone high-DPI exports.

**Architecture:** Extract report data-loaders and plot-builders into a new sourced `scoring/report_lib.R` so each is a pure function testable from the committed `reports/` data. `make_report.R` becomes a thin driver that sources the lib, assembles pages in section order (Headline -> Diagnostics -> Resources), writes the multipage PDF, and exports select figures to `reports/figures/`. A dependency-free `tests/smoke_report.R` (base `stopifnot`) asserts each builder returns a `ggplot`.

**Tech Stack:** R 4.5.2, ggplot2, dplyr, tidyr, patchwork, scales, forcats (all installed). No `ggupset`, no base-graphics UpSet. Lab styling from `~/.claude/skills/ggplot-figures/R/`.

---

## Conventions for every task

- Work in the benchmark repo: `/rhome/nmath020/bigdata/github/github_tools/RelocaTE/relocate_benchmark/relocate-benchmark`, branch `feat/report-plots-expansion`.
- Run R via: `module load R` then `Rscript ...` (as `pipeline/aggregate.sh` does).
- The committed `reports/` and `truth/` tables are the test fixtures — no new data generation needed.
- Data schemas (verified): `matches.tsv` per-event columns include `biological_class, call_status, matched, distance_bp, tsd_exact, strand, tsd, event_id, expected_vaf, cellular_fraction, position, call_position, te_family`. `correctness.tsv`, `precision.tsv`, `head_to_head.tsv` per the current `make_report.R`.
- Caller-agnostic throughout: never hardcode the caller set; use `pretty_caller()` and `scale_color_lab()`.

---

## Task 0: Create `scoring/report_lib.R` skeleton + smoke harness

**Files:**
- Create: `scoring/report_lib.R`
- Create: `tests/smoke_report.R`

**Step 1:** Create `scoring/report_lib.R` with the shared header (library loads, lab-styling sourcing, `pretty_caller`, `read_tsv`, `sem`, `line_sem`, class level/label vectors) moved out of `make_report.R` verbatim so both files share one copy. Add nothing new yet.

**Step 2:** Create `tests/smoke_report.R`:

```r
#!/usr/bin/env Rscript
# Dependency-free smoke checks: each builder returns a ggplot from real reports/.
source("scoring/report_lib.R")
reports_dir <- "reports"
matches <- load_matches(reports_dir)
truth   <- load_truth("truth/truth.tsv")
stopifnot(is.data.frame(matches), nrow(matches) > 0)
cat(sprintf("smoke: loaded %d match rows across %d callers\n",
            nrow(matches), length(unique(matches$caller))))
# builders appended as tasks land:
check <- function(label, p) {
  stopifnot(inherits(p, c("ggplot", "patchwork")))
  cat(sprintf("smoke: %-24s OK\n", label))
}
```

**Step 3:** Run: `module load R && Rscript tests/smoke_report.R`
Expected: FAIL — `load_matches`/`load_truth` not defined yet. This confirms the harness runs and the functions are missing.

**Step 4:** Commit:
```bash
git add scoring/report_lib.R tests/smoke_report.R
git commit -m "refactor: extract report_lib.R + add smoke harness"
```

---

## Task 1: Data loader (`load_matches`, `load_truth`)

**Files:**
- Modify: `scoring/report_lib.R`
- Modify: `tests/smoke_report.R`

**Step 1 (test):** Append to `tests/smoke_report.R`:

```r
# path metadata parsed correctly
stopifnot(all(c("caller","coverage","replicate","sample") %in% names(matches)))
stopifnot(is.integer(matches$coverage) || is.numeric(matches$coverage))
# row count equals sum of per-file rows
files <- Sys.glob(file.path(reports_dir, "per_sample", "*", "*", "matches.tsv"))
n_expected <- sum(sapply(files, function(f) nrow(read_tsv(f))))
stopifnot(nrow(matches) == n_expected)
```

**Step 2:** Run `Rscript tests/smoke_report.R` -> FAIL (`load_matches` undefined).

**Step 3 (implement):** Add to `report_lib.R`:

```r
# Concatenate every per_sample/<caller>/<sample>/matches.tsv into one tidy
# per-event frame, tagging caller/coverage/replicate parsed from the path.
load_matches <- function(reports_dir = "reports") {
  files <- Sys.glob(file.path(reports_dir, "per_sample", "*", "*", "matches.tsv"))
  if (length(files) == 0) stop("no matches.tsv under ", reports_dir, "/per_sample")
  parts <- lapply(files, function(f) {
    d <- read_tsv(f)
    if (nrow(d) == 0) return(NULL)
    rel    <- strsplit(f, .Platform$file.sep)[[1]]
    caller <- rel[length(rel) - 2]
    sample <- rel[length(rel) - 1]           # e.g. cov15x_rep2
    cov    <- as.integer(sub(".*cov([0-9]+)x.*", "\\1", sample))
    rep    <- as.integer(sub(".*rep([0-9]+).*", "\\1", sample))
    d$caller <- pretty_caller(caller); d$sample <- sample
    d$coverage <- cov; d$replicate <- rep
    d
  })
  dplyr::bind_rows(parts)
}

load_truth <- function(path = "truth/truth.tsv") read_tsv(path)
```

**Step 4:** Run `Rscript tests/smoke_report.R` -> PASS (loader block); expected `18` files, prints match-row count.

**Step 5:** Commit `refactor: add per-event matches loader`.

---

## Task 2: A1 — genotype/detection confusion matrix (`plot_confusion`)

**Files:** Modify `scoring/report_lib.R`, `tests/smoke_report.R`

**Step 1 (test):** append `check("A1 confusion", plot_confusion(matches))`.

**Step 2:** Run -> FAIL (undefined).

**Step 3 (implement):** truth rows {homozygous, heterozygous, somatic_insertion}; called cols {homozygous, heterozygous, missed}. A row is "missed" when `matched == 0`; else the called genotype is `call_status`. Somatic truth uses `biological_class == "somatic_insertion"`.

```r
plot_confusion <- function(matches) {
  df <- matches %>%
    dplyr::mutate(
      truth_class = factor(biological_class, levels = class_levels),
      called = ifelse(matched == 0 | is.na(call_status) | call_status == "",
                      "missed", call_status),
      called = factor(called, levels = c("homozygous","heterozygous","missed"))) %>%
    dplyr::filter(!is.na(truth_class)) %>%
    dplyr::count(caller, truth_class, called, name = "n") %>%
    dplyr::group_by(caller, truth_class) %>%
    dplyr::mutate(row_frac = n / sum(n)) %>% dplyr::ungroup()
  ggplot(df, aes(called, truth_class, fill = row_frac)) +
    geom_tile(colour = "white", linewidth = 0.5) +
    geom_text(aes(label = sprintf("%d\n%.0f%%", n, 100 * row_frac)), size = 3) +
    facet_wrap(~caller) +
    scale_fill_gradient(low = "#F7FBFF", high = "#08519C", labels = percent,
                        limits = c(0, 1), name = "Row %") +
    scale_x_discrete(labels = c(homozygous="Hom", heterozygous="Het", missed="Missed")) +
    scale_y_discrete(labels = class_labs) +
    labs(title = "Genotype / detection confusion",
         subtitle = "Row-normalised: where each truth class's events land (pooled over coverage)",
         x = "Called status", y = "Truth class")
}
```

**Step 4:** Run smoke -> PASS. **Eyeball note:** later full render confirms somatic row splits across Hom/Het/Missed as expected.

**Step 5:** Commit `feat: A1 confusion matrix`.

---

## Task 3: A2 — breakpoint accuracy ECDF (`plot_breakpoint`)

**Step 1 (test):** `check("A2 breakpoint", plot_breakpoint(matches))`.
**Step 3 (implement):** matched events only; `distance_bp` numeric.

```r
plot_breakpoint <- function(matches) {
  df <- matches %>%
    dplyr::filter(matched == 1, !is.na(distance_bp)) %>%
    dplyr::mutate(distance_bp = as.numeric(distance_bp),
                  coverage = factor(paste0(coverage, "x"),
                                    levels = paste0(sort(unique(coverage)), "x")))
  ggplot(df, aes(distance_bp, colour = caller)) +
    stat_ecdf(linewidth = 0.9) + facet_wrap(~coverage) +
    scale_color_lab() +
    scale_x_continuous(limits = c(0, 20)) +
    scale_y_continuous(labels = percent) +
    labs(title = "Breakpoint positional accuracy",
         subtitle = "ECDF of |called - true| position for matched events; steeper/left = better",
         x = "Distance to true position (bp)", y = "Cumulative fraction of calls",
         colour = NULL)
}
```
**Steps 2/4/5:** fail -> pass -> commit `feat: A2 breakpoint ECDF`.

---

## Task 4: A3 — missed-event intersection bar (`plot_intersection`)

**Step 1 (test):** `check("A3 intersection", plot_intersection(matches))`.
**Step 3 (implement):** per `event_id` x sample, which callers detected it (`matched == 1`); classify into RT2-only / RT3-only / both / neither; count. Caller-agnostic: build the set label from whichever callers detected each event.

```r
plot_intersection <- function(matches) {
  callers <- sort(unique(matches$caller))
  det <- matches %>%
    dplyr::group_by(sample, event_id, caller) %>%
    dplyr::summarise(hit = as.integer(any(matched == 1)), .groups = "drop") %>%
    tidyr::pivot_wider(names_from = caller, values_from = hit, values_fill = 0)
  set_label <- function(row) {
    got <- callers[as.logical(unlist(row[callers]))]
    if (length(got) == 0) "Neither"
    else if (length(got) == length(callers)) "Both"
    else paste0(got, "-only")
  }
  det$set <- apply(det, 1, set_label)
  df <- det %>% dplyr::count(set, name = "n") %>%
    dplyr::mutate(set = forcats::fct_reorder(set, n))
  ggplot(df, aes(set, n, fill = set)) +
    geom_col(width = 0.7, show.legend = FALSE) +
    geom_text(aes(label = n), hjust = -0.15, size = 3.4) +
    coord_flip() + scale_color_lab() +
    scale_y_continuous(expand = expansion(mult = c(0, 0.12))) +
    labs(title = "Per-event caller agreement",
         subtitle = "Truth events by which caller(s) detected them (pooled over all samples)",
         x = NULL, y = "Truth events")
}
```
**Steps 2/4/5:** fail -> pass -> commit `feat: A3 intersection bar`.

---

## Task 5: A4 — missed-event profile (`plot_missed_profile`)

**Step 1 (test):** `check("A4 missed profile", plot_missed_profile(matches))`.
**Step 3 (implement):** recall stratified by strand and ambiguous-TSD flag (`tsd` all-N).

```r
plot_missed_profile <- function(matches) {
  df <- matches %>%
    dplyr::mutate(
      ambiguous_tsd = ifelse(grepl("^N+$", tsd), "Ambiguous TSD (N)", "Defined TSD"),
      strand = ifelse(strand %in% c("+","-"), strand, "?")) %>%
    tidyr::pivot_longer(c(strand, ambiguous_tsd),
                        names_to = "facet", values_to = "level") %>%
    dplyr::group_by(caller, facet, level) %>%
    dplyr::summarise(recall = mean(matched == 1), n = dplyr::n(), .groups = "drop") %>%
    dplyr::mutate(facet = dplyr::recode(facet, strand = "Strand",
                                        ambiguous_tsd = "TSD definition"))
  ggplot(df, aes(level, recall, fill = caller)) +
    geom_col(position = position_dodge(0.8), width = 0.7) +
    facet_wrap(~facet, scales = "free_x") +
    scale_color_lab() +
    scale_y_continuous(limits = c(0, 1), labels = percent) +
    labs(title = "What do missed events have in common?",
         subtitle = "Detection recall stratified by strand and TSD ambiguity (pooled)",
         x = NULL, y = "Detection recall", fill = NULL)
}
```
Note: `geom_col(fill=)` needs a fill scale; use `scale_fill_lab()` if the ggplot-figures helper provides one, else fall back to default fill. Verify helper names during implementation (`ls ~/.claude/skills/ggplot-figures/R/`).
**Steps 2/4/5:** fail -> pass -> commit `feat: A4 missed-event profile`.

---

## Task 6: B1 — recall vs VAF with LOD50 (`plot_lod`)

**Step 1 (test):** `check("B1 LOD50", plot_lod(matches))`.
**Step 3 (implement):** per event use `expected_vaf` as continuous x; per caller x coverage compute observed recall at each VAF level, fit `glm(matched ~ log10(vaf), binomial)`, solve for VAF at p=0.5, annotate. Guard groups with <2 distinct VAF or all-0/all-1 recall (skip the fit, plot points only).

```r
plot_lod <- function(matches) {
  pts <- matches %>%
    dplyr::mutate(vaf = as.numeric(expected_vaf)) %>%
    dplyr::group_by(caller, coverage, vaf) %>%
    dplyr::summarise(recall = mean(matched == 1), n = dplyr::n(), .groups = "drop")
  fit_one <- function(d) {
    d <- d[d$n > 0, ]
    if (dplyr::n_distinct(d$vaf) < 3 || all(d$recall %in% c(0,1))) return(NULL)
    m <- tryCatch(glm(recall ~ log10(vaf), weights = n, family = binomial, data = d),
                  error = function(e) NULL)
    if (is.null(m)) return(NULL)
    b <- coef(m); lod <- 10^((0 - b[1]) / b[2])
    grid <- data.frame(vaf = 10^seq(log10(min(d$vaf)), log10(max(d$vaf)), length.out = 60))
    grid$recall <- predict(m, grid, type = "response"); grid$lod <- as.numeric(lod)
    grid
  }
  curves <- pts %>% dplyr::group_by(caller, coverage) %>%
    dplyr::group_modify(~ { g <- fit_one(.x); if (is.null(g)) g <- .x[0, c("vaf","recall")]; g$lod <- if (!is.null(g$lod)) g$lod else NA; g }) %>%
    dplyr::ungroup()
  ggplot(pts, aes(vaf, recall, colour = caller)) +
    geom_line(data = curves, aes(vaf, recall), linewidth = 0.9) +
    geom_point(aes(size = n), alpha = 0.8) +
    facet_wrap(~ paste0(coverage, "x")) +
    scale_color_lab() + scale_size_continuous(guide = "none") +
    scale_x_log10() + scale_y_continuous(limits = c(0,1), labels = percent) +
    labs(title = "Detection sensitivity vs variant allele frequency",
         subtitle = "Logistic fit per caller; VAF at 50% detection = limit of detection (LOD50)",
         x = "Expected VAF (log scale)", y = "Detection recall", colour = NULL)
}
```
Implementation note: keep the LOD50 numeric annotation simple (a `geom_vline` + text per facet); refine label placement during the eyeball step.
**Steps 2/4/5:** fail -> pass -> commit `feat: B1 LOD50 sensitivity curve`.

---

## Task 7: B2 — precision-recall operating points (`plot_pr`)

**Files:** also reads `correctness.tsv` + `precision.tsv` (pass them in).
**Step 1 (test):** load `corr`/`prec` in smoke, then `check("B2 PR", plot_pr(corr, prec))`.
**Step 3 (implement):** recall per caller x coverage x class from `correctness`; precision per caller x coverage from `precision` (precision is per-sample, not per-class — join on caller x coverage x replicate, then average). One point per class, faceted by coverage.

```r
plot_pr <- function(corr, prec) {
  rec <- corr %>%
    dplyr::group_by(caller, coverage, replicate, biological_class) %>%
    dplyr::summarise(recall = sum(detected_events)/sum(truth_events), .groups="drop")
  pr <- prec %>% dplyr::select(caller, coverage, replicate, precision = overall_precision)
  df <- rec %>% dplyr::left_join(pr, by = c("caller","coverage","replicate")) %>%
    dplyr::group_by(caller, coverage, biological_class) %>%
    dplyr::summarise(recall = mean(recall), precision = mean(precision), .groups="drop") %>%
    dplyr::mutate(biological_class = factor(biological_class, levels = class_levels))
  ggplot(df, aes(recall, precision, colour = caller, shape = biological_class)) +
    geom_point(size = 3, alpha = 0.9) + facet_wrap(~ paste0(coverage, "x")) +
    scale_color_lab() +
    scale_shape_discrete(labels = class_labs, name = NULL) +
    scale_x_continuous(limits = c(0,1), labels = percent) +
    scale_y_continuous(limits = c(0,1), labels = percent) +
    labs(title = "Precision-recall operating points",
         subtitle = "One point per biological class; up-and-right is better", colour = NULL)
}
```
Note: `precision.tsv` uses a global denominator (documented caveat) — subtitle should say "precision = matched / all calls (per sample)".
**Steps 2/4/5:** fail -> pass -> commit `feat: B2 precision-recall plot`.

---

## Task 8: B3 — dumbbell RT2 vs RT3 (`plot_dumbbell`)

**Files:** reads `head_to_head.tsv`.
**Step 1 (test):** `check("B3 dumbbell", plot_dumbbell(h2h))`.
**Step 3 (implement):** generalize from the two `*_detection_recall` columns via reshape so it is not hardcoded to exactly two callers where avoidable; acceptable to key on the `head_to_head` wide columns since that table is inherently pairwise.

```r
plot_dumbbell <- function(h2h) {
  df <- h2h %>%
    dplyr::mutate(biological_class = factor(biological_class, levels = class_levels),
                  row = paste0(coverage, "x  ", class_labs[as.character(biological_class)])) %>%
    tidyr::pivot_longer(c(relocate2_detection_recall, relocate3_detection_recall),
                        names_to = "caller", values_to = "recall") %>%
    dplyr::mutate(caller = pretty_caller(sub("_detection_recall","",caller))) %>%
    dplyr::group_by(row, coverage, biological_class, caller) %>%
    dplyr::summarise(recall = mean(recall), .groups = "drop")
  ord <- df %>% dplyr::distinct(row, coverage, biological_class) %>%
    dplyr::arrange(coverage, biological_class)
  df$row <- factor(df$row, levels = rev(ord$row))
  ggplot(df, aes(recall, row)) +
    geom_line(aes(group = row), colour = "grey70", linewidth = 1) +
    geom_point(aes(colour = caller), size = 3) +
    scale_color_lab() + scale_x_continuous(limits = c(0,1), labels = percent) +
    labs(title = "RelocaTE2 vs RelocaTE3 detection recall",
         subtitle = "Each row = coverage x class; gap = head-to-head difference",
         x = "Detection recall", y = NULL, colour = NULL)
}
```
**Steps 2/4/5:** fail -> pass -> commit `feat: B3 dumbbell comparison`.

---

## Task 9: B4 — F1 tile heatmap (`plot_f1`)

**Step 1 (test):** `check("B4 F1", plot_f1(corr, prec))`.
**Step 3 (implement):** F1 from recall (per class) and precision (per sample, averaged to caller x coverage), combined as harmonic mean; tile caller x (coverage x class).

```r
plot_f1 <- function(corr, prec) {
  rec <- corr %>% dplyr::group_by(caller, coverage, biological_class) %>%
    dplyr::summarise(recall = sum(detected_events)/sum(truth_events), .groups="drop")
  pr <- prec %>% dplyr::group_by(caller, coverage) %>%
    dplyr::summarise(precision = mean(overall_precision), .groups="drop")
  df <- rec %>% dplyr::left_join(pr, by = c("caller","coverage")) %>%
    dplyr::mutate(f1 = ifelse(precision + recall > 0,
                              2*precision*recall/(precision+recall), 0),
                  biological_class = factor(biological_class, levels = class_levels),
                  col = paste0(coverage, "x\n", class_labs[as.character(biological_class)]))
  ggplot(df, aes(col, caller, fill = f1)) +
    geom_tile(colour = "white", linewidth = 0.5) +
    geom_text(aes(label = sprintf("%.2f", f1)), size = 3) +
    scale_fill_gradient(low = "#FFF5EB", high = "#7F2704", limits = c(0,1), name = "F1") +
    labs(title = "F1 (detection x precision) by condition",
         subtitle = "Harmonic mean of recall and precision", x = NULL, y = NULL)
}
```
**Steps 2/4/5:** fail -> pass -> commit `feat: B4 F1 heatmap`.

---

## Task 10: Wire pages + standalone figure exports into `make_report.R`

**Files:** Modify `scoring/make_report.R`

**Step 1:** Replace the moved header block with `source("scoring/report_lib.R")`. Load `matches <- load_matches(reports_dir)` and build the new pages. Assemble `pages` in section order using patchwork title spacers:
Headline: existing p1-p4, then B1, B2, B3, B4.
Diagnostics: A1, A2, A3, A4.
Resources: existing p5 (optional).

**Step 2:** After the multipage PDF loop, export standalone figures:

```r
fig_dir <- file.path(reports_dir, "figures"); dir.create(fig_dir, showWarnings = FALSE, recursive = TRUE)
standalone <- list("lod50" = plot_lod(matches), "precision_recall" = plot_pr(corr, prec),
                   "confusion_matrix" = plot_confusion(matches))
for (nm in names(standalone)) {
  p <- standalone[[nm]] + theme_lab()
  if (exists("save_figure")) save_figure(p, file.path(fig_dir, nm))     # helper picks DPI/size
  else ggsave(file.path(fig_dir, paste0(nm, ".png")), p, width = 9, height = 6, dpi = 300)
}
```
Confirm the `save_figure` signature during implementation (`sed -n 1,60p ~/.claude/skills/ggplot-figures/R/save_figure.R`) and adapt the call; the `ggsave` branch is the guaranteed fallback.

**Step 3 (verify render):** `module load R && Rscript scoring/make_report.R reports /tmp/rpt.pdf`
Expected: `Wrote /tmp/rpt.pdf (N pages)` with N = old pages + 8; `reports/figures/` contains 3 files. No errors.

**Step 4 (eyeball):** open the PDF and each figure; confirm: confusion somatic row splits Hom/Het/Missed; LOD curves monotone with sane LOD50; PR points in-range; dumbbell rows ordered coverage-then-class. This is a visual check, not an automated assertion.

**Step 5:** Commit `feat: wire diagnostic+publication pages and figure exports`.

---

## Task 11: Full pipeline smoke + docs

**Files:** Modify `docs/` (progress note), verify `pipeline/aggregate.sh` still drives the report.

**Step 1:** Run the smoke harness end to end: `module load R && Rscript tests/smoke_report.R` -> all `OK` lines, no error.
**Step 2:** Confirm `pipeline/aggregate.sh` needs no change (it calls `Rscript scoring/make_report.R reports "$PDF"`); the new `reports/figures/` are written as a side effect.
**Step 3:** Add a dated note under `docs/` (per repo policy): what was added, how to regenerate (`Rscript scoring/make_report.R`), the LOD50 caveat (needs >=3 VAF levels per group), and the `precision.tsv` global-denominator caveat carried into B2.
**Step 4:** Commit `docs: report plots progress note`.
**Step 5 (handoff):** Open a PR from `feat/report-plots-expansion` (only when the user asks).

---

## Notes / caveats to preserve

- `precision.tsv` precision uses a global (all-calls) denominator; B2/B4 inherit this — stated in subtitles, not silently.
- Callers emit no `somatic` status word; A1's "missed" column + Hom/Het split is the honest representation.
- LOD50 fit is skipped (points-only) for groups with <3 VAF levels or degenerate all-0/all-1 recall — no crash.
- Everything runs from existing committed `reports/`; no re-run of callers required to develop/verify the plots.
