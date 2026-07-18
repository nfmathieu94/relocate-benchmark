# Interactive benchmark dashboard implementation plan

Date/time: 2026-07-17 America/Los_Angeles

Last updated: 2026-07-18 America/Los_Angeles

## Purpose

Implement GitHub issue #3: a local Streamlit and Plotly dashboard that presents
the benchmark's existing combined reports without running callers, matching
events, or redefining authoritative metrics.

## Invariants

- `reports/correctness.tsv`, `precision.tsv`, `head_to_head.tsv`, and
  `resources.tsv` remain the dashboard's source of truth.
- Dashboard code is read-only with respect to benchmark inputs and reports.
- Precision comes only from `precision.tsv`; `class_call_share` is never
  presented as precision.
- Filter values are data-driven and the code remains N-caller compatible.
- Missing files, missing columns, empty tables, invalid numeric values, and
  duplicate keys produce actionable validation messages.
- The dashboard is launched on the login node for interactive viewing; it does
  not submit or run computational benchmark jobs.

## Architecture

```text
dashboard/app.py + dashboard/pages/
              |
              +-- components/filters.py, messages.py
              +-- plots/accuracy.py, resources.py
              +-- data/loaders.py
                        |
                        +-- validation.py (schema and duplicate contracts)
                        +-- transforms.py (display-only summaries/filters)
                                      |
                                      +-- reports/*.tsv (read-only)
```

Streamlit modules should remain thin renderers. Data loading, validation,
filtering, and plot-input transformations must be importable without starting
a Streamlit server so they can be covered by `unittest`.

## Implementation sequence

1. Add pandas, Plotly, and Streamlit to `env/benchmark/pixi.toml`, define a
   Pixi dashboard task, and add a small root-relative launch wrapper.
2. Add the modular `dashboard/` package and resolve the report directory from
   `RELOCATE_REPORT_DIR` or `--report-dir`, defaulting to `reports/`.
3. Define required/optional columns, numeric conversions, expected uniqueness,
   and a structured validation exception for each combined report.
4. Implement cached loading, shared filters, metric summaries, and plot-input
   transformations. These transformations may aggregate existing values for
   display but may not reproduce event matching or authoritative scoring.
5. Add a small synthetic two-caller fixture with multiple coverages, germline
   and somatic classes, multiple cellular fractions, and resources.
6. Test loaders, schema failures, empty files, numeric parsing, duplicates,
   filters, precision provenance, somatic selection, transformations, and safe
   module imports.
7. Implement Overview, Accuracy, Somatic, Resources, and Provenance pages with
   shared resettable filters and actionable validation errors.
8. Document launch, alternative report directories, metric interpretation,
   HPCC viewing, and troubleshooting. Update the root README.
9. Run the complete Python suite, dashboard tests, import smoke checks, Pixi
   manifest validation, and the existing R report smoke test where available.

## Status

Implemented on local branch `feat/dashboard`, based on the verified RelocaTE2
container commit. The validated data layer, five pages, filters, Plotly figure
builders, fixtures, tests, launch wrapper, pinned environment, and user
documentation are present. Browser visual review remains a final acceptance
step for the repository owner.

## Known execution constraint

The active Codex checkout exposes `.git` read-only to the agent. The repository
owner created and pushed `feat/dashboard`, after which the implementation was
migrated from its temporary scratch clone into the primary checkout. Source
edits and tests can proceed here, but the repository owner must perform local
Git metadata operations such as commit and push.

## Commands and verification

```bash
# Validated the real committed combined reports with the dashboard loader.
python -c 'from dashboard.data.loaders import load_reports; load_reports("reports")'

# Full Python suite under an existing Python 3.12 + pandas environment.
python -m unittest discover -s tests -v

# Static validation.
python -m compileall -q dashboard tests/test_dashboard_*.py
bash -n pipeline/run_dashboard.sh
pixi task list --manifest-path env/benchmark/pixi.toml

# Existing R figure builders, run where ignored per-sample match tables exist.
Rscript tests/smoke_report.R
```

Results: all 66 Python tests pass, including imports and Streamlit headless
rendering of all five pages. All five pages also render the real committed
reports with zero Streamlit exceptions. The real report schemas validate, the
dashboard task parses, shell/Python syntax checks pass, and all eight existing
R plot-builder smoke checks pass.

## Visual refinements

Interactive review on 2026-07-18 identified redundant Plotly facet text on the
Accuracy page. Facet headers now omit Plotly's generated field prefixes (for
example, `coverage=5` is displayed as `5x`, and
`biological_class=homozygous` as `Homozygous`). Repeated per-subplot x-axis
titles were replaced by one centered shared title per faceted figure. Dedicated
plot-contract tests enforce clean facet text and a single shared x-axis label.
Caller-comparison figures reserve additional bottom margin and place the shared
`Biological Class` title below the longer categorical tick labels to prevent
overlap at dashboard dimensions; interactive review set the final title offset
to `-0.42` with a 140-pixel bottom margin. Somatic-performance coverage facet
headers use the same concise `5x`, `15x`, and `30x` convention.

## Failures

- The primary checkout initially rejected `git switch -c feat/dashboard`
  because `.git` is read-only to the agent. A temporary writable clone was used
  until the repository owner created the branch in the primary checkout.
- The connected GitHub app rejected remote branch creation with HTTP 403, and
  `gh` is not installed.
- The first `pixi install` attempt could not refresh the lock because sandbox
  DNS/network access is blocked. The repository owner subsequently provisioned
  the environment and updated the lockfile successfully.
- The R smoke test cannot use a fresh clone because its required
  `reports/per_sample/` data are intentionally gitignored. It passed unchanged
  in the original checkout containing those files.
- Streamlit reached server startup, but the managed sandbox forbids creating
  listening sockets (`PermissionError: Operation not permitted`). Streamlit's
  own headless `AppTest` runtime successfully rendered fixture and real reports;
  an interactive browser check must run outside the sandbox.
- The first interactive browser check exposed that Streamlit executes secondary
  page scripts with `dashboard/pages/` as their import context, so `import
  dashboard` failed even though isolated imports and `AppTest` passed. Every
  page now bootstraps the repository root explicitly, with a subprocess
  regression test that recreates the actual page import context.

## Next steps

1. Launch Streamlit outside the managed sandbox and visually inspect every page
   and representative filter combination.
2. Ask the repository owner to commit and push the completed changes because
   the agent cannot modify `.git` in the primary checkout.
3. Continue refinements from issue #3 after the initial visual QC, then open a
   draft pull request when requested.
