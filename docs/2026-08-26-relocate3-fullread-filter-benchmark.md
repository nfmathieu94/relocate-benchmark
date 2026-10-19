# RelocaTE3 junction-full-read filter benchmark

Date: 2026-08-26 PDT

## Purpose

Evaluate RelocaTE3 after wiring RelocaTE2's full-read false-junction filter into
the staged benchmark path for `riceTElib/cov5x_rep1`.

## Status

Implementation and lightweight validation complete; submission pending. The
first Slurm attempt was not confirmed because `sbatch` returned no numeric job
ID and both controllers were reported down. Existing benchmark artifacts have
not been moved yet.

## Benchmark logic

- Retain the completed RelocaTE2 `cov5x_rep1` baseline.
- Archive the previous RelocaTE3 run and per-sample report before submission.
- Run only caller `relocate3-blat-bwaaln` for dataset `ricetelib`, sample
  `cov5x_rep1`.
- Require a numeric array job ID and dependent aggregation job ID.
- Confirm the new junction-only full-read BAM is generated with `bwa aln` and
  passed to `find-insertions` before the all-read characterization BAM is built.
- Compare calls, matched truth events, false positives, precision, recall, F1,
  call identity, step-4 parity, and filtered-candidate counts with the prior
  RelocaTE3 result and retained RelocaTE2 baseline.

## Commands

```bash
bash -n callers/relocate3/run.sh pipeline/submit_benchmark.sh \
  pipeline/run_benchmark_array.sh pipeline/aggregate.sh

env/benchmark/.pixi/envs/default/bin/python \
  -m unittest discover -s tests -q

scontrol ping

python3.12 pipeline/config_env.py --config config/benchmark.toml \
  --dataset ricetelib indices \
  --caller relocate3-blat-bwaaln --sample cov5x_rep1
```

Validation result: Bash syntax and `git diff --check` passed; all 112 benchmark
tests passed. The intended selection still resolves uniquely to array task 9.

## Failures

- Full-test submission hung without returning a job ID and was interrupted
  after 60 seconds. `scontrol ping` then reported the primary and backup Slurm
  controllers down. This is an unconfirmed submission, not a running job.

## Next step

Validate the implementation, archive the previous RelocaTE3 artifacts, submit
through `pipeline/submit_benchmark.sh`, and monitor both SLURM jobs to terminal
completion.
