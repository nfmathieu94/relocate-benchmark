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
#             RT3_MIN_MATCH RT3_MIN_TRIMMED RT3_MIN_MAPQ
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
RT3_MIN_MAPQ="${RT3_MIN_MAPQ:-1}"

for f in "$R1" "$R2" "$REFERENCE" "$TE_LIBRARY" "$REPEATMASKER"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: required input file missing: $f" >&2
    exit 1
  fi
done

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

# ---------------------------------------------------------------------------
# 3. Raw output directory used as RelocaTE3 --outdir / -o.
# ---------------------------------------------------------------------------
RAW="$OUTDIR/raw"
mkdir -p "$RAW"

# ---------------------------------------------------------------------------
# 4. Activate the RelocaTE3 pixi environment (puts tools on PATH).
# ---------------------------------------------------------------------------
ADAPTER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env.sh
source "$ADAPTER_DIR/env.sh"

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
NONREF_TXT="$RAW/results/${TARGET}.${TE_NAME}.all_nonref_insert.txt"
CHAR_TXT="$RAW/results/${TARGET}.${TE_NAME}.all_nonref_insert.characTErized.txt"
FULLREADS_BAM="$RAW/${SAMPLE}.original_reads.sorted.bam"

echo "[$(date)] RelocaTE3 benchmark adapter"
echo "  sample      : $SAMPLE"
echo "  reference   : $REFERENCE"
echo "  TE library  : $TE_LIBRARY"
echo "  R1          : $R1"
echo "  R2          : $R2"
echo "  outdir      : $OUTDIR (raw -> $RAW)"
echo "  threads     : $THREADS"
echo "  te-aligner  : $RT3_TE_ALIGNER"
echo "  gen-aligner : $RT3_GENOME_ALIGNER"
echo "  mismatch    : $RT3_MISMATCH"
echo "  match/trim  : ${RT3_MIN_MATCH}/${RT3_MIN_TRIMMED}"
echo "  te_name/TSD : ${TE_NAME}/${TSD_PATTERN}"
echo "  target      : $TARGET"
echo "  min-mapq    : $RT3_MIN_MAPQ"

# Step 1: index the reference genome (skip if .fai + .mmi already exist).
if [[ ! -s "${REFERENCE}.fai" || ! -s "${REFERENCE}.mmi" ]]; then
  echo "[$(date)] index-genome"
  relocaTE3 index-genome -g "$REFERENCE"
else
  echo "[$(date)] genome already indexed (.fai + .mmi present), skipping index-genome"
fi

# Steps 2+3: align reads to the TE library and trim TE sequence from them.
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
  --genome-aligner "$RT3_GENOME_ALIGNER"

if [[ ! -s "$GENOME_BAM" ]]; then
  echo "ERROR: expected genome-aligned BAM not produced: $GENOME_BAM" >&2
  exit 1
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
  --min-mapq "$RT3_MIN_MAPQ"

if [[ ! -s "$NONREF_TXT" ]]; then
  echo "ERROR: expected non-reference insertion table not produced: $NONREF_TXT" >&2
  exit 1
fi

# Build the full-reads-to-genome BAM ourselves for characterize (no external
# alignment available in the benchmark). Atomic: write to a temp then rename.
echo "[$(date)] building full-reads-to-genome BAM for characterize"
minimap2 -a -x sr -t "$THREADS" "$REFERENCE" "$R1" "$R2" \
  | samtools sort -@ "$THREADS" -o "${FULLREADS_BAM}.tmp"
mv -f "${FULLREADS_BAM}.tmp" "$FULLREADS_BAM"
samtools index "$FULLREADS_BAM"

# Step 7: characterize zygosity (hom/het/somatic) using our full-reads BAM.
echo "[$(date)] characterize (step 7) using full-reads BAM: $FULLREADS_BAM"
relocaTE3 characterize \
  -s "$NONREF_TXT" \
  -b "$FULLREADS_BAM" \
  -g "$REFERENCE" \
  -o "$RAW/results" \
  --samtools samtools --bcftools "$RT3_BCFTOOLS"

# ---------------------------------------------------------------------------
# 6. Assert final characterized output exists and is non-empty.
# ---------------------------------------------------------------------------
if [[ ! -s "$CHAR_TXT" ]]; then
  echo "ERROR: characterized output missing or empty: $CHAR_TXT" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 7. Sentinel.
# ---------------------------------------------------------------------------
date > "$OUTDIR/.run_complete"
echo "[$(date)] RelocaTE3 run complete for '$SAMPLE'"
echo "  characterized table: $CHAR_TXT"
