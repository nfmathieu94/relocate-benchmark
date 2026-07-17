#!/usr/bin/env Rscript
# Dependency-free smoke checks: each builder returns a ggplot from real reports/.
source("scoring/report_lib.R")
reports_dir <- "reports"
matches <- load_matches(reports_dir)
truth   <- load_truth("truth/truth.tsv")
corr <- read_tsv("reports/correctness.tsv")
prec <- read_tsv("reports/precision.tsv")
h2h  <- read_tsv("reports/head_to_head.tsv")
stopifnot(is.data.frame(matches), nrow(matches) > 0)
cat(sprintf("smoke: loaded %d match rows across %d callers\n",
            nrow(matches), length(unique(matches$caller))))
check <- function(label, p) {
  stopifnot(inherits(p, c("ggplot", "patchwork")))
  cat(sprintf("smoke: %-24s OK\n", label))
}
# path metadata parsed correctly
stopifnot(all(c("caller","coverage","replicate","sample") %in% names(matches)))
stopifnot(is.integer(matches$coverage) || is.numeric(matches$coverage))
# row count equals sum of per-file rows
files <- Sys.glob(file.path(reports_dir, "per_sample", "*", "*", "matches.tsv"))
n_expected <- sum(sapply(files, function(f) nrow(read_tsv(f))))
stopifnot(nrow(matches) == n_expected)

# ---- plot-builder smoke checks -------------------------------------------
check("A1 confusion", plot_confusion(matches))
check("A2 breakpoint", plot_breakpoint(matches))
check("A3 intersection", plot_intersection(matches))
check("A4 missed profile", plot_missed_profile(matches))
check("B1 LOD50", plot_lod(matches))
