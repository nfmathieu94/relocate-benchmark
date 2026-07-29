# Benchmark issue audit for future investigation

Date/time: 2026-07-27 America/Los_Angeles

## Purpose

Record issues and interpretation caveats identified while tracing the simulated
mPing panel into the `relocate-benchmark` workflow. These items are documented
for a later, focused investigation. They are not the primary focus of the
current work, and no implementation changes were made as part of this audit.

## Status

- Documentation only.
- The active benchmark has 45 completed caller/sample runs: five caller
  configurations across nine simulated samples.
- The benchmark's exported `truth/truth.tsv` and `truth/samples.tsv` were
  verified to be byte-identical to the active Chr1 panel's source files.
- Existing generated report modifications in the benchmark working tree were
  left untouched.

## 1. Simulation regeneration entry points are stale after reorganization

### Evidence

The simulation project currently stores the submission and worker scripts
under:

```text
pipeline/make_mping_benchmark/
```

However:

- simulation documentation still gives:

  ```bash
  bash pipeline/submit_somatic_panel_chr1.sh
  ```

- `pipeline/make_mping_benchmark/submit_somatic_panel_chr1.sh` submits:

  ```text
  pipeline/05_make_somatic_te_catalog.sh
  pipeline/06_simulate_somatic_panel_reads.sh
  ```

- those two root-level paths do not currently exist; the files are under
  `pipeline/make_mping_benchmark/`.

### Impact

The completed data remain usable, but the documented regeneration command is
not currently rerunnable from the simulation project root. This weakens the
reproducibility guarantee if the panel needs to be rebuilt.

### Future checks

1. Decide whether `pipeline/make_mping_benchmark/` is the permanent layout.
2. Update submission helpers and documentation to use the same paths.
3. Run `bash -n` on all affected scripts.
4. Perform a lightweight submission-path validation without launching the
   computational jobs.

## 2. Reference-only controls are generated but not benchmarked

### Evidence

Each row of `panel_manifest.tsv` contains:

```text
control_r1
control_r2
```

The task construction in `pipeline/config_env.py` reads only `r1` and `r2`.
No active caller adapter or scoring step consumes `control_r1` or `control_r2`.

### Impact

Current precision measures unmatched calls in insertion-bearing samples. It
does not directly measure caller behavior on matched samples with no simulated
non-reference insertions. Therefore, the generated controls are not currently
providing a dedicated negative-control specificity or false-positive test.

### Future checks

1. Decide whether controls should be separate canonical benchmark tasks.
2. Define the expected truth contract for a control sample: zero non-reference
   insertions, or reference insertions only.
3. Report calls per control genome and false positives per genome or per
   callable megabase.
4. Keep control metrics separate from insertion-bearing sample precision.

## 3. ART-origin `observed_vaf` is a junction-support ratio, not literal VAF

### Evidence

The simulator's `_count_origin_support` function counts:

- reads spanning either of the two insertion junctions for an insertion-bearing
  haplotype; and
- reads spanning one reference coordinate for an insertion-absent haplotype.

The resulting value is written as `observed_vaf` in `observed_support.tsv`.
Examples from `cov15x_rep1` include:

```text
expected VAF 0.50 -> mean observed value approximately 0.68
expected VAF 0.20 -> mean observed value approximately 0.34
expected VAF 0.10 -> mean observed value approximately 0.17
expected VAF 0.05 -> mean observed value approximately 0.10
```

The upward shift is consistent with providing insertion-bearing reads two
junction opportunities while reference reads have one spanning opportunity.

### Impact

The field is useful as ART-origin junction-support QC, but it should not be
interpreted as an unbiased allele-frequency estimate or used directly to
validate the configured expected VAF.

### Future checks

1. Consider renaming the field to `observed_junction_support_fraction`.
2. If literal VAF QC is required, define one comparable opportunity per allele
   or calculate molecule-level support.
3. Document the expected transformation between allele fraction and the
   current junction-support statistic.

## 4. One truth event has an ambiguous all-N TSD

### Evidence

The active Chr1 panel contains one event at:

```text
Chr1:550
```

with:

```text
TSD = NNNNN
```

The TSD was taken from an ambiguous region of the reference genome.

### Impact

Detection and status evaluation may remain valid, but exact-TSD accuracy for
this event is not a meaningful test of sequence recovery.

### Future checks

1. Decide whether catalog generation should reject insertion anchors whose TSD
   contains non-ACGT bases.
2. Alternatively, retain the event but mark exact-TSD scoring as not applicable.
3. Quantify whether any other truth or callable flanking sequence contains
   ambiguous bases.

## 5. Documentation does not fully match the active benchmark

### Evidence

Several statements describe older configurations:

- parts of `README.md` describe two callers and 18 tasks, while the active
  configuration enables five callers and produces 45 tasks;
- the README's known-limitation section describes fixed three-base `...` TSDs,
  while all active RelocaTE3 configurations now use `tsd = "UNK"`;
- `docs/data_provenance.md` lists heterozygous cellular fraction as 0.5, while
  the actual truth correctly records cellular fraction 1.0 and expected VAF
  0.5;
- the provenance regeneration command points to the stale simulation script
  path described in issue 1.

### Impact

These inconsistencies can cause incorrect interpretation of task counts,
zygosity, TSD results, and regeneration procedures.

### Future checks

1. Derive current task counts from configuration rather than embedding a count
   in prose.
2. Update TSD documentation to distinguish historical fixed-TSD runs from
   current variable-length inference.
3. Correct the heterozygous cellular-fraction row.
4. Update data-regeneration paths after the simulation layout is finalized.

## 6. The simulation workspace contains a superseded local benchmark

### Evidence

The simulation project contains `relocate3_benchmark/`, an older harness that:

- uses the three-chromosome panel;
- runs RelocaTE3 only;
- uses fixed `TSD_PATTERN="..."`; and
- has different normalization and reporting behavior.

The active multi-caller harness is this standalone `relocate-benchmark`
repository and uses the Chr1 panel.

### Impact

The two harnesses can be mistaken for equivalent benchmark implementations or
their reports can be compared without accounting for different datasets,
callers, TSD handling, and scoring code.

### Future checks

1. Mark the simulation-local harness explicitly as archived or superseded.
2. Link from it to this active repository.
3. Avoid reusing its reports as current benchmark results.

## 7. Completed-run sentinels can retain results across configuration changes

### Evidence

Caller adapters skip raw execution when `.run_complete` exists. Scoring can be
rerun, but changing a caller's aligner, TSD mode, thresholds, or code does not
invalidate an existing raw-run sentinel automatically.

This behavior is already noted in the variable-length TSD development
documentation, which required deliberate regeneration after changing
`TSD_PATTERN`.

### Impact

A submission made after a configuration or implementation change can silently
reuse older raw calls unless the operator uses a new work root or deliberately
archives or removes the applicable completed run directories.

### Future checks

1. Store a run fingerprint containing input checksums, caller revision, adapter
   revision, and relevant parameters.
2. Compare the fingerprint before honoring `.run_complete`.
3. Prefer a new versioned work root for materially different benchmark runs.

## 8. Generated report files currently have pre-existing uncommitted changes

### Evidence

At the time of this audit, `git status --short` reported modifications to:

```text
reports/benchmark_report.pdf
reports/correctness.tsv
reports/head_to_head.tsv
reports/precision.tsv
reports/resources.tsv
```

No source-code changes were observed in that status check, and the existing
report changes were not modified or reverted during the audit.

### Impact

Future work should first determine whether these reports are intended outputs
from the latest completed 45-task run before committing, regenerating, or
replacing them.

### Future checks

1. Associate the report set with the SLURM job IDs and caller revisions that
   produced it.
2. Review the report diff before any cleanup.
3. Avoid mixing reports from different raw-run generations.

## Commands used for this audit

Representative read-only checks included:

```bash
find runs -name .run_complete -type f
find reports/per_sample -name .complete -type f
find reports/resources -name '*.time-v.txt' -type f
sha256sum truth/truth.tsv truth/samples.tsv
rg 'control_r1|control_r2|reference_control'
git status --short
```

The source truth and manifest were compared with:

```text
/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/
make_simulation_new/results/somatic_mping_panel_chr1/
```

## Recommended next step

Treat these items as a future audit backlog. When work resumes, start with the
regeneration-path issue because it affects reproducibility, then decide whether
negative-control benchmarking and literal VAF validation are desired benchmark
requirements before changing scoring or reports.
