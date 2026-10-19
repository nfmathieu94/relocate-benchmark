# Recover the six incomplete checkpoint baselines

Completion follow-up, 2026-10-18 12:41 PDT: recovery array **30041652** and
finalizer **30041653** succeeded. All six outputs were validated and promoted;
aggregation completed October 17 at 12:37:52 PDT. Accuracy reports now cover
all 432 caller/sample combinations; full-pipeline resource rows intentionally
exclude the six recovered R2 samples (426 rows total). Both R2 and R3
BLAT/bwa-aln normalized calls reproduce their validated historical counterparts
in 72/72 samples. See the
[updated assessment](../../../RelocaTE3_jason/RelocaTE3/docs/2026-10-18-recovered-full-benchmark.md).
The setup/submission history below is retained as originally recorded.

Recorded: 2026-10-16 20:47 PDT, America/Los_Angeles.
Benchmark branch: `main`; RelocaTE3 `main`, revision `213a0df`, after PR #54.
Status: implementation and lightweight validation complete; **no jobs submitted**.

The R2 adapter now creates `raw/repeat/results` before parallel workers start,
captures the driver log, rejects Python worker tracebacks, and verifies the
expected non-reference and reference output files for every generated worker.
Existing completion sentinels are also validated before skipping a run.
Empty chromosome files and a header-only final table remain valid when all
workers produced their expected outputs; zero detected insertions alone is
not a failure. R2 scientific algorithms and all R3 source files are unchanged.

The recovery runs all chromosome insertion/absence workers and characterization
for these six samples using the existing BAMs, indexes, and read-family tables:

| Recovery index | Panel | Sample | Original array index |
|---|---|---|---:|
| 0 | mPing | cov30x_rep2 | 7 |
| 1 | mPing | cov30x_rep3 | 8 |
| 2 | riceTElib | cov15x_rep1 | 57 |
| 3 | riceTElib | cov15x_rep3 | 59 |
| 4 | ricetelib_divergence | div010_rep02_cov5x | 138 |
| 5 | ricetelib_divergence | div010_rep03_cov5x | 141 |

Recovered runs are isolated under `runs/checkpoint-213a0df-r2-recovery/`.
Cached alignments are linked, small mutable inputs copied, and results
directories created before workers start. Each worker is executed directly
in the existing R2 container with checked exit status and a separate log.
The original generated commands supply the parameters. Non-reference/ref
tables are concatenated in filename order as in the old step-7 script,
followed by the same cleaner and characterizer. No BLAT or genome realignment
is performed. Eight workers per task respect the SLURM CPU allocation.

The dependent finalizer checks all six `.complete` markers, all expected
chromosome outputs, and 500 truth records per recovered report before any
promotion. It archives the entire existing checkpoint report tree plus the
six original result directories, normalized calls, sentinels, per-sample
reports, and resource rows under
`runs/checkpoint-213a0df-r2-recovery/original-results/`.
It then installs the recovered results and runs the existing aggregation.
Original alignments and all R3 run outputs stay in place. Prior figures and
reports are recoverable from that archive after aggregation refreshes them.

The six invalid original full-pipeline resource rows are archived, not used
in the refreshed resource tables. R2 resource summaries will consequently
have 66 valid full runs, while accuracy returns to 72 samples. New recovery
timings are saved separately in `logs/r2-recovery-resource.<array>_<task>.txt`;
they must not be presented as full-pipeline runtimes. Subsequent paired
resource analysis must match samples and exclude these six from both tools.
The prior accuracy-audit script's assumption of 72 resource rows per caller
will need adjustment when interpreting these deliberately separate cohorts.

The source guard was deliberately refreshed for the R2 adapter and five new
runtime files. Its original manifest is preserved as
`config/checkpoint-213a0df.pre-r2-recovery.source.json`. R3 source hashes,
scientific parameters, scoring, and reference settings remain unchanged.
Do not edit guarded scripts or change R3 HEAD while recovery runs.

## Validation and submission

Eleven focused tests pass, covering missing chromosome outputs, valid zero-call
runs, swallowed worker tracebacks, duplicate/absent worker manifests,
all-task validation before promotion, backup preservation/idempotence,
worker exit propagation, and refusal to run heavy recovery on a login node.
Shell syntax, Ruff formatting/lint, and source guards pass. Preflight confirms
the six cached datasets have BAM indexes and 12 worker commands per step.
The real incomplete mPing run is rejected and a complete mPing run accepted.
Container execution could not be smoke-tested in this managed session:
module loading encountered `/dev/log` restrictions and did not expose
`apptainer`. The job uses the existing R2 adapter environment on compute nodes.

Submission was attempted but stopped at the live partition lookup: `scontrol`
timed out before any `sbatch` invocation. There is no numeric job ID or
submission receipt. The wrapper checks that epyc permits the requested eight
hours before submission (the previously recorded maximum was 30 days).

From the **relocate-benchmark root**, run:

```bash
bash scripts/submit_r2_recovery.sh
```

It submits six recovery tasks (8 CPUs, 64 GB, eight hours each) and an
`afterok` finalizer (2 CPUs, 8 GB, 30 minutes). Confirm it prints numeric
`array=` and `finalize=` IDs. These are recorded in
`logs/checkpoint-213a0df-r2-recovery.submission`. The receipt prevents accidental
duplicate submissions. If submission is unconfirmed or only the array was
submitted, inspect the receipt and scheduler before retrying.

No deletion is needed. Incomplete recovery directories and interrupted
promotion backups cause explicit failures rather than silent overwrites;
retain them for diagnosis. Completed recovery tasks skip safely on rerun.
Next action: submit the wrapper from the cluster terminal, then inspect all
six recovery logs and the finalization log before reassessing all 72 samples.
