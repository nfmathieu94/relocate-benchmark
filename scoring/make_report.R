#!/usr/bin/env Rscript
# Build the multipage RelocaTE benchmark comparison PDF from the combined
# report tables. Caller-agnostic: colours by whatever callers appear.
#
# Usage:
#   Rscript scoring/make_report.R [reports_dir] [output_pdf]
# Defaults: reports_dir = "reports", output_pdf = "reports/benchmark_report.pdf".

# Shared styling header, TSV reader, and stats/plot helpers live in report_lib.R.
source("scoring/report_lib.R")

# ---- args ----------------------------------------------------------------
args <- commandArgs(trailingOnly = TRUE)
reports_dir <- ifelse(length(args) >= 1, args[1], "reports")
out_pdf     <- ifelse(length(args) >= 2, args[2], file.path(reports_dir, "benchmark_report.pdf"))

corr <- read_tsv(file.path(reports_dir, "correctness.tsv"))
prec <- read_tsv(file.path(reports_dir, "precision.tsv"))
res_path <- file.path(reports_dir, "resources.tsv")
res <- if (file.exists(res_path) && file.info(res_path)$size > 0) read_tsv(res_path) else NULL
matches <- load_matches(reports_dir)
h2h <- read_tsv(file.path(reports_dir, "head_to_head.tsv"))

corr <- corr %>%
  mutate(caller = pretty_caller(caller),
         coverage = as.integer(coverage),
         replicate = as.integer(replicate),
         detected_events = as.numeric(detected_events),
         truth_events = as.numeric(truth_events),
         status_correct_events = as.numeric(status_correct_events),
         biological_class = factor(biological_class, levels = class_levels))
prec <- prec %>%
  mutate(caller = pretty_caller(caller),
         coverage = as.integer(coverage),
         overall_precision = as.numeric(overall_precision),
         false_discovery_rate = as.numeric(false_discovery_rate),
         false_positive_calls = as.numeric(false_positive_calls))

# ---- Page 1: detection recall by class x coverage ------------------------
recall_by_class <- corr %>%
  group_by(caller, coverage, replicate, biological_class) %>%
  summarise(recall = sum(detected_events) / sum(truth_events), .groups = "drop") %>%
  group_by(caller, coverage, biological_class) %>%
  summarise(mean = mean(recall), se = sem(recall), .groups = "drop")

p1 <- line_sem(recall_by_class) +
  facet_wrap(~biological_class, labeller = as_labeller(class_labs)) +
  scale_y_continuous(limits = c(0, 1), labels = percent) +
  labs(title = "Detection recall vs. coverage",
       subtitle = "Fraction of simulated insertions recovered (mean ± SEM, 3 replicates)",
       x = "Coverage (x)", y = "Detection recall")

# ---- Page 2: genotype status accuracy by class x coverage ----------------
status_by_class <- corr %>%
  group_by(caller, coverage, replicate, biological_class) %>%
  summarise(acc = ifelse(sum(detected_events) > 0,
                         sum(status_correct_events) / sum(detected_events), NA_real_),
            .groups = "drop") %>%
  group_by(caller, coverage, biological_class) %>%
  summarise(mean = mean(acc, na.rm = TRUE),
            se = sem(acc[!is.na(acc)]), .groups = "drop")

p2 <- line_sem(status_by_class) +
  facet_wrap(~biological_class, labeller = as_labeller(class_labs)) +
  scale_y_continuous(limits = c(0, 1), labels = percent) +
  labs(title = "Genotype-status accuracy vs. coverage",
       subtitle = "Correct hom/het/somatic call among DETECTED insertions (mean ± SEM)",
       x = "Coverage (x)", y = "Status accuracy | detected")

# ---- Page 3: precision + false positives ---------------------------------
prec_cov <- prec %>%
  group_by(caller, coverage) %>%
  summarise(mean = mean(overall_precision), se = sem(overall_precision), .groups = "drop")
fp_cov <- prec %>%
  group_by(caller, coverage) %>%
  summarise(mean = mean(false_positive_calls), se = sem(false_positive_calls), .groups = "drop")

p3a <- line_sem(prec_cov) +
  scale_y_continuous(limits = c(0, 1), labels = percent) +
  labs(title = "Overall precision", x = "Coverage (x)", y = "Precision (matched / total calls)")
p3b <- line_sem(fp_cov) +
  labs(title = "False-positive calls", x = "Coverage (x)", y = "False-positive calls (count)")
p3 <- (p3a | p3b) + plot_layout(guides = "collect") +
  plot_annotation(title = "Precision and false positives vs. coverage",
                  subtitle = "RelocaTE precision = fraction of calls matching a true insertion (mean ± SEM)",
                  theme = theme_lab())

# ---- Page 4: somatic recall by cellular fraction -------------------------
som <- corr %>%
  filter(biological_class == "somatic_insertion") %>%
  mutate(cf = paste0("Cellular fraction ", cellular_fraction,
                     "  (VAF ", expected_vaf, ")")) %>%
  group_by(caller, coverage, cf, replicate) %>%
  summarise(recall = sum(detected_events) / sum(truth_events), .groups = "drop") %>%
  group_by(caller, coverage, cf) %>%
  summarise(mean = mean(recall), se = sem(recall), .groups = "drop")

p4 <- line_sem(som) +
  facet_wrap(~cf) +
  scale_y_continuous(limits = c(0, 1), labels = percent) +
  labs(title = "Somatic detection recall by cellular fraction",
       subtitle = "Lower cellular fraction = lower variant allele frequency = harder (mean ± SEM)",
       x = "Coverage (x)", y = "Somatic recall")

# ---- Publication pages (B1-B4) and diagnostic pages (A1-A4) ---------------
pB1 <- plot_lod(matches)
pB2 <- plot_pr(corr, prec)
pB3 <- plot_dumbbell(h2h)
pB4 <- plot_f1(corr, prec)
pA1 <- plot_confusion(matches)
pA2 <- plot_breakpoint(matches)
pA3 <- plot_intersection(matches)
pA4 <- plot_missed_profile(matches)

# Section order: Headline -> Diagnostics -> Resources (appended below if present).
pages <- list(p1, p2, p3, p4, pB1, pB2, pB3, pB4,  # Headline
              pA1, pA2, pA3, pA4)                    # Diagnostics

# ---- Page 5: resources (optional) ----------------------------------------
if (!is.null(res)) {
  res <- res %>%
    mutate(caller = pretty_caller(caller), coverage = as.integer(coverage),
           wall_min = as.numeric(wall_seconds) / 60,
           rss_gb = as.numeric(max_rss_kb) / 1e6)
  wall <- res %>% group_by(caller, coverage) %>%
    summarise(mean = mean(wall_min), se = sem(wall_min), .groups = "drop")
  rss <- res %>% group_by(caller, coverage) %>%
    summarise(mean = mean(rss_gb), se = sem(rss_gb), .groups = "drop")
  p5a <- line_sem(wall) + labs(title = "Wall time", x = "Coverage (x)", y = "Wall time (min)")
  p5b <- line_sem(rss) + labs(title = "Peak memory", x = "Coverage (x)", y = "Max RSS (GB)")
  p5 <- (p5a | p5b) + plot_layout(guides = "collect") +
    plot_annotation(title = "Compute resources vs. coverage",
                    subtitle = "Per-sample wall time and peak RSS (mean ± SEM)",
                    theme = theme_lab())
  pages <- c(pages, list(p5))
}

# ---- write multipage PDF -------------------------------------------------
dir.create(dirname(out_pdf), showWarnings = FALSE, recursive = TRUE)
# cairo_pdf renders system fonts (the theme picks Helvetica/DejaVu/etc.) and
# falls back gracefully; the base pdf() device rejects those with "invalid font
# type". Fall back to pdf() only if cairo is unavailable.
if (isTRUE(capabilities("cairo"))) {
  cairo_pdf(out_pdf, width = 9, height = 6.2, onefile = TRUE)
} else {
  pdf(out_pdf, width = 9, height = 6.2, onefile = TRUE)
}
for (p in pages) {
  # `&` applies theme_lab() to every panel of a patchwork; `+` to a lone ggplot.
  if (inherits(p, "patchwork")) print(p & theme_lab()) else print(p + theme_lab())
}
invisible(dev.off())
cat(sprintf("Wrote %s (%d pages)\n", out_pdf, length(pages)))

# ---- standalone figure exports -------------------------------------------
# save_figure() (from the ggplot-figures skill) writes BOTH a cairo PDF and a
# PNG at consistent dimensions; the tryCatch falls back to a bare PNG if the
# skill helper is unavailable or errors.
fig_dir <- file.path(reports_dir, "figures")
dir.create(fig_dir, showWarnings = FALSE, recursive = TRUE)
standalone <- list(lod50 = pB1, precision_recall = pB2, confusion_matrix = pA1)
for (nm in names(standalone)) {
  p <- standalone[[nm]] + theme_lab()
  if (exists("save_figure")) {
    # nature_double (183 mm) — these are 2-3 panel figures; nature_single (89 mm)
    # is too cramped for the facets and tile text.
    tryCatch(save_figure(p, file.path(fig_dir, nm), size = "nature_double"),
             error = function(e) ggplot2::ggsave(file.path(fig_dir, paste0(nm, ".png")),
                                                 p, width = 9, height = 6, dpi = 300))
  } else {
    ggplot2::ggsave(file.path(fig_dir, paste0(nm, ".png")), p, width = 9, height = 6, dpi = 300)
  }
}
