#!/usr/bin/bash -l
#SBATCH -p epyc
#SBATCH --mem=48gb
#SBATCH --cpus-per-task=8
#SBATCH --time=04:00:00
#SBATCH -J bwa-aln-version-diff
#SBATCH -o logs/bwa_aln_version_diff.%j.log
#
# Diagnostic: does `bwa aln` 0.6.2 (what RelocaTE2 uses, bundled in its
# BioContainer) place RelocaTE3's flanking reads differently from 0.7.19 (what
# RelocaTE3 uses)?
#
# Context: BLAT v35 vs v36 was tested head-to-head and produces byte-identical
# PSL, so the TE search is not the divergence. bwa aln is the one remaining
# uncontrolled aligner difference on the path where RelocaTE3 emits ~2.3x the
# calls RelocaTE2 does on riceTElib. It matters beyond raw placement because
# RelocaTE3's read-admission gate (`InsertionFinder._passes_quality`, a port of
# relocaTE_insertionFinder.py:1521-1558) filters on bwa's XT and X1 tags.
#
# Both versions are run on the SAME flanking FASTQ subset against the SAME
# reference, with the exact command RelocaTE3 issues:
#     bwa aln -t <threads> <ref> <fq>  ->  bwa samse <ref> <sai> <fq>
#
# Submit from the repository root:
#     sbatch scripts/compare_bwa_aln_versions.sh
set -euo pipefail

echo "[$(date)] bwa aln version comparison starting on $(hostname)"

THREADS="${SLURM_CPUS_PER_TASK:-8}"
BASE_DIR="${SLURM_SUBMIT_DIR:-$(pwd)}"
cd "$BASE_DIR"

# --- inputs -----------------------------------------------------------------
SAMPLE="${SAMPLE:-cov30x_rep1}"
FLANK="${FLANK:-runs/ricetelib/relocate3-blat-bwaaln/${SAMPLE}/raw/flanking/${SAMPLE}.left.flankingReads.fq}"
REFERENCE="${REFERENCE:-/bigdata/wesslerlab/shared/Rice/Nathan/rice/make_simulated_genome/make_simulation_new/input/ref_genome/MSU_r7.fa}"
RT2_SIF="${RT2_SIF:-callers/relocate2/images/relocate2.sif}"
BWA_NEW="${BWA_NEW:-/bigdata/stajichlab/nmath020/github/github_tools/RelocaTE/RelocaTE3_jason/RelocaTE3/.pixi/envs/default/bin/bwa}"
# Reads to sample. The whole file is ~1.5M reads; a subset keeps the two index
# builds (single-threaded, ~10 min each) the dominant cost.
NREADS="${NREADS:-200000}"

# Work under runs/ (gitignored, on /bigdata). /scratch/$USER exists on the login
# node but is not writable from the compute nodes, which failed job 27545711 at
# its first mkdir. The two bwa indexes need ~1.5 GB each, so node-local /tmp is
# not a safe default either.
WORK="${WORK:-$BASE_DIR/runs/_diag/bwa_aln_version_diff.${SLURM_JOB_ID:-manual}}"
OUT="${OUT:-$BASE_DIR/runs/_diag}"

for f in "$FLANK" "$REFERENCE" "$RT2_SIF" "$BWA_NEW"; do
  if [[ ! -e "$f" ]]; then
    echo "ERROR: missing required input: $f" >&2
    exit 1
  fi
done

mkdir -p "$WORK" "$OUT" logs

echo "  sample     : $SAMPLE"
echo "  flanks     : $FLANK"
echo "  reference  : $REFERENCE"
echo "  reads used : $NREADS"
echo "  threads    : $THREADS"
echo "  workdir    : $WORK"
echo "  outdir     : $OUT"

# --- apptainer shim for the RelocaTE2 container -----------------------------
command -v apptainer >/dev/null 2>&1 || module load apptainer || true
command -v apptainer >/dev/null 2>&1 || { echo "ERROR: apptainer unavailable" >&2; exit 1; }
export APPTAINER_CACHEDIR="${APPTAINER_CACHEDIR:-$WORK/apptainer-cache}"
RT2_SIF_ABS="$(readlink -f "$RT2_SIF")"
bwa_old() { apptainer exec -B /scratch:/scratch -B /bigdata:/bigdata "$RT2_SIF_ABS" bwa "$@"; }

echo "[$(date)] versions under test:"
echo -n "  old (RelocaTE2 container): "; bwa_old 2>&1 | grep -i '^Version' || true
echo -n "  new (RelocaTE3 pixi)     : "; "$BWA_NEW" 2>&1 | grep -i '^Version' || true

# --- subsample the flanking reads (deterministic) ---------------------------
SUB="$WORK/flanks.subset.fq"
if [[ ! -s "$SUB" ]]; then
  echo "[$(date)] subsampling $NREADS reads"
  head -n $((NREADS * 4)) "$FLANK" > "$SUB.tmp"
  mv -f "$SUB.tmp" "$SUB"
fi
echo "  subset reads: $(( $(wc -l < "$SUB") / 4 ))"

# --- per-version index ------------------------------------------------------
# bwa changed its index format historically, so each version gets its own copy
# rather than assuming cross-compatibility.
REF_OLD="$WORK/ref_old/$(basename "$REFERENCE")"
REF_NEW="$WORK/ref_new/$(basename "$REFERENCE")"
for pair in "old:$REF_OLD" "new:$REF_NEW"; do
  tag="${pair%%:*}"; ref="${pair#*:}"
  mkdir -p "$(dirname "$ref")"
  [[ -e "$ref" ]] || ln -s "$(readlink -f "$REFERENCE")" "$ref"
  if [[ ! -s "${ref}.bwt" ]]; then
    echo "[$(date)] building bwa index ($tag)"
    if [[ "$tag" == old ]]; then bwa_old index "$ref"; else "$BWA_NEW" index "$ref"; fi
  else
    echo "[$(date)] bwa index ($tag) already present"
  fi
done

# --- align with each version ------------------------------------------------
align() {  # align <tag> <ref>
  local tag="$1" ref="$2"
  local sai="$WORK/${tag}.sai" sam="$WORK/${tag}.sam"
  [[ -s "$sam" ]] && { echo "[$(date)] $tag SAM present; skipping"; return; }
  echo "[$(date)] bwa aln ($tag)"
  if [[ "$tag" == old ]]; then
    bwa_old aln -t "$THREADS" "$ref" "$SUB" > "$sai"
    bwa_old samse "$ref" "$sai" "$SUB" > "$sam.tmp"
  else
    "$BWA_NEW" aln -t "$THREADS" "$ref" "$SUB" > "$sai"
    "$BWA_NEW" samse "$ref" "$sai" "$SUB" > "$sam.tmp"
  fi
  mv -f "$sam.tmp" "$sam"
}
align old "$REF_OLD"
align new "$REF_NEW"

# --- compare ----------------------------------------------------------------
echo "[$(date)] comparing placements"
REPORT="$OUT/bwa_aln_version_diff.${SAMPLE}.txt"
python3.12 - "$WORK/old.sam" "$WORK/new.sam" > "$REPORT" <<'PY'
import sys, collections

def load(path):
    recs = {}
    tags_of = {}
    with open(path) as fh:
        for line in fh:
            if line.startswith("@"):
                continue
            f = line.rstrip("\n").split("\t")
            if len(f) < 11:
                continue
            name, flag, chrom, pos, mapq = f[0], int(f[1]), f[2], int(f[3]), int(f[4])
            tags = {}
            for t in f[11:]:
                parts = t.split(":", 2)
                if len(parts) == 3:
                    tags[parts[0]] = parts[2]
            recs[name] = (flag & 4 == 0, chrom, pos, mapq)
            tags_of[name] = tags
    return recs, tags_of

old, old_t = load(sys.argv[1])
new, new_t = load(sys.argv[2])
names = set(old) | set(new)

def summarise(label, recs, tags):
    mapped = [n for n in recs if recs[n][0]]
    print(f"{label}:")
    print(f"  records            : {len(recs)}")
    print(f"  mapped             : {len(mapped)} ({100*len(mapped)/max(len(recs),1):.2f}%)")
    mq = collections.Counter()
    for n in mapped:
        q = recs[n][3]
        mq["0" if q == 0 else "1-9" if q < 10 else "10-28" if q < 29 else ">=29"] += 1
    print(f"  MAPQ buckets       : {dict(sorted(mq.items()))}")
    for tag in ("XT", "X0", "X1"):
        c = collections.Counter(tags[n].get(tag, "-") for n in mapped)
        top = dict(sorted(c.items(), key=lambda kv: -kv[1])[:6])
        print(f"  {tag} distribution   : {top}")

summarise("bwa 0.6.2 (RelocaTE2)", old, old_t)
print()
summarise("bwa 0.7.19 (RelocaTE3)", new, new_t)

print()
print("Head-to-head:")
both_mapped = same_pos = diff_pos = only_old = only_new = neither = 0
mapq_cross = collections.Counter()
xt_cross = collections.Counter()
for n in names:
    o = old.get(n); w = new.get(n)
    om = bool(o and o[0]); wm = bool(w and w[0])
    if om and wm:
        both_mapped += 1
        if o[1] == w[1] and o[2] == w[2]:
            same_pos += 1
        else:
            diff_pos += 1
        # does the read-admission gate see a different answer?
        og = old_t[n].get("XT", "-"); wg = new_t[n].get("XT", "-")
        if og != wg:
            xt_cross[f"{og}->{wg}"] += 1
        oq, wq = o[3], w[3]
        if (oq == 0) != (wq == 0):
            mapq_cross[f"MAPQ0 {'old' if oq==0 else 'new'} only"] += 1
    elif om:
        only_old += 1
    elif wm:
        only_new += 1
    else:
        neither += 1
print(f"  reads compared     : {len(names)}")
print(f"  mapped by both     : {both_mapped}  (same position {same_pos}, different {diff_pos})")
print(f"  mapped by 0.6.2 only : {only_old}")
print(f"  mapped by 0.7.19 only: {only_new}")
print(f"  unmapped by both   : {neither}")
print(f"  XT tag disagreements : {sum(xt_cross.values())}  {dict(xt_cross.most_common(6))}")
print(f"  MAPQ-zero disagreements : {dict(mapq_cross)}")
print()
print("Interpretation: RelocaTE3's _passes_quality admits a non-properly-paired read")
print("only when XT == 'U' and X1 <= 3, so XT disagreements change which reads")
print("become evidence. Large 'mapped by ... only' or XT-disagreement counts mean the")
print("benchmark comparison is not aligner-controlled at the genome-placement stage.")
PY

echo "[$(date)] done. Report:"
echo "  $REPORT"
cat "$REPORT"
