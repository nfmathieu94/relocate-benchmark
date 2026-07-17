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
