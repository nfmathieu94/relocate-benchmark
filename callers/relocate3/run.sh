#!/usr/bin/bash -l
# RelocaTE3 caller adapter for the relocate-benchmark harness.
#
# Runs the full RelocaTE3 non-reference insertion + characterize pipeline on one
# sample inside the RelocaTE3 dev repo's pixi environment, writing all raw output
# under "$OUTDIR/raw". Unlike the dev-repo validation script, we have no external
# reads-to-genome alignment, so we build the full-reads-to-genome BAM ourselves
# and feed it to `characterize -b`.
#
# Contract (env vars):
#   Required: SAMPLE R1 R2 REFERENCE TE_LIBRARY REPEATMASKER OUTDIR THREADS RT3_REPO
#   Defaults: TE_NAME TSD_PATTERN TARGET RT3_ALIGNER RT3_MISMATCH
#             RT3_MIN_MATCH RT3_MIN_TRIMMED RT3_MIN_MAPQ RT3_REPLAY_MANIFEST
#   RT3_REPLAY_MANIFEST set => replay mode (development tier; see callers/relocate3-replay)
#
# Final output:
#   $OUTDIR/raw/results/$TARGET.$TE_NAME.all_nonref_insert.characTErized.txt
set -euo pipefail

# ---------------------------------------------------------------------------
# 1. Validate required inputs.
# ---------------------------------------------------------------------------
: "${SAMPLE:?SAMPLE must be set}"
: "${R1:?R1 must be set}"
: "${R2:?R2 must be set}"
: "${REFERENCE:?REFERENCE must be set}"
: "${TE_LIBRARY:?TE_LIBRARY must be set}"
: "${REPEATMASKER:?REPEATMASKER must be set}"
: "${OUTDIR:?OUTDIR must be set}"
: "${THREADS:?THREADS must be set}"
: "${RT3_REPO:?RT3_REPO must be set (RelocaTE3 repo path)}"

# Knobs with sensible defaults.
TE_NAME="${TE_NAME:-mPing}"
TSD_PATTERN="${TSD_PATTERN:-...}"
TARGET="${TARGET:-ALL}"
# Per-stage aligners (RT3_ALIGNER kept as a back-compat default for both).
RT3_TE_ALIGNER="${RT3_TE_ALIGNER:-${RT3_ALIGNER:-minimap2}}"
RT3_GENOME_ALIGNER="${RT3_GENOME_ALIGNER:-${RT3_ALIGNER:-minimap2}}"
RT3_MISMATCH="${RT3_MISMATCH:-2}"
RT3_MIN_MATCH="${RT3_MIN_MATCH:-10}"
RT3_MIN_TRIMMED="${RT3_MIN_TRIMMED:-10}"
# 0 = no MAPQ admission gate, matching RelocaTE2 and RelocaTE3's own default.
# RelocaTE2 never filters reads on MAPQ; it records MAPQ<29 as low quality
# (relocaTE_insertionFinder.py:1523,1539) and drops only calls resting entirely
# on such reads (:226-241). This adapter previously forced 1, which discarded the
# single MAPQ-0 read that often carries the second junction.
RT3_MIN_MAPQ="${RT3_MIN_MAPQ:-0}"
# Junction policy.
#
# CORRECTED 2026-08-14. This comment used to claim that RelocaTE2 keeps a site on
# `left >= 1 OR right >= 1` (relocaTE_insertionFinder.py:365), and therefore that
# passing --require-both-junctions made RelocaTE3 stricter than the tool it is
# compared against. That reading is wrong. Line 365 only admits a row into the
# intermediate all_nonref_insert.txt; the branch at :373 writes a real TSD ONLY
# when both sides have junction reads, and every one-sided case gets a sentinel
# (supporting_junction / singleton / insufficient_data) that is then dropped by
# characterizer.pl:91 and clean_false_positive.py:99,107. RelocaTE2's final call
# set is two-sided-only plus the supporting_junction class (3 of 360 calls at
# riceTElib cov30x_rep1; 5 of 412 at mPing cov30x_rep1).
#
# So ON is the like-for-like setting and the RelocaTE3 default. Default here is
# ON to match; set to 0 only for the deliberately permissive variant.
RT3_REQUIRE_BOTH_JUNCTIONS="${RT3_REQUIRE_BOTH_JUNCTIONS:-1}"
# Build the flag explicitly: "${VAR:+...}" would expand for the string "0" too,
# which is precisely the case that must NOT pass the flag.
# Always pass the policy explicitly. RelocaTE3's own default is now ON, so
# passing nothing would silently make the permissive variant strict and the two
# benchmark variants indistinguishable.
BOTH_JUNCTION_ARGS=()
case "${RT3_REQUIRE_BOTH_JUNCTIONS,,}" in
  1|true|yes|on) BOTH_JUNCTION_ARGS=(--require-both-junctions) ;;
  0|false|no|off|"") BOTH_JUNCTION_ARGS=(--no-require-both-junctions) ;;
  *) echo "ERROR: RT3_REQUIRE_BOTH_JUNCTIONS must be 0/1 (got '$RT3_REQUIRE_BOTH_JUNCTIONS')" >&2; exit 1 ;;
esac

for f in "$R1" "$R2" "$REFERENCE" "$TE_LIBRARY" "$REPEATMASKER"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: required input file missing: $f" >&2
    exit 1
  fi
done

# ---------------------------------------------------------------------------
# 1b. Replay mode (development tier). With RT3_REPLAY_MANIFEST set, reuse a
#     registered full-tier run's TE-search BAMs and all-read genotyping BAM
#     instead of rerunning BLAT and minimap2. The guard refuses when RT3_REPO's
#     TE-search source or the TE library no longer matches the cache.
#     A completed replay is reused only for the same RelocaTE3 tree: its
#     identity (HEAD + uncommitted/untracked src/ changes) is recorded in
#     replay_source.txt, and a rerun against any other tree is refused rather
#     than silently re-scoring the old calls.
# ---------------------------------------------------------------------------
REPLAY_RAW=""
REPLAY_SOURCE=""
if [[ -n "${RT3_REPLAY_MANIFEST:-}" ]]; then
  if [[ -f "$OUTDIR/.run_complete" ]]; then
    REPLAY_SOURCE="$(python3.12 callers/relocate3-replay/check_cache.py identity \
      --rt3-repo "$RT3_REPO")"
    RECORDED_SOURCE="none recorded"
    if [[ -f "$OUTDIR/replay_source.txt" ]]; then
      RECORDED_SOURCE="$(<"$OUTDIR/replay_source.txt")"
    fi
    if [[ "$RECORDED_SOURCE" != "$REPLAY_SOURCE" ]]; then
      echo "ERROR: $OUTDIR holds replay results from a different RelocaTE3 tree ($RECORDED_SOURCE) than $RT3_REPO ($REPLAY_SOURCE); move runs/dev and reports/dev aside (e.g. runs/dev-<label>) before resubmitting." >&2
      exit 1
    fi
  else
    REPLAY_RAW="$(python3.12 callers/relocate3-replay/check_cache.py check \
      --manifest "$RT3_REPLAY_MANIFEST" \
      --rt3-repo "$RT3_REPO" \
      --dataset "${DATASET:?DATASET must be set in replay mode}" \
      --sample "$SAMPLE" \
      --te-library "$TE_LIBRARY" \
      --te-aligner "$RT3_TE_ALIGNER" \
      --input "$R1" --input "$R2" --input "$REFERENCE")"
    REPLAY_SOURCE="$(python3.12 callers/relocate3-replay/check_cache.py identity \
      --rt3-repo "$RT3_REPO")"
  fi
fi

# ---------------------------------------------------------------------------
# 2. Idempotency / run-dir safety.
# ---------------------------------------------------------------------------
if [[ -f "$OUTDIR/.run_complete" ]]; then
  echo "[$(date)] RelocaTE3 run already complete for '$SAMPLE' ($OUTDIR/.run_complete); skipping."
  exit 0
fi
if [[ -d "$OUTDIR" ]] && [[ -n "$(ls -A "$OUTDIR" 2>/dev/null)" ]]; then
  echo "ERROR: refusing incomplete non-empty run dir: $OUTDIR" >&2
  echo "       Remove it or move it aside before re-running." >&2
  exit 1
fi
mkdir -p "$OUTDIR"
if [[ -n "$REPLAY_RAW" ]]; then
  printf '%s\n' "$REPLAY_SOURCE" > "$OUTDIR/replay_source.txt"
fi

# ---------------------------------------------------------------------------
# 3. Raw output directory used as RelocaTE3 --outdir / -o.
# ---------------------------------------------------------------------------
RAW="$OUTDIR/raw"
mkdir -p "$RAW"

# ---------------------------------------------------------------------------
# 4. Activate the RelocaTE3 pixi environment (puts tools on PATH).
# ---------------------------------------------------------------------------
: "${ADAPTER_DIR:=callers/relocate3}"
# shellcheck source=env.sh
source "$ADAPTER_DIR/env.sh"
if [[ -n "$REPLAY_RAW" ]]; then
  # Test the tree in RT3_REPO itself, whichever RelocaTE3 the env installed.
  export PYTHONPATH="$RT3_REPO/src${PYTHONPATH:+:$PYTHONPATH}"
  # Check with the interpreter relocaTE3 itself runs under (its shebang), so a
  # different python3 on PATH cannot pass the check for the wrong environment.
  # Trust only a python shebang: pip/uv write a `#!/bin/sh` trampoline when the
  # interpreter path exceeds 127 chars; fall back to python3 then.
  RT3_PYTHON="python3"
  _rt3_shebang="$(LC_ALL=C head -n 1 "$(command -v relocaTE3)" 2>/dev/null | tr -d '\0' || true)"
  if [[ "$_rt3_shebang" =~ ^\#\!(/[^[:space:]]+)[[:space:]]*$ && -x "${BASH_REMATCH[1]}" \
        && "${BASH_REMATCH[1]##*/}" == python* ]]; then
    RT3_PYTHON="${BASH_REMATCH[1]}"
  fi
  "$RT3_PYTHON" - <<'PY'
import os, pathlib, sys
import RelocaTE3
root = (pathlib.Path(os.environ["RT3_REPO"]) / "src").resolve()
source = getattr(RelocaTE3, "__file__", None)
if not source:
    sys.exit(f"ERROR: RelocaTE3 imported as a namespace package, not under {root}")
path = pathlib.Path(source).resolve()
print("Replay source:", path)
if not path.is_relative_to(root):
    sys.exit(f"ERROR: RelocaTE3 imported from {path}, not under {root}")
PY
fi

# ---------------------------------------------------------------------------
# 5. RelocaTE3 pipeline.
# ---------------------------------------------------------------------------
# Paths emitted by each pipeline step (must match RelocaTE3's output layout).
READ_REPEAT="$RAW/te_containing/${SAMPLE}.read_repeat_name.txt"
FLANK5="$RAW/flanking/${SAMPLE}.left.flankingReads.fq"
FLANK3="$RAW/flanking/${SAMPLE}.right.flankingReads.fq"
# align-genome names the BAM by the genome aligner: minimap2 keeps the historical
# ".repeat.minimap.sorted.bam"; others use ".repeat.<aligner>.sorted.bam".
if [[ "$RT3_GENOME_ALIGNER" == "minimap2" ]]; then
  GENOME_BAM="$RAW/${SAMPLE}.repeat.minimap.sorted.bam"
else
  GENOME_BAM="$RAW/${SAMPLE}.repeat.${RT3_GENOME_ALIGNER}.sorted.bam"
fi
JUNCTION_FULLREADS_BAM="$RAW/genome_aln/${SAMPLE}.fullreads.genome.bam"
NONREF_TXT="$RAW/results/${TARGET}.${TE_NAME}.all_nonref_insert.txt"
CHAR_TXT="$RAW/results/${TARGET}.${TE_NAME}.all_nonref_insert.characTErized.txt"
CHARACTERIZATION_BAM="$RAW/${SAMPLE}.original_reads.sorted.bam"

echo "[$(date)] RelocaTE3 benchmark adapter"
echo "  sample      : $SAMPLE"
echo "  reference   : $REFERENCE"
echo "  TE library  : $TE_LIBRARY"
echo "  R1          : $R1"
echo "  R2          : $R2"
echo "  outdir      : $OUTDIR (raw -> $RAW)"
echo "  threads     : $THREADS"
echo "  te-aligner  : $RT3_TE_ALIGNER${REPLAY_RAW:+ (cached)}"
echo "  gen-aligner : $RT3_GENOME_ALIGNER"
echo "  mismatch    : $RT3_MISMATCH"
echo "  match/trim  : ${RT3_MIN_MATCH}/${RT3_MIN_TRIMMED}"
echo "  te_name/TSD : ${TE_NAME}/${TSD_PATTERN}"
echo "  target      : $TARGET"
echo "  min-mapq    : $RT3_MIN_MAPQ"
echo "  both-junc   : $RT3_REQUIRE_BOTH_JUNCTIONS"
echo "  replay      : ${REPLAY_RAW:-no (full TE search)}"

# Reference inputs are external and read-only to this benchmark. Substantial
# indexing also does not belong inside every array task.
if [[ ! -s "${REFERENCE}.fai" || ! -s "${REFERENCE}.mmi" ]]; then
  echo "ERROR: prebuilt reference indexes are required (.fai and .mmi)" >&2
  echo "       Build them through a separate HPC job before submission." >&2
  exit 1
fi
echo "[$(date)] genome already indexed (.fai + .mmi present)"

# Steps 2+3: align reads to the TE library and trim TE sequence from them.
if [[ -n "$REPLAY_RAW" ]]; then
  # Same write_trimmed_reads call `run` makes, on the cached TE-search BAMs.
  echo "[$(date)] replay: trim from cached TE-search BAMs in $REPLAY_RAW"
  for side in left right; do
    for ext in bam bam.bai; do
      ln -s "$(readlink -f "$REPLAY_RAW/${SAMPLE}.${side}.${ext}")" \
        "$RAW/${SAMPLE}.${side}.${ext}"
    done
  done
  relocaTE3 trim \
    --bam "$RAW/${SAMPLE}.left.bam" "$RAW/${SAMPLE}.right.bam" \
    --fastq "$R1" "$R2" \
    --name "$SAMPLE" \
    --outdir "$RAW" \
    --min-match "$RT3_MIN_MATCH" \
    --min-trimmed "$RT3_MIN_TRIMMED" \
    --mismatch "$RT3_MISMATCH"
else
  echo "[$(date)] run (map + trim)"
  relocaTE3 run \
    --left "$R1" \
    --right "$R2" \
    --te-library "$TE_LIBRARY" \
    --name "$SAMPLE" \
    --outdir "$RAW" \
    --threads "$THREADS" \
    --te-aligner "$RT3_TE_ALIGNER" \
    --min-match "$RT3_MIN_MATCH" \
    --min-trimmed "$RT3_MIN_TRIMMED" \
    --mismatch "$RT3_MISMATCH"
fi

if [[ ! -s "$READ_REPEAT" ]]; then
  echo "ERROR: expected read_repeat table not produced: $READ_REPEAT" >&2
  exit 1
fi

# Step 4: align trimmed flanking reads back to the reference genome.
FLANK_INPUTS=()
[[ -s "$FLANK5" ]] && FLANK_INPUTS+=("$FLANK5")
[[ -s "$FLANK3" ]] && FLANK_INPUTS+=("$FLANK3")
if [[ ${#FLANK_INPUTS[@]} -eq 0 ]]; then
  echo "ERROR: no flanking FASTQs produced under $RAW/flanking/" >&2
  exit 1
fi

echo "[$(date)] align-genome (flanking -> genome BAM)"
relocaTE3 align-genome \
  -g "$REFERENCE" \
  -f "${FLANK_INPUTS[@]}" \
  -n "$SAMPLE" \
  -o "$RAW" \
  --threads "$THREADS" \
  --genome-aligner "$RT3_GENOME_ALIGNER" \
  -1 "$R1" \
  -2 "$R2"

if [[ ! -s "$GENOME_BAM" ]]; then
  echo "ERROR: expected genome-aligned BAM not produced: $GENOME_BAM" >&2
  exit 1
fi

# align-genome also restores and aligns only the original versions of junction
# reads. RelocaTE2 feeds this small bwa-aln BAM into step 5 to reject apparent
# junctions whose full reads map straight through both proposed breakpoints.
FULLREAD_FILTER_ARGS=()
HAS_JUNCTIONS=0
for flank in "${FLANK_INPUTS[@]}"; do
  if grep -m 1 -Eq '^@.*:(start|end):[53]([[:space:]]|$)' "$flank"; then
    HAS_JUNCTIONS=1
    break
  fi
done
if [[ "$HAS_JUNCTIONS" -eq 1 ]]; then
  if [[ ! -s "$JUNCTION_FULLREADS_BAM" || ! -s "${JUNCTION_FULLREADS_BAM}.bai" ]]; then
    echo "ERROR: junction reads exist but their full-read BAM/index is missing:" >&2
    echo "       $JUNCTION_FULLREADS_BAM" >&2
    exit 1
  fi
  FULLREAD_FILTER_ARGS=(--fullreads-bam "$JUNCTION_FULLREADS_BAM")
  echo "[$(date)] false-junction BAM: $JUNCTION_FULLREADS_BAM"
else
  echo "[$(date)] no junction reads; full-read false-junction filter is not needed"
fi

# Step 5: cluster junction/supporting reads and call non-reference insertions.
echo "[$(date)] find-insertions"
relocaTE3 find-insertions \
  -b "$GENOME_BAM" \
  --read-repeat "$READ_REPEAT" \
  --tsd "$TSD_PATTERN" \
  --target "$TARGET" \
  --name "$SAMPLE" \
  --outdir "$RAW" \
  --te-name "$TE_NAME" \
  --reference-ins "$REPEATMASKER" \
  --mismatch "$RT3_MISMATCH" \
  --min-mapq "$RT3_MIN_MAPQ" \
  "${FULLREAD_FILTER_ARGS[@]}" \
  "${BOTH_JUNCTION_ARGS[@]}"

# Absent means find-insertions failed; present-but-empty means it ran and
# called nothing, which is a real result -- at 20% TE divergence both callers
# collapse (RelocaTE2 recall 0.002, RelocaTE3 0.000). Scoring that as zero
# recall is correct; failing the task loses the data point and, because the
# aggregation job is afterok, silently blocks the whole panel.
if [[ ! -f "$NONREF_TXT" ]]; then
  echo "ERROR: expected non-reference insertion table not produced: $NONREF_TXT" >&2
  exit 1
fi

# Build the full-reads-to-genome BAM ourselves for characterize (no external
# alignment available in the benchmark). Atomic: write to a temp then rename.
if [[ -n "$REPLAY_RAW" ]]; then
  # minimap2 of all reads involves no RelocaTE3 code; reuse it read-only.
  CHARACTERIZATION_BAM="$(readlink -f "$REPLAY_RAW/${SAMPLE}.original_reads.sorted.bam")"
  echo "[$(date)] replay: cached all-read BAM $CHARACTERIZATION_BAM"
else
  echo "[$(date)] building full-reads-to-genome BAM for characterize"
  minimap2 -a -x sr -t "$THREADS" "$REFERENCE" "$R1" "$R2" \
    | samtools sort -@ "$THREADS" -o "${CHARACTERIZATION_BAM}.tmp"
  mv -f "${CHARACTERIZATION_BAM}.tmp" "$CHARACTERIZATION_BAM"
  samtools index "$CHARACTERIZATION_BAM"
fi

# Step 7: characterize zygosity (hom/het/somatic) using our full-reads BAM.
echo "[$(date)] characterize (step 7) using all-read BAM: $CHARACTERIZATION_BAM"
relocaTE3 characterize \
  -s "$NONREF_TXT" \
  -b "$CHARACTERIZATION_BAM" \
  -g "$REFERENCE" \
  -o "$RAW/results" \
  --samtools samtools --bcftools "$RT3_BCFTOOLS"

# ---------------------------------------------------------------------------
# 6. Assert final characterized output exists and is non-empty.
# ---------------------------------------------------------------------------
if [[ ! -f "$CHAR_TXT" ]]; then
  echo "ERROR: characterized output missing: $CHAR_TXT" >&2
  exit 1
fi
if [[ ! -s "$CHAR_TXT" ]]; then
  echo "[$(date)] NOTE: caller reported zero insertions for '$SAMPLE'; recording as a zero-recall result."
fi

# ---------------------------------------------------------------------------
# 7. Sentinel.
# ---------------------------------------------------------------------------
date > "$OUTDIR/.run_complete"
echo "[$(date)] RelocaTE3 run complete for '$SAMPLE'"
echo "  characterized table: $CHAR_TXT"
