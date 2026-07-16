# Data provenance — simulated Chr1 mPing panel

Date/time: 2026-07-15 America/Los_Angeles

## Purpose

Record where the simulated benchmark data lives and how it was generated. This
repo runs and scores callers; it does **not** generate data. The data lives
outside this repo and is referenced by config path
(`config/benchmark.toml` → `[dataset].panel_root`).

## Where the data lives

`panel_root` (OUTSIDE this repo):

```
/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/results/somatic_mping_panel_chr1
```

Contains per-sample reads, `truth_events.tsv`, `panel_manifest.tsv`, and
`run_metadata.json`. The benchmark never writes here — it only reads via config.

## How it was generated

Produced by `simulate-data te-benchmark-panel` in the separate
`make_simulation_new` project, config `somatic_mping_panel_chr1.toml`, seed 916.
The data-generation scripts intentionally live in that project, **not** in this
repo.

Regenerate (run from the `make_simulation_new` project root):

```bash
cd /bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new
bash pipeline/submit_somatic_panel_chr1.sh
```

## Truth composition

500 truth events total on Chr1: 100 per (class × cellular fraction).

| class         | cellular_fraction | expected_vaf | count |
|---------------|-------------------|--------------|-------|
| homozygous    | 1.0               | 1.0          | 100   |
| heterozygous  | 0.5               | 0.5          | 100   |
| somatic       | 0.1               | 0.05         | 100   |
| somatic       | 0.2               | 0.10         | 100   |
| somatic       | 0.4               | 0.20         | 100   |

Note: the somatic class spans three cellular fractions (0.1 / 0.2 / 0.4 →
expected VAF 0.05 / 0.10 / 0.20), 100 events each; homozygous and heterozygous
are 100 events each.

## Panel dimensions

- Chromosome: Chr1 only
- Coverage: 5x, 15x, 30x
- Replicates: 3
- Samples: 9 (coverage × replicate)
- Truth events: 500

## Input checksums (SHA256)

From `run_metadata.json`, so provenance is verifiable:

```
ref       95836fac1a16be27eca781aaf12431208d89a5d02ae6b7d79555072bdf7a5548  input/ref_genome/MSU_r7.fa
te        00639d36ab72ce62e6c27fa895e4e115b370900c21efa7c489c21ac99ea6585a  input/TE_lib/mping_superfam_header.fa
known_del 09e19789251f3925b67831b6d4b6fc0466f48e558ddef262f121150117568e7a  input/repeatmasker/MSU_r7.mping_harbinger.tevarsim.out
```

Paths are relative to the `make_simulation_new` project root.
