# RelocaTE2 containerization (Phase 2) — design

Date/time: 2026-07-17 America/Los_Angeles

## Purpose

Give RelocaTE2 a portable, digest-pinned frozen environment via a container, so
it no longer depends on the cluster `relocate2/2.0.1` module — closing the one
gap Phase 1 left open (RT2 was cluster-only; see [[env-pinning-phase1]] /
relocate2-not-conda-freezable). RT3 and the benchmark stay on their pixi envs.

## Key findings (verified 2026-07-17)

- **Local image builds are BLOCKED on this cluster.** `apptainer build --fakeroot`
  fails: `/etc/subuid`/`/etc/subgid` are empty and the fakeroot `faked` daemon is
  missing. User namespaces work (`unshare -r` ok) and **pull + exec work**
  (`apptainer exec docker://alpine ...` succeeds), so we can run/convert existing
  images but not build def-file images locally.
- **RelocaTE2 has a prebuilt BioContainer** on quay.io at the SAME build hash as
  the cluster module: `relocate2:2.0.1--hdfd78af_6`. So RT2 can be containerized
  by PULLING an immutable image — no build needed.
- apptainer 1.4.5 via `module load apptainer`. `/scratch` (1.5 TB free) for the
  apptainer cache/tmp (avoid NFS).

## Decisions (approved 2026-07-17)

Containerize RT2 via pulled BioContainers; leave RT3/benchmark on pixi; no CI.

## Images (pulled, pinned by digest)

Recorded in `callers/relocate2/images.txt` (manifest, like `pinned-modules.txt`):

| role       | image (digest-pinned)                                                        | provides                    |
|------------|-------------------------------------------------------------------------------|-----------------------------|
| relocate2  | `docker://quay.io/biocontainers/relocate2:2.0.1--hdfd78af_6` @ `sha256:900d3dd35c324f03f328839ce134df937a9f5b0b4b122cbc4cd431eb66c7e109` | relocaTE2.py, blat, samtools |
| bwa        | `docker://quay.io/biocontainers/bwa:0.7.19--h577a1d6_1` @ `sha256:99a35e5ee4e9c329e8746c4689890b97a3ac5620cb36d374cba69ba52016e72a` | bwa (for `bwa mem`)          |

`.sif` files materialize under a gitignored `callers/relocate2/images/`.

## env.sh — container-first via shims (run.sh unchanged)

`env.sh` builds a task-scoped shim bin dir on PATH; each required tool is a tiny
wrapper that `apptainer exec`s the right image:
- `relocaTE2.py`, `blat`, `samtools` → `apptainer exec <relocate2.sif> <tool> "$@"`
- `bwa` → `apptainer exec <bwa.sif> bwa "$@"`

So `run.sh` still calls `bwa mem` / `relocaTE2.py` unchanged; the shims route them.
This also removes the PATH-ordering hazard: the `bwa` shim always resolves to the
0.7.19 image, and `relocaTE2.py`'s internal `blat`/`samtools` calls resolve inside
its own container. Binds: `--bind /bigdata,/rhome,/scratch` so containers see the
reference, reads, and `OUTDIR`. apptainer cache/tmp → `/scratch`.

## Fallback chain (each degradation warns)

container (portable) → **Phase 1 pinned modules** (cluster-only) → error.
The `relocaTE2.py blat bwa samtools` presence check (`exit 127`) is preserved.

## Provisioning

Extend `pipeline/setup_envs.sh` with an idempotent apptainer-pull step: for each
line in `callers/relocate2/images.txt`, `apptainer pull` the digest-pinned image
into `callers/relocate2/images/<name>.sif` (skip if present). Requires
`module load apptainer` + network. Gitignore `callers/relocate2/images/`.

## Verification

Re-run the cov5 RelocaTE2 tasks under the containerized `env.sh` and confirm the
per-sample results are IDENTICAL to the pinned-module run (already bit-identical
to Jul-15). Note the rerun hygiene: clear `runs/relocate2/cov5x_rep*` and
`reports/per_sample/relocate2/cov5x_rep*` first (see [[env-pinning-phase1]]).

## Boundary / scope

Only `callers/relocate2/` + `pipeline/setup_envs.sh` + `.gitignore` change. RT2
adapter contract untouched. RT3/benchmark unchanged. No local build, no CI;
works on any cluster with apptainer.

## Next steps

Turn into a task-by-task implementation plan (writing-plans), then execute.
Later (optional): a CI→GHCR path could containerize RT3 + benchmark too.
