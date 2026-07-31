#!/usr/bin/bash -l
# RelocaTE2 caller adapter for the relocate-benchmark harness.
#
# Runs the full RelocaTE2 non-reference insertion + characterize pipeline on one
# sample, writing all raw output under "$OUTDIR/raw". RelocaTE2 needs a
# reads-to-genome BAM (its --bam input); the benchmark has raw reads only, so we
# build that BAM ourselves with bwa mem before invoking relocaTE2.py.
#
# Contract (env vars):
#   Required: SAMPLE R1 R2 REFERENCE TE_LIBRARY REPEATMASKER OUTDIR THREADS
#   Defaults: RT2_ALIGNER RT2_SIZE RT2_MISMATCH
#
# Final output:
#   $OUTDIR/raw/repeat/results/ALL.all_nonref_insert.characTErized.txt
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

# Knobs with sensible defaults.
RT2_ALIGNER="${RT2_ALIGNER:-blat}"
RT2_SIZE="${RT2_SIZE:-250}"
RT2_MISMATCH="${RT2_MISMATCH:-2}"

for f in "$R1" "$R2" "$REFERENCE" "$TE_LIBRARY" "$REPEATMASKER"; do
  if [[ ! -f "$f" ]]; then
    echo "ERROR: required input file missing: $f" >&2
    exit 1
  fi
done

# The reference must already carry a bwa index; building one here would be huge
# and slow, so refuse rather than silently indexing.
if [[ ! -f "${REFERENCE}.bwt" ]]; then
  echo "ERROR: reference not bwa-indexed (missing ${REFERENCE}.bwt)" >&2
  echo "       Run 'bwa index $REFERENCE' once before benchmarking." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 2. Idempotency / run-dir safety.
# ---------------------------------------------------------------------------
if [[ -f "$OUTDIR/.run_complete" ]]; then
  echo "[$(date)] RelocaTE2 run already complete for '$SAMPLE' ($OUTDIR/.run_complete); skipping."
  exit 0
fi
if [[ -d "$OUTDIR" ]] && [[ -n "$(ls -A "$OUTDIR" 2>/dev/null)" ]]; then
  echo "ERROR: refusing incomplete non-empty run dir: $OUTDIR" >&2
  echo "       Remove it or move it aside before re-running." >&2
  exit 1
fi
mkdir -p "$OUTDIR"

# ---------------------------------------------------------------------------
# 3. Working sub-directories.
#    RAW     -> relocaTE2.py --outdir (it writes RAW/repeat/... here)
#    FQ_DIR  -> holds ${SAMPLE}_R1.fastq / ${SAMPLE}_R2.fastq for --fq_dir
#    BAM_DIR -> holds the reads-to-genome BAM for --bam (a directory input)
# ---------------------------------------------------------------------------
RAW="$OUTDIR/raw"
FQ_DIR="$OUTDIR/fq"
BAM_DIR="$OUTDIR/bam"
mkdir -p "$RAW" "$FQ_DIR" "$BAM_DIR"

# ---------------------------------------------------------------------------
# 4. Put relocaTE2.py / bwa / samtools on PATH.
# ---------------------------------------------------------------------------
: "${ADAPTER_DIR:=callers/relocate2}"
# shellcheck source=env.sh
source "$ADAPTER_DIR/env.sh"

# ---------------------------------------------------------------------------
# 5. Stage reads under RelocaTE2's mate-id naming convention (_R1 / _R2).
#    Preserve a gzip suffix: RelocaTE2 supports *.fastq.gz, but hiding gzip data
#    behind a *.fastq symlink can make suffix-based readers treat it as text.
# ---------------------------------------------------------------------------
if [[ "$R1" == *.gz && "$R2" == *.gz ]]; then
  STAGED_FASTQ_SUFFIX=".fastq.gz"
elif [[ "$R1" != *.gz && "$R2" != *.gz ]]; then
  STAGED_FASTQ_SUFFIX=".fastq"
else
  echo "ERROR: R1/R2 compression differs; both mates must be gzip or plain FASTQ" >&2
  exit 1
fi
ln -sf "$(readlink -f "$R1")" "$FQ_DIR/${SAMPLE}_R1${STAGED_FASTQ_SUFFIX}"
ln -sf "$(readlink -f "$R2")" "$FQ_DIR/${SAMPLE}_R2${STAGED_FASTQ_SUFFIX}"

# ---------------------------------------------------------------------------
# 6. Build the reads-to-genome BAM (atomic: temp then rename) and index it.
# ---------------------------------------------------------------------------
GENOME_BAM="$BAM_DIR/${SAMPLE}.bam"
CHAR_TXT="$RAW/repeat/results/ALL.all_nonref_insert.characTErized.txt"

echo "[$(date)] RelocaTE2 benchmark adapter"
echo "  sample      : $SAMPLE"
echo "  reference   : $REFERENCE"
echo "  TE library  : $TE_LIBRARY"
echo "  repeatmasker: $REPEATMASKER"
echo "  R1          : $R1"
echo "  R2          : $R2"
echo "  outdir      : $OUTDIR (raw -> $RAW)"
echo "  threads     : $THREADS"
echo "  aligner     : $RT2_ALIGNER"
echo "  size        : $RT2_SIZE"
echo "  mismatch    : $RT2_MISMATCH"

echo "[$(date)] building reads-to-genome BAM: $GENOME_BAM"
# -T gives samtools a task-specific temp prefix under this sample's own BAM dir.
# Without it, sorting from the bwa-mem pipe spills to "STDIN.tmp.*.bam" in the
# shared CWD, so concurrent array tasks truncate one another's temp files (only
# surfaces when the BAM is large enough to spill, e.g. the multi-TE panel).
bwa mem -t "$THREADS" "$REFERENCE" "$R1" "$R2" \
  | samtools sort -@ "$THREADS" -T "$BAM_DIR/sort.${SAMPLE}" -o "${GENOME_BAM}.tmp"
mv -f "${GENOME_BAM}.tmp" "$GENOME_BAM"
samtools index "$GENOME_BAM"

# ---------------------------------------------------------------------------
# 7. Run RelocaTE2. Step string 1234567 includes step 7 (the characterizer that
#    writes the genotype `status` column). We do NOT run CallPing.py.
# ---------------------------------------------------------------------------
echo "[$(date)] relocaTE2.py (steps 1234567)"
relocaTE2.py \
  --te_fasta "$TE_LIBRARY" \
  --reference_ins "$REPEATMASKER" \
  --genome_fasta "$REFERENCE" \
  --fq_dir "$FQ_DIR" \
  --mate_1_id _R1 \
  --mate_2_id _R2 \
  --outdir "$RAW" \
  --sample "$SAMPLE" \
  --bam "$BAM_DIR" \
  --split \
  --run \
  --size "$RT2_SIZE" \
  --step 1234567 \
  --mismatch "$RT2_MISMATCH" \
  --cpu "$THREADS" \
  --aligner "$RT2_ALIGNER" \
  --verbose 4

# ---------------------------------------------------------------------------
# 8. Assert the characterized output exists and is non-empty.
# ---------------------------------------------------------------------------
if [[ ! -s "$CHAR_TXT" ]]; then
  echo "ERROR: characterized output missing or empty: $CHAR_TXT" >&2
  echo "       (Confirm this path on the first real run; RelocaTE2 writes it" >&2
  echo "        under <outdir>/repeat/results/.)" >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# 9. Sentinel.
# ---------------------------------------------------------------------------
date > "$OUTDIR/.run_complete"
echo "[$(date)] RelocaTE2 run complete for '$SAMPLE'"
echo "  characterized table: $CHAR_TXT"
