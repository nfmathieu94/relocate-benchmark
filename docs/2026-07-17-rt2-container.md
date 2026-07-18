# RelocaTE2 containerization — digest-pinned BioContainers

Date/time: 2026-07-17

## Purpose

Give RelocaTE2 a portable, digest-pinned frozen environment via pulled
BioContainers, closing the Phase 1 gap where RT2 was cluster-module-only (see
`docs/2026-07-17-env-pinning.md`). RT2 cannot be a pixi env — its bioconda
package (relocate2 2.0.1) is a dead python-2.7 build whose dependency closure no
longer resolves on current channels.

Local image builds are **blocked on this cluster** (empty `/etc/subuid`,
fakeroot broken), so we **PULL** immutable BioContainers by digest rather than
building. Pinning by `@sha256:` digest makes the images reproducible and
tamper-evident.

## Pinned images

Manifest: `callers/relocate2/images.txt` (format: `<sifname> <apptainer-pull-ref>`).
Pulled into gitignored `callers/relocate2/images/<sifname>.sif`.

- **relocate2** — `docker://quay.io/biocontainers/relocate2@sha256:900d3dd35c324f03f328839ce134df937a9f5b0b4b122cbc4cd431eb66c7e109`
  (tag `2.0.1--hdfd78af_6`, the same build as cluster module `relocate2/2.0.1`).
  Provides `relocaTE2.py`, `blat`, and `samtools`.
- **bwa** — `docker://quay.io/biocontainers/bwa@sha256:99a35e5ee4e9c329e8746c4689890b97a3ac5620cb36d374cba69ba52016e72a`
  (tag `0.7.19--h577a1d6_1`). Provides modern `bwa` (0.7.19) for the adapter's
  `bwa mem` reads-to-genome alignment step.

## How env.sh works

`callers/relocate2/env.sh` is **container-first** and is *sourced* by the
caller's `run.sh` (run.sh is unchanged):

- Builds a task-scoped shim `bin` dir (via `mktemp -d`) prepended to `PATH`.
  Each shim execs its image: `relocaTE2.py`/`blat`/`samtools` →
  `apptainer exec relocate2.sif <tool>`, and `bwa` → `apptainer exec bwa.sif bwa`.
- Bind roots so containers see reference/reads/OUTDIR:
  `APPTAINER_BIND=/bigdata,/rhome,/scratch` (preserving any pre-set binds).
- Apptainer cache on `/scratch`: `APPTAINER_CACHEDIR=/scratch/$USER/apptainer-cache`.
- Preserves the uniform verify step: `relocaTE2.py blat bwa samtools` must all be
  on PATH after setup, else `exit 127`.

**Fallback chain:** container → Phase 1 pinned cluster modules
(`callers/relocate2/pinned-modules.txt`: `relocate2/2.0.1` + `bwa/0.7.19`) →
error. The module fallback emits a `WARN`; a total failure (no containers, no
modules) exits 1.

## Commands

Provision everything (idempotent — pixi envs plus RT2 image pulls; skips any
`.sif` that already exists):

```bash
bash pipeline/setup_envs.sh
```

`setup_envs.sh` pulls the RT2 images after the pixi installs. Apptainer is
required for the container path; if it is unavailable the pulls are skipped with
a `WARN` and env.sh falls back to modules.

How a run activates: `run.sh` sources `callers/relocate2/env.sh`, which puts the
apptainer-exec shims (or the module tools) on PATH for that task.

## How to bump an image

1. Resolve the new digest for the desired tag (e.g. via the quay.io tag API):

   ```bash
   curl -s 'https://quay.io/api/v1/repository/biocontainers/relocate2/tag/?onlyActiveTags=true' \
     | python3 -m json.tool | grep -A2 '"name": "<new-tag>"'
   ```

   (Use the `manifest_digest` field for the `@sha256:...` ref.)
2. Edit the `<name> docker://...@sha256:...` line in
   `callers/relocate2/images.txt`.
3. Remove the stale local image so it is re-pulled:

   ```bash
   rm callers/relocate2/images/<name>.sif
   ```
4. Re-pull:

   ```bash
   bash pipeline/setup_envs.sh
   ```

## Verification (2026-07-17)

Container-tool checks, all green:

- `relocaTE2.py -h` runs OK inside the relocate2 container.
- `bwa` reports version 0.7.19 via the bwa container.
- `blat` reports v35 and `samtools` runs, both from the relocate2 container.
- All four tools (`relocaTE2.py blat bwa samtools`) resolve to the task-scoped
  shim dir on PATH, not to cluster modules.

**Version caveat (documented honestly):** the relocate2 BioContainer bundles
**samtools 1.3**, whereas the cluster module bundles **samtools 1.9**. samtools
is used only for BAM sort/index and is not expected to change TE calls. A cov5
acceptance re-run comparing container results to the pinned-module/Jul-15
baseline is the validation method for this; that run is **in progress — result
pending confirmation** (do not treat the acceptance as passed yet).

## Decisions / logic

- PULL, not build: local builds are impossible here (empty `/etc/subuid`,
  fakeroot broken), so digest-pinned pulls are the portable freeze.
- Container-first with a module fallback keeps runs working on this cluster even
  if a pull fails, while giving off-cluster portability when apptainer + images
  are present.
- Two images (relocate2 + a separate modern bwa) mirror the Phase 1 split where
  a modern `bwa mem` must win over the package's bundled bwa 0.6.2.

## Next steps

- Confirm the cov5 acceptance (identical results vs the pinned-module/Jul-15
  baseline) and record the outcome here.
- RelocaTE3 and the benchmark/scoring stack stay on pixi. A CI → GHCR path could
  containerize those too later for full off-cluster portability.
