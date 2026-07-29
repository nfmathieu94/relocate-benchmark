# Multi-dataset benchmark integration

Date/time: 2026-07-28T09:30:42-07:00  
Status: implemented; lightweight validation and automated tests pass; no
benchmark jobs were submitted by this change.

## Purpose

Add the completed riceTElib multi-TE panel without mixing it with the existing
mPing benchmark. The benchmark can now select `mping`, `ricetelib`, or `full`,
score each dataset independently, and display each dataset independently in the
dashboard.

## External-data contract

The benchmark remains read-only with respect to simulation products. Dataset
tables in `config/benchmark.toml` point to the external
`make_simulation_new` project.

| Dataset key | Panel | Caller TE library | Reference-TE annotation |
| --- | --- | --- | --- |
| `mping` | `results/somatic_mping_panel_chr1` | `input/TE_lib/mping_superfam_header.fa` | mPing/Ping RepeatMasker `.out` |
| `ricetelib` | `results/riceTElib_benchmark` | the panel's exact `selected_te_library.fa` | a cached `.out` converted from the genome-wide RepeatMasker GFF |

Both panels expose the same `panel_manifest.tsv` sample contract: 5x, 15x, and
30x coverage, each with three replicates. Both use the same biological states
and somatic allele frequencies. Their sample names intentionally overlap, so
dataset identity is a required path component.

The riceTElib truth additionally contains `te_group`, `te_class`, `te_order`,
`te_superfamily`, and `library_classification`. Scoring carries the first four
fields into count-backed summary rows. Legacy truth receives
`te_group = te_family`, leaving the other taxonomy fields blank.

Before submission, each configured TE library is copied byte-for-byte to
`cache/te_libraries/<dataset>/library.fa`. RelocaTE index sidecars are built
beside that staged copy. This is necessary because the callers derive index
paths from the library path; staging prevents them from writing into either
external simulation panel. If the source FASTA changes, submission replaces
the staged copy and deletes only its cache-owned index sidecars so every needed
index is rebuilt against the new bytes.

The shared reference remains external. Submission requires its existing
samtools (`.fai`), minimap2 (`.mmi`), and complete BWA index set and refuses to
launch if any is missing; array tasks never build indexes beside the external
reference.

## Selection and task identity

`pipeline/submit_benchmark.sh` accepts:

```bash
bash pipeline/submit_benchmark.sh --dataset mping
bash pipeline/submit_benchmark.sh --dataset ricetelib
bash pipeline/submit_benchmark.sh --dataset full
```

An omitted `--dataset` uses `[benchmark].default_dataset`. `full` expands to
every enabled `[datasets.<key>]` table. Existing caller, coverage, sample, and
replicate filters operate after dataset expansion.

Canonical array order is:

1. dataset key, sorted;
2. enabled caller key, sorted;
3. panel-manifest order.

The submission script passes the explicit selection to both array and
aggregation jobs. This prevents a config default or shell environment from
changing the array-index mapping after submission.

## Isolated output layout

```text
truth/<dataset>/
runs/<dataset>/<caller>/<sample>/
reports/datasets/<dataset>/per_sample/<caller>/<sample>/
reports/datasets/<dataset>/resources/<caller>/
reports/datasets/<dataset>/{correctness,precision,head_to_head,resources}.tsv
reports/datasets/<dataset>/benchmark_report.pdf
reports/datasets.tsv
```

Aggregation loops over selected datasets and invokes the existing combiner,
caller comparison, and R report independently for each. `reports/datasets.tsv`
indexes every complete dataset report already present, not only the most recent
selection. Thus rerunning riceTElib does not remove a completed mPing dataset
from the dashboard.

Precision remains a global per-sample measure. It is not assigned to individual
TE groups because unmatched calls do not always have an unambiguous truth-group
denominator. Recall, status accuracy among detections, and exact-TSD accuracy
among detections are safely stratified by TE group using event counts.

## Reference-TE annotation choice

The available small `.out` is mPing/Ping-focused and is unsuitable for the
multi-TE library. A genome-wide RepeatMasker GFF exists, but RelocaTE2 selects a
legacy parser based on the filename and expects fixed `.out` token positions;
RelocaTE3 accepts either `.out` or BED.

`pipeline/gff_to_repeatmasker_out.py` therefore converts the genome-wide GFF to
one deterministic, atomic cached `.out` used by both callers. Submission
regenerates it explicitly so an external GFF update cannot leave a silent stale
cache. It preserves
chromosome, 1-based inclusive boundaries, strand, repeat name, class, alignment
score, divergence/deletion/insertion percentages, and source record ID. The
converter produced 256,637 records with 15 fields per data row during
validation. The cache is regenerable and gitignored.

## Dashboard and figures

The dashboard reads `reports/datasets.tsv`. A benchmark-dataset selector is
shown before the ordinary filters, and every page receives exactly one
`ReportBundle`; metrics from different datasets are never concatenated.
Legacy copied report directories without a manifest still load as one dataset.

The existing Overview, Accuracy, Somatic, Resources, and Provenance pages work
unchanged for either selected dataset. The new **TE groups** page provides:

- coverage curves faceted by curated TE group;
- a caller-by-group heatmap across selected coverages;
- filters for TE group, class, order, and superfamily when those fields exist.

The per-dataset PDF adds a TE-group recall page and standalone TE-group figure
when more than one group is present.

## TSD design provenance

The benchmark does not replace the simulation truth TSDs; it passes
`tsd = "UNK"` to RelocaTE3 so TSD length and sequence are inferred from
junction reads, and evaluates exact agreement with each event's truth.

The simulation design and complete literature rationale are recorded in:

`/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/docs/2026-07-27-riceTElib-benchmark-workflow.md`

The main modeled rules are 5 bp for LTR/Copia and LTR/Gypsy, variable 7–20 bp
for LINE/SINE, `TWA` for PIF/Harbinger, `TA` for Tc1/Mariner, 9 bp for MULE,
8 bp for hAT, 3 bp for CACTA, and no TSD at an `A|T` target for Helitron.
Supporting literature includes McCarthy et al. (2002,
<https://pmc.ncbi.nlm.nih.gov/articles/PMC134482/>), Rangwala and Richards
(2010, <https://link.springer.com/article/10.1186/1759-8753-1-10>), Zhang et
al. (2004, <https://pmc.ncbi.nlm.nih.gov/articles/PMC1470744/>), Zhao et al.
(2015, <https://pmc.ncbi.nlm.nih.gov/articles/PMC4330571/>), and Kapitonov and
Jurka (2001, <https://pmc.ncbi.nlm.nih.gov/articles/PMC37501/>). These are
benchmark assumptions with documented approximations, not claims of invariant
TSD behavior across every family.

## Validation commands and results

```bash
python3.12 -m py_compile \
  pipeline/config_env.py pipeline/gff_to_repeatmasker_out.py \
  scoring/score_calls.py scoring/compare_callers.py scoring/combine_reports.py

bash -n \
  pipeline/submit_benchmark.sh \
  pipeline/run_benchmark_array.sh \
  pipeline/aggregate.sh

python3.12 pipeline/config_env.py \
  --config config/benchmark.toml --dataset full count

pixi run --manifest-path env/benchmark/pixi.toml \
  python3 -m unittest discover -s tests -p 'test_*.py'
```

The full selection resolves to 108 tasks: 2 datasets × 6 callers × 9 samples.
The final pinned-environment run passed all 92 tests, including the focused
multi-dataset, taxonomy, suite-loader, GFF-conversion, and Streamlit page tests.
The real 500-event riceTElib truth contract produced 50 summary rows spanning
all 10 TE groups, 3 biological-class labels (with somatic cellular fractions
kept separate), and a summed truth denominator of 500.

## Failures and cautions

- A bare system Python test run cannot import dashboard dependencies such as
  pandas. The repository's pinned benchmark Pixi environment is the supported
  test environment and passed.
- In this restricted session the Pixi wrapper remained resident after unittest
  printed its successful final summary, so it was interrupted after the
  `Ran 92 tests ... OK` result. The tests themselves and Streamlit AppTest page
  rendering completed.
- No caller workload was run on the login node, and no SLURM job was submitted
  during implementation.
- Existing root-level mPing reports are a legacy layout and were not moved or
  overwritten. New runs use dataset-qualified paths.
- A `.complete` truth sentinel currently indicates successful export but does
  not checksum the external panel. Use `scoring/export_truth.py --force` after
  deliberately replacing a panel, or move the dataset truth directory aside.

## Next steps

1. Submit `--dataset ricetelib` and monitor the array and dependent aggregation
   job.
2. Review per-group truth counts, detection recall, and exact-TSD accuracy,
   especially LINE/SINE and zero-TSD Helitron events.
3. Launch the dashboard and compare the mPing and riceTElib selections.
4. Consider adding panel hashes to truth completion metadata before external
   datasets are routinely revised in place.

## First riceTElib runtime failure

Date/time: 2026-07-28T18:46:36-07:00  
Status: diagnosed; fixes and cleanup not yet applied.

The first riceTElib submission created array job `26803795` and dependent
aggregation job `26803796`. Aggregation entered
`DependencyNeverSatisfied` because all nine RelocaTE2 tasks failed. All 45
RelocaTE3 tasks completed and produced complete per-sample reports, so they do
not need to be rerun.

Two independent RelocaTE2 failures were identified:

1. Five tasks that completed BAM sorting failed in RelocaTE2's
   `existingTE_RM_ALL` parser with
   `ValueError: invalid literal for int() with base 10: '(0)'`. The GFF
   converter emitted forward-style repeat-coordinate fields for reverse
   (`C`) records. Legacy RepeatMasker `.out` requires reverse records to order
   those fields as `(left), repeat_end, repeat_begin`.
2. Four tasks failed during old samtools sorting. Every array task sorting from
   standard input used the same implicit `STDIN.tmp.*.bam` prefix in the shared
   project working directory. Concurrent tasks truncated or removed one
   another's files. The RelocaTE2 adapter needs a task-specific `samtools sort
   -T` prefix under its own BAM directory.

The failed RelocaTE2 run tree occupies approximately 132 GB, and 32 orphaned
root-level `STDIN.tmp.*.bam` files occupy approximately 4.4 GB. They were
inspected but not moved or deleted. Recovery should:

1. correct and test reverse-strand RepeatMasker conversion;
2. give RelocaTE2 samtools a sample-specific temporary prefix;
3. cancel the unsatisfiable aggregation job;
4. move or remove the nine incomplete RelocaTE2 run directories and orphaned
   sort files;
5. resubmit only `--dataset ricetelib --caller relocate2`, allowing its new
   dependent aggregation job to combine those results with the 45 preserved
   RelocaTE3 reports.
