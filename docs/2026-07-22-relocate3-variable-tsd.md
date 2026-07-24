# 2026-07-22 — RelocaTE3 variable-length TSD benchmark wiring

**Purpose:** Remove the benchmark's fixed three-base TSD wildcard so RelocaTE3
reports the per-insertion TSD length and sequence, matching the RelocaTE2 `UNK`
mode behavior.

**Status:** Ready for a fresh SLURM benchmark run; existing RelocaTE3 results
were generated with `tsd = "..."` and must not be compared as variable-length
TSD calls.

**Changes:**

- Set every enabled/available RelocaTE3 caller's `tsd` config value to `UNK`.
- The adapter now activates the configured `RT3_REPO` development pixi
  environment, rather than the older frozen package revision.
- `find-insertions --tsd UNK` now dispatches to RelocaTE3's breakpoint/depth
  inference helpers and writes the legacy non-reference TXT format consumed by
  `characterize`.
- The adapter passes its resolved bcftools executable explicitly to
  `characterize`. The development pixi environment does not include bcftools;
  it first tries the HPCC module and otherwise uses the benchmark runtime copy.

**Validation commands:**

```bash
(cd ../../RelocaTE3_jason/RelocaTE3 && pixi run --manifest-path pixi.toml pytest \
  tests/insertions_test.py -k 'known_tsd_call or tsd_unknown_infers_variable_length_tsd')
python3.12 -m unittest tests/test_config_env.py
bash -n callers/relocate3/env.sh callers/relocate3/run.sh
```

**Next step:** Submit new RelocaTE3 jobs through `pipeline/submit_benchmark.sh`
(not on the login node), then aggregate and inspect exact-TSD accuracy. Existing
completed run directories require deliberate removal or a new work root because
the adapter's idempotency guard will otherwise skip them.

## Post-run integration failure and fix

The first full `UNK` benchmark completed all 27 RelocaTE3 tasks but scored zero
detected events. The variable-length path emitted `TE=NA` because genome-aligned
junction names include `:start|end:5|3`, while `read_repeat_name.txt` is keyed by
the original untagged read name. The TE-family lookup now strips that suffix
before lookup. RelocaTE3 outputs from that first run must be regenerated; rescoring
the existing normalized files is insufficient because they already contain
`te_family=NA`.

Archived per-sample reports were initially retained under `reports/per_sample`
with a `.pre-te-family-fix` suffix. The aggregator's caller wildcard also found
those directories, creating duplicate combined rows. Aggregation now verifies
that each row's caller matches its containing caller directory and skips renamed
archives, preventing stale and active reports from being combined.
