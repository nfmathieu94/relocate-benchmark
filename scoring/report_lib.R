# Shared helpers for the RelocaTE benchmark report. Sourced by make_report.R
# and by tests/smoke_report.R so both share ONE copy of the styling header,
# TSV reader, and small stats helpers.

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(tidyr)
  library(scales)
  library(patchwork)
})

# ---- lab styling helpers -------------------------------------------------
skill_dir <- "~/.claude/skills/ggplot-figures"
for (f in c("theme_lab.R", "palettes.R", "figure_sizes.R", "save_figure.R")) {
  src <- file.path(skill_dir, "R", f)
  if (file.exists(src)) source(src)
}
if (!exists("theme_lab")) theme_lab <- function(...) theme_gray()
if (!exists("scale_color_lab")) scale_color_lab <- function(...) scale_colour_hue()
if (!exists("scale_fill_lab")) scale_fill_lab <- function(...) scale_fill_hue()

read_tsv <- function(p) read.delim(p, sep = "\t", stringsAsFactors = FALSE, check.names = FALSE)

# Pretty caller labels (relocate2 -> RelocaTE2) without hardcoding the set.
pretty_caller <- function(x) {
  ifelse(grepl("^relocate", x, ignore.case = TRUE),
         sub("relocate", "RelocaTE", x, ignore.case = TRUE), x)
}
class_levels <- c("homozygous", "heterozygous", "somatic_insertion")
class_labs <- c(homozygous = "Homozygous", heterozygous = "Heterozygous",
                somatic_insertion = "Somatic")

sem <- function(x) if (length(x) > 1) sd(x) / sqrt(length(x)) else 0

# Common line-with-SEM geom builder.
line_sem <- function(df, y) {
  ggplot(df, aes(coverage, mean, colour = caller, group = caller)) +
    geom_errorbar(aes(ymin = mean - se, ymax = mean + se), width = 1.2,
                  linewidth = 0.4, alpha = 0.8) +
    geom_line(linewidth = 0.9) +
    geom_point(size = 2.1) +
    scale_color_lab() +
    scale_x_continuous(breaks = sort(unique(df$coverage))) +
    labs(colour = NULL)
}

# ---- per-event data loader -----------------------------------------------
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
    sample <- rel[length(rel) - 1]
    cov    <- as.integer(sub(".*cov([0-9]+)x.*", "\\1", sample))
    rep    <- as.integer(sub(".*rep([0-9]+).*", "\\1", sample))
    d$caller <- pretty_caller(caller); d$sample <- sample
    d$coverage <- cov; d$replicate <- rep
    d
  })
  dplyr::bind_rows(parts)
}

load_truth <- function(path = "truth/truth.tsv") read_tsv(path)

# ---- plot builders -------------------------------------------------------
# A1: genotype / detection confusion matrix (row-normalised per truth class).
plot_confusion <- function(matches) {
  df <- matches %>%
    dplyr::mutate(
      truth_class = factor(biological_class, levels = class_levels),
      called = ifelse(matched == 0 | is.na(call_status) | call_status == "",
                      "missed", call_status)) %>%
    dplyr::filter(!is.na(truth_class))
  # Data-driven called-status axis: every status present, "missed" forced last.
  lvls <- c(sort(setdiff(unique(df$called), "missed")), "missed")
  df <- df %>%
    dplyr::mutate(called = factor(called, levels = lvls)) %>%
    dplyr::count(caller, truth_class, called, name = "n", .drop = FALSE) %>%
    dplyr::group_by(caller, truth_class) %>%
    dplyr::mutate(row_frac = if (sum(n) > 0) n / sum(n) else 0) %>% dplyr::ungroup()
  # Readable labels for known statuses; fall back to raw value otherwise.
  status_lab <- c(homozygous = "Hom", heterozygous = "Het",
                  `homozygous/excision_no_footprint` = "Hom (excision)",
                  somatic_insertion = "Somatic", missed = "Missed")
  labs_vec <- ifelse(lvls %in% names(status_lab), status_lab[lvls], lvls)
  ggplot(df, aes(called, truth_class, fill = row_frac)) +
    geom_tile(colour = "white", linewidth = 0.5) +
    geom_text(aes(label = sprintf("%d\n%.0f%%", n, 100 * row_frac)), size = 3) +
    facet_wrap(~caller) +
    scale_fill_gradient(low = "#F7FBFF", high = "#08519C", labels = scales::percent,
                        limits = c(0, 1), name = "Row %") +
    scale_x_discrete(labels = labs_vec) +
    scale_y_discrete(labels = class_labs) +
    labs(title = "Genotype / detection confusion",
         subtitle = "Row-normalised: where each truth class's events land (pooled over coverage)",
         x = "Called status", y = "Truth class") +
    theme(axis.text.x = element_text(angle = 20, hjust = 1))
}

# A2: breakpoint positional accuracy ECDF (matched events, per coverage).
plot_breakpoint <- function(matches) {
  df <- matches %>%
    dplyr::filter(matched == 1, !is.na(distance_bp)) %>%
    dplyr::mutate(distance_bp = as.numeric(distance_bp),
                  coverage = factor(paste0(coverage, "x"),
                                    levels = paste0(sort(unique(coverage)), "x")))
  ggplot(df, aes(distance_bp, colour = caller)) +
    stat_ecdf(linewidth = 0.9) + facet_wrap(~coverage) +
    scale_color_lab() +
    coord_cartesian(xlim = c(0, 20)) +
    scale_y_continuous(labels = scales::percent) +
    labs(title = "Breakpoint positional accuracy",
         subtitle = "ECDF of |called - true| position for matched events; steeper/left = better",
         x = "Distance to true position (bp)", y = "Cumulative fraction of calls",
         colour = NULL)
}

# A3: per-event caller agreement bar (which caller(s) detected each truth event).
# Filter blank event_id so the "Neither" bucket counts only genuine truth events.
plot_intersection <- function(matches) {
  callers <- sort(unique(matches$caller))
  det <- matches %>%
    dplyr::filter(event_id != "") %>%
    dplyr::group_by(sample, event_id, caller) %>%
    dplyr::summarise(hit = as.integer(any(matched == 1)), .groups = "drop") %>%
    tidyr::pivot_wider(names_from = caller, values_from = hit, values_fill = 0)
  callers <- intersect(callers, names(det))               # only materialized caller columns
  hits  <- as.matrix(det[, callers, drop = FALSE]) == 1   # logical matrix, no char coercion
  n_hit <- rowSums(hits)
  label_row <- function(i) {
    if (n_hit[i] == 0) return("Neither")
    if (n_hit[i] == length(callers)) return("Both")
    paste0(paste(callers[hits[i, ]], collapse = "+"), "-only")
  }
  det$set <- vapply(seq_len(nrow(det)), label_row, character(1))
  df <- det %>% dplyr::count(set, name = "n") %>%
    dplyr::mutate(set = forcats::fct_reorder(set, n))
  ggplot(df, aes(set, n, fill = set)) +
    geom_col(width = 0.7, show.legend = FALSE) +
    geom_text(aes(label = n), hjust = -0.15, size = 3.4) +
    coord_flip() +
    scale_y_continuous(expand = expansion(mult = c(0, 0.12))) +
    labs(title = "Per-event caller agreement",
         subtitle = "Truth events by which caller(s) detected them (pooled over all samples)",
         x = NULL, y = "Truth events")
}

# A4: missed-event profile - detection recall stratified by strand and TSD.
plot_missed_profile <- function(matches) {
  df <- matches %>%
    dplyr::mutate(
      ambiguous_tsd = dplyr::case_when(is.na(tsd) | tsd == "" ~ "Unknown TSD",
                                       grepl("^N+$", tsd) ~ "Ambiguous TSD (N)",
                                       TRUE ~ "Defined TSD"),
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
    scale_fill_lab() +
    scale_y_continuous(limits = c(0, 1), labels = scales::percent) +
    labs(title = "What do missed events have in common?",
         subtitle = "Detection recall stratified by strand and TSD ambiguity (pooled)",
         x = NULL, y = "Detection recall", fill = NULL)
}

# B1: detection recall vs expected VAF with per-group logistic fit (LOD50).
# Pools hom/het/somatic onto a single expected-VAF axis; fits recall ~ log10(vaf)
# per caller x coverage; the VAF at 50% recall is the limit of detection.
plot_lod <- function(matches) {
  pts <- matches %>%
    dplyr::mutate(vaf = as.numeric(expected_vaf)) %>%
    dplyr::group_by(caller, coverage, vaf) %>%
    dplyr::summarise(recall = mean(matched == 1), n = dplyr::n(), .groups = "drop")
  fit_one <- function(d) {
    d <- d[d$n > 0, ]
    if (dplyr::n_distinct(d$vaf) < 3 || all(d$recall %in% c(0, 1))) return(NULL)
    m <- tryCatch(glm(recall ~ log10(vaf), weights = n, family = binomial, data = d),
                  error = function(e) NULL)
    if (is.null(m)) return(NULL)
    grid <- data.frame(vaf = 10^seq(log10(min(d$vaf)), log10(max(d$vaf)), length.out = 60))
    grid$recall <- predict(m, grid, type = "response")
    grid
  }
  curves <- pts %>% dplyr::group_by(caller, coverage) %>%
    dplyr::group_modify(~ {
      g <- fit_one(.x)
      if (is.null(g)) g <- .x[0, c("vaf", "recall")]
      g
    }) %>% dplyr::ungroup()
  ggplot(pts, aes(vaf, recall, colour = caller)) +
    geom_line(data = curves, aes(vaf, recall), linewidth = 0.9) +
    geom_point(aes(size = n), alpha = 0.8) +
    facet_wrap(~ paste0(coverage, "x")) +
    scale_color_lab() + scale_size_continuous(guide = "none") +
    scale_x_log10() + scale_y_continuous(limits = c(0, 1), labels = scales::percent) +
    labs(title = "Detection sensitivity vs variant allele frequency",
         subtitle = "Logistic fit per caller; VAF at 50% detection = limit of detection (LOD50)",
         x = "Expected VAF (log scale)", y = "Detection recall", colour = NULL)
}
