# Full benchmark of RelocaTE3 checkpoint 213a0df

Recovery update: [2026-10-12 checkpoint recovery](2026-10-12-checkpoint-recovery.md)
records the private-adapter export bug, its correction, and R3-only rerun
commands. The initial array completed R2 but did not run R3 successfully.

Recorded: 2026-10-07 19:21 PDT, America/Los_Angeles.
RelocaTE3 source: `main`, revision `213a0df99af71a57fffad726138593b152fc9a77`,
after PRs #50–#54. Status: installed and verified; not submitted by this session.

Run from this benchmark repository root:

```bash
CONFIG=config/benchmark.checkpoint-213a0df.toml \
  bash pipeline/submit_benchmark.sh --dataset full
```

The profile resolves to 432 tasks: 72 samples across mPing, canonical riceTElib,
and diverged riceTElib, with RelocaTE2 plus five R3 aligner combinations.
Both tools use explicit TSD-interval scoring and the same 10-bp tolerance.
Existing GNU-time resource recording captures full adapter elapsed time and
maximum RSS. Automatic aggregation depends on successful array completion.

Fresh outputs are `runs/checkpoint-213a0df/` and
`reports/checkpoint-213a0df/`; historical results are preserved. No cleanup
or deletion is required. The existing dashboard has not been reconfigured.

The checkpoint R3 adapter sets and verifies its source import path. Guards
verify the Git revision, production/package files, active config/pipeline,
and adapter hashes before work and before the R3 completion sentinel. Keep
the RelocaTE3 checkout and guarded benchmark files unchanged during the run.
The guard pins source/settings, not every input FASTQ byte or tool binary.

Installation preserved existing original caller/default config/dashboard
changes. Replaced scorer/pipeline files were backed up under
`cache/checkpoint_setup/213a0df99af71a57fffad726138593b152fc9a77/`.
Shell syntax and configuration enumeration pass; 17 coordinate-policy tests
pass against the installed scorer. References, annotations, and existing
genome/TE indexes were checked during preparation. Resource requests remain
64 GB/eight CPUs/96 hours on epyc, below its cached 30-day maximum.

Submission should show array 0-431 and numeric array/aggregation job IDs.
Monitor with `squeue -u "$USER"`. After completion, compare all three panels,
low-frequency somatic detections, TE groups, runtime, and peak memory before
deciding on a release tag.
