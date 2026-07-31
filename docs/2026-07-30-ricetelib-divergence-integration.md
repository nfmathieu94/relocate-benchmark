# riceTElib divergence dataset integration

Created: 2026-07-30 09:00 PDT (America/Los_Angeles)

## Purpose

Integrate the completed riceTElib TE-divergence simulation panel into the
multi-dataset RelocaTE benchmark without changing the generated source data.

## Status

- dataset key: `ricetelib_divergence`
- source panel:
  `/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/results/riceTElib_div_benchmark`
- source completion sentinel is present
- 18 divergence/replicate scenarios, 54 mixed-read samples, and 9 shared
  reference controls were generated
- all 126 retained FASTQs are gzip-compressed; no plain FASTQs remain
- benchmark configuration, manifest normalization, row-specific truth export,
  compressed-input validation, and RelocaTE2 gzip staging are implemented

## Configuration

The `[datasets.ricetelib_divergence]` table in `config/benchmark.toml` uses:

- the MSU7 rice reference
- the full reference RepeatMasker annotation used by the canonical riceTElib
  benchmark
- `canonical_te_library.fa` as the caller library

The per-scenario `inserted_te_variants.fa` files are audit truth and must never
be supplied to a caller because doing so would remove the intended divergence
challenge.

## Manifest adaptation

The simulator manifest uses treatment-oriented columns:

- `dataset_id`
- `divergence_percent`
- `divergence_replicate`
- `truth_tsv`

The benchmark's older panels use `sample`, `replicate`, and one root-level
truth table. `lib/panel.py` normalizes both layouts. Divergence samples receive
unique names such as:

```text
div005_rep01_cov15x
```

Truth export writes the exact scenario truth used by each sample under:

```text
truth/ricetelib_divergence/per_sample/<sample>.tsv
```

This prevents samples at different divergence levels from being scored against
pooled or canonical-only truth.

## Compressed FASTQ handling

The submission wrapper checks every distinct read path before `sbatch`. It
requires the file to be non-empty and checks the gzip magic bytes for `.gz`
inputs without rereading the complete 267 GB panel.

RelocaTE3 receives the `.fastq.gz` paths directly. Its configured minimap2,
BWA, Bowtie2, and BLAT input paths support gzip data.

The RelocaTE2 adapter now stages compressed mates as
`<sample>_R1.fastq.gz` and `<sample>_R2.fastq.gz`. It no longer hides gzip
content behind misleading `.fastq` symlink names.

## Aggregation

The following conditions are retained in combined correctness, precision,
resource, and head-to-head reports when present:

- `dataset_id`
- `divergence_percent`
- `divergence_replicate`
- coverage and normalized replicate

The dashboard exposes a data-driven **TE divergence (%)** filter for datasets
that provide this field. Dataset reports remain isolated under
`reports/datasets/ricetelib_divergence/`.

## Commands

Run the complete divergence dataset:

```bash
bash pipeline/submit_benchmark.sh --dataset ricetelib_divergence
```

Run selected divergence levels:

```bash
bash pipeline/submit_benchmark.sh \
  --dataset ricetelib_divergence \
  --divergence 0,5,20
```

Include every enabled dataset:

```bash
bash pipeline/submit_benchmark.sh --dataset full
```

## Detailed simulation design

The authoritative description of how the panel was generated, including the
mutation model, biological mixture, replicate pairing, truth schema,
limitations, validation, and literature references, is:

```text
/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/docs/2026-07-28-riceTElib-divergence-benchmark.md
```

## Validation record

- all 99 benchmark repository unit tests passed in the pinned Pixi environment
- Bash syntax and Python compilation checks passed
- the real manifest normalized to 54 unique samples and 324 tasks across the
  six currently enabled callers
- a temporary truth export produced 54 per-sample tables and 9,000 combined
  event/scenario rows
- all 108 mixed-read FASTQs referenced by benchmark tasks are present,
  non-empty, and have gzip magic bytes
- the configured canonical library matches the original selected riceTElib
  library by SHA256
- all required reference indexes are present
- no caller or benchmark SLURM jobs were submitted during validation

## Next steps

1. Submit a small filtered caller/coverage/divergence smoke run before the full
   caller matrix.
2. Aggregate the completed dataset and inspect it through the
   `ricetelib_divergence` dashboard selection.
