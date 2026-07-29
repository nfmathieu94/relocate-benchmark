# Interactive benchmark dashboard

Date/time: 2026-07-28 America/Los_Angeles

## Purpose

The dashboard is a local, interactive presentation layer for completed
RelocaTE benchmark runs. It complements `reports/benchmark_report.pdf`; it does
not execute callers, submit SLURM jobs, normalize calls, match events, or modify
benchmark reports.

## Inputs

The report root normally contains `datasets.tsv`, whose rows point to isolated
dataset report directories. Each selected dataset directory contains:

- `correctness.tsv` — class- and condition-stratified truth/detection counts,
  recall, status accuracy, TSD counts, and class call share.
- `precision.tsv` — authoritative per-sample precision, false-discovery rate,
  matched calls, and unmatched calls.
- `head_to_head.tsv` — N-caller recall and status-accuracy comparisons.
- `resources.tsv` — GNU `time -v` runtime and memory measurements.

The application validates required columns, numeric fields, empty files, and
expected unique keys before rendering. It reports malformed inputs without
silently changing them.

## Provision and launch

Provision the frozen environment once from the repository root:

```bash
bash pipeline/setup_envs.sh
```

Launch with the convenience wrapper:

```bash
bash pipeline/run_dashboard.sh
```

The equivalent direct Pixi command is:

```bash
pixi run --manifest-path env/benchmark/pixi.toml dashboard
```

Both commands default to `reports/`. A legacy copied directory containing four
tables directly is still supported. Open one with:
without moving files:

```bash
bash pipeline/run_dashboard.sh --report-dir results/history/run_2026_07_17
```

The `RELOCATE_REPORT_DIR` environment variable provides the same override; an
explicit `--report-dir` takes precedence.

Streamlit prints a local URL when it starts. On the HPCC, keep Streamlit bound
to the login host and use SSH port forwarding from the workstation, for example
with local port 8501 forwarded to the host's port 8501. The committed Streamlit
configuration binds to `127.0.0.1`, runs headlessly, and disables usage
telemetry by default. The dashboard itself is lightweight and read-only;
substantial benchmark analyses still belong in SLURM jobs.

## Pages

- **Overview** — active report directory, represented callers and conditions,
  and a small overall recall/precision comparison.
- **Accuracy** — recall, genotype-status accuracy, exact-TSD accuracy,
  precision, false-discovery rate, false-positive counts, and N-caller direct
  comparisons.
- **Somatic performance** — recall by cellular fraction, expected VAF, caller,
  and coverage.
- **TE groups** — recall, status accuracy, and exact-TSD accuracy by curated TE
  group, with taxonomy filters when present.
- **Computational resources** — mean wall time and peak RSS by caller and
  coverage.
- **Provenance** — dataset/configuration paths, enabled caller settings, report
  timestamps, metric definitions, and known limitations.

The dataset selector is shown when more than one complete dataset is indexed.
All pages and filters then operate on only that dataset. Sidebar filters are
populated from its reports. Reset them with **Reset filters**.

## Metric interpretation

- Detection recall is matched truth events divided by truth events.
- Genotype-status accuracy is correct status calls among detected events.
- Exact-TSD accuracy is `tsd_exact_events / detected_events`, using the
  authoritative counts already present in `correctness.tsv`.
- Overall precision and false-discovery rate come only from `precision.tsv`.
- `class_call_share` is a diagnostic fraction of all calls and is not precision.
- Resource comparisons are meaningful only for runs collected under the same
  standardized SLURM and software conditions.

RelocaTE3 is configured with `tsd = "UNK"` and infers variable TSD length and
sequence from junction reads. Exact-TSD results compare that call with each
event's truth.

## Troubleshooting

- **Missing file:** run `bash pipeline/aggregate.sh` after all array tasks have
  completed, or point to a complete historical report directory.
- **Missing/invalid columns:** do not edit the report in the dashboard. Confirm
  that all four tables were produced by compatible aggregation scripts and
  regenerate them if necessary.
- **Empty filters:** reset the sidebar filters to restore all conditions.
- **Pixi lock mismatch:** run `pixi install --manifest-path
  env/benchmark/pixi.toml` on a network-enabled provisioning node and commit the
  updated `env/benchmark/pixi.lock`.
- **Copied HPCC results:** preserve the four filenames in one directory, copy
  them to an accessible location, and pass that directory with `--report-dir`.

## Tests

Run the complete suite inside the benchmark environment:

```bash
pixi run --manifest-path env/benchmark/pixi.toml \
  python -m unittest discover -s tests -v
```

Synthetic dashboard fixtures under `tests/fixtures/dashboard_reports/` contain
no unpublished experimental data.
