# Checkpoint array failure and recovery

Recorded: 2026-10-12 21:56 PDT, America/Los_Angeles.
RelocaTE3: `main`, scientific source revision `213a0df`, after merged PR #54.
Status: benchmark setup corrected and tested; no recovery jobs submitted here.

Array 29610466 produced 432 logs: 72 successful R2 task logs and 360 R3
failures. Aggregation 29610467 has an unsatisfiable `afterok` dependency.
All R2 run sentinels and per-sample precision/match tables are present. No R3
run directories exist, so no partial alignment outputs require cleanup.
SLURM accounting could not connect from this managed session; filesystem/log
evidence independently establishes these outcomes.

## Cause and correction

The private `callers/relocate3-checkpoint-213a0df` adapter was introduced to
guard the exact source revision. `pipeline/config_env.py` selected its export
map using the directory basename, which was no longer `relocate3`. Thus
`caller-env` returned an empty string, omitting RT3_REPO as well as both
stage aligners and other settings. Every R3 adapter stopped at its required
input check before creating its run directory. This was a setup bug, not a
scientific failure in the RelocaTE3 pipeline.

The checkpoint's five R3 tables now specify `adapter_type = "relocate3"`.
The bridge uses that explicit contract identifier, retaining basename fallback
for old configurations. Source-guard hashes for the changed bridge and profile
were refreshed intentionally. No scientific source, scoring policy, R2 adapter,
truth, or successful result changed.

Tests now cover complete setting export for private adapter directories across
all five aligner pairs. **43 tests and five subtests pass**, including existing
configuration behavior and coordinate policy. Live caller-env assertions match
every configured R3 source/aligner/TSD/junction value. The full source guard
passes. Selected recovery indices are 9–53, 63–107, and 162–431: 360 tasks.

The RelocaTE3-side preparation helper was also corrected to emit the explicit
contract. The original `-ready` bundle represents the earlier failed setup;
do not reinstall that old bundle over this corrected configuration. Recovery
uses the installed checkpoint profile directly.

## Recovery commands

From the relocate-benchmark root:

```bash
scancel 29610467
CONFIG=config/benchmark.checkpoint-213a0df.toml \
  bash pipeline/submit_benchmark.sh --dataset full \
  --caller relocate3-blat-bwa,relocate3-blat-bwaaln,relocate3-bowtie2-bwa,relocate3-bwa-bwa,relocate3-minimap2-minimap2
```

The first command cancels only the unusable aggregation job. The second
submits the 360 R3 tasks and a new aggregation job depending on their success.
Aggregation includes all six callers: the existing R2 results remain in the
same report root and need no rerun. A numeric new array/aggregation ID is
required to confirm submission. No output deletion is needed.

Keep the RelocaTE3 revision and guarded benchmark settings unchanged during
recovery. Preserve original failed logs for provenance. Results remain under
`runs/checkpoint-213a0df/` and `reports/checkpoint-213a0df/`.
