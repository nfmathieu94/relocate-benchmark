# 2026-07-24 — Why RT3 trails RT2 on TSD-exact (and what it takes for R3 ≥ R2)

## Purpose
Diagnose the remaining RelocaTE3 vs RelocaTE2 gap after the mate-anchoring fix,
to decide the path to "R3 ≥ R2" before a v1 release. Question posed: is the gap
the aligner, and should RT3 switch to BLAT+bwa like RT2?

## Current status (fresh full rerun, all 9 samples)
Detection **recall** is ~identical across all callers incl. RT2 (somatic ~0.44) —
the low somatic recall is the low-VAF data (~1–2 reads/junction), not the caller.
The entire gap is **TSD-exact on detected events**:

| caller | germline tsd-exact | somatic tsd-exact |
| --- | --- | --- |
| relocate2 | 0.996 | 0.961 |
| relocate3-minimap2 | 0.951 | 0.808 |
| relocate3-bowtie2-bwa | 0.948 | 0.808 |
| relocate3-bwa-bwa | 0.897 | 0.702 |

## Decisions / logic (evidence)
The gap decomposes into two parts — **neither is a general aligner problem**:

1. **Scoring asymmetry (most of the visible gap).** RT2's `characterize` drops
   every one-sided locus (412 rows, all resolved). RT3 keeps them as `tsd=UNK`
   insertions (435 rows, 31 UNK), which score as detections-with-wrong-TSD.
   Score RT3 the same way (exclude UNK) and tsd-exact jumps to 0.94–0.98,
   matching/beating RT2. bwa-bwa resolved somatic = 0.982 > RT2 0.961 (why it
   "looked best"). Every one of 22 sampled detected-but-UNK somatic events was
   **single-sided** (R=0 or L=0) — RT3 found one junction, not both.

2. **Second-junction recovery (the real deficit).** At 10/22 UNK loci, RT2 had
   reads on BOTH sides where RT3 had only one (e.g. 8377730: RT2 R=3 L=1, RT3
   R=0 L=2) → RT2 resolved a real TSD. The reads exist; RT3's pipeline missed
   the second junction. Resolved-only recall: RT3 somatic 0.373 vs RT2 0.441.
   RT2 does NOT resolve one-sided either — it emits `insufficient_data`/`singleton`.

Dropping UNK alone is **not** enough for R3 ≥ R2: it fixes tsd-exact but pushes
resolved-recall below RT2. Parity on BOTH metrics requires converting single-sided
detections into resolved two-sided ones (second-junction recovery). This is a
short-flank alignment-sensitivity problem, which is where BLAT *may* help — but as
a targeted second-junction tool, not a blanket aligner swap. RT3's `BlatBackend`
cannot do genome alignment today (`map_genome` raises).

## Plan (priority order)
1. **bwa mate-suffix fix** (done — see RT3 branch): bwa mem strips `/1 /2`, so the
   bwa TE-aligner produced 0 paired flanks → most UNK. Restore the suffix per side.
   bwa-bwa has the best resolved-TSD (0.982) but worst resolved-recall (0.317)
   purely from this; fixing it should give the strongest single variant.
2. Diagnose whether minimap2 misses second junctions at the **TE-search** step or
   the **flank→genome** step (tells us if/where BLAT helps) — cheap, before any
   BLAT implementation.
3. If step 2 points to alignment sensitivity: implement BLAT flank→genome in RT3.
4. Decide RT3's one-sided-call policy (emit UNK vs. drop like RT2) for a fair,
   apples-to-apples comparison.

## Commands
```
# per-caller, per-class recall + tsd-exact (as-is vs excluding UNK)
# see analysis in scoring/ per_sample matches.tsv; reproduced via awk over
# reports/per_sample/<caller>/*/matches.tsv (matched==1 filters to detected).
```

## Next steps
Rerun the benchmark after the bwa mate-suffix fix merges + re-pin; expect bwa-bwa
UNK to drop sharply (170 → ~78 at cov30x) and its resolved-recall to rise.
