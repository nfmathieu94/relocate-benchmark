# Checkpoint benchmark audit

Recorded: 2026-10-16, America/Los_Angeles, after 20:20 PDT.
Benchmark branch: `main`. RelocaTE3: `main`, `213a0df`, following merged PR #54.
Status: analysis complete; benchmark outputs and runtime scripts unchanged.

Aggregation 29932899 completed at 19:49:41 PDT on October 16. All 360 R3
recovery tasks (array 29932898) and 72 original R2 tasks (array 29610466) have
completion logs, run sentinels, report tables, and adapter exit status zero.
The pinned source/configuration verifier passes. However, six R2 tasks lack
chromosome output files, and two of those report zero calls because Chr1
insertion calling failed. The latter logs contain an R2 results-directory
creation race. A header-only characterized table passed the adapter check.

Affected R2 indices: **7, 8, 57, 59, 138, 141**. These correspond to
mping/cov30x_rep2, mping/cov30x_rep3, ricetelib/cov15x_rep1,
ricetelib/cov15x_rep3, ricetelib_divergence/div010_rep02_cov5x, and
ricetelib_divergence/div010_rep03_cov5x. Do not interpret their incomplete
results as valid accuracy or resource measurements.

The primary comparison excludes these same six samples from all callers.
RelocaTE3 BLAT/bwa-aln has slightly higher pooled recall/F1 in each panel,
but more multi-TE FPs and approximately threefold higher 30× multi-TE RSS.
It exactly reproduces the earlier validated normalized calls in all 72
samples. A universal no-performance-sacrifice release claim is not supported.

Full analysis, biological strata, aligner comparison, resource tables, and
reproduction commands are in
[the RelocaTE3 report](../../../RelocaTE3_jason/RelocaTE3/docs/2026-10-16-full-checkpoint-results.md).
Machine-readable tables and input hashes are under
`../../RelocaTE3_jason/RelocaTE3/results/full-checkpoint-analysis/2026-10-16-complete-chromosomes/`
relative to the benchmark root.

Next action: fix R2 directory-creation/preflight and internal-worker
validation in the benchmark, recover the six affected R2 samples while
preserving existing alignments/results, then regenerate aggregation. No fix,
submission, deletion, report replacement, or dashboard change was made here.
Unfiltered checkpoint reports still include the incomplete R2 results.
