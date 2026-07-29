"""Plain-language guide to the benchmark datasets, metrics, and plots."""
from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.runtime import configure_page, load_bundle


def main() -> None:
    configure_page("Information")
    # Render the shared sidebar dataset selector so navigation is consistent; the
    # content below describes every dataset regardless of the active selection.
    load_bundle()

    st.title("Information & metrics glossary")
    st.caption(
        "What the benchmark measures, what each dataset contains, and how to read "
        "every metric and plot. Written to be self-contained for a new reader."
    )

    st.header("What this benchmark does")
    st.markdown(
        """
This dashboard compares transposable-element (TE) **non-reference insertion
callers** — RelocaTE2 and several RelocaTE3 aligner variants — on **simulated**
short-read data where the truth is known exactly. Reads are simulated from
genomes carrying inserted TEs at known positions, zygosities, and target-site
duplications (TSDs); each caller is run on those reads, and its calls are scored
against the truth. Because the truth is exact, every metric below is a direct
measurement rather than an estimate.

Each caller name encodes its aligner choices as **`<TE-search aligner>/<genome
aligner>`** — e.g. `relocate3-blat/bwaaln` uses BLAT to find TE-containing reads
and `bwa aln` to place the trimmed flanks on the genome.
"""
    )

    st.header("The two datasets")
    st.markdown(
        "Pick a dataset from the **sidebar selector**. Only one dataset is shown at "
        "a time, so metrics from different datasets are never mixed."
    )
    with st.expander("mPing panel — single-family (deep dive)", expanded=True):
        st.markdown(
            """
A focused panel of **mPing** insertions (a ~430 bp rice MITE in the
PIF/Harbinger superfamily, canonical 3 bp `TWA` TSD). It is the high-resolution
case for studying one well-behaved element in detail.
"""
        )
    with st.expander("riceTElib panel — multi-TE (breadth)", expanded=True):
        st.markdown(
            """
A realistic panel spanning **10 curated TE groups, 50 insertions each (500 per
sample)**, drawn from a rice TE library, with per-family TSD biology:

| TE group | Class | Order | Modeled TSD |
| --- | --- | --- | --- |
| LTR_Copia | I (retro) | LTR | 5 bp |
| LTR_Gypsy | I (retro) | LTR | 5 bp |
| LINE | I (retro) | LINE | variable 7–20 bp |
| SINE | I (retro) | SINE | variable 7–20 bp |
| PIF_Harbinger | II (DNA) | TIR | 3 bp (`TWA`) |
| Tc1_Mariner | II (DNA) | TIR | 2 bp (`TA`) |
| MULE | II (DNA) | TIR | 9 bp |
| hAT | II (DNA) | TIR | 8 bp |
| CACTA | II (DNA) | TIR | 3 bp |
| Helitron | II (DNA) | Helitron | **none** (A\\|T target, no TSD) |

Class I (retro) = 200 events, Class II (DNA) = 300. Only this dataset has the
TE-group metadata used on the **TE groups** page.
"""
        )
    st.markdown(
        """
**Both panels share the same sample design:**

- **9 samples** = 3 coverages (**5×, 15×, 30×**) × 3 replicates.
- **5 biological states per sample, 100 events each:**
  - **homozygous** (both haplotypes carry the insertion; expected VAF 1.0),
  - **heterozygous** (one haplotype; expected VAF 0.5),
  - **somatic** at three cellular fractions — VAF **0.2, 0.1, 0.05** — modeling
    insertions present in only a subset of cells (few supporting reads).
"""
    )

    st.header("How a call is judged")
    st.markdown(
        """
A predicted insertion is a **true positive (matched call)** when it falls within
a small position window (default **±10 bp**) of a truth event; otherwise it is a
**false positive**. A truth event is **detected** if some call matches it.
"Detected" refers to truth events found; "matched call" refers to predictions
that hit truth — they differ when a caller emits several calls near one event.
"""
    )

    st.header("Metrics glossary")
    _metric(
        "Detection recall",
        "detected truth events / total truth events",
        "The fraction of real insertions the caller found. The headline "
        "sensitivity metric. Reported pooled (summed counts) across the active "
        "slice, so it is a true event-weighted rate, not an average of ratios.",
    )
    _metric(
        "Somatic recall",
        "detection recall restricted to somatic insertions",
        "Recall on the low-VAF somatic events (fractions 0.05–0.2). These have few "
        "supporting reads, so this is the hardest, most discriminating sensitivity "
        "test. Shown by cellular fraction on the Somatic page.",
    )
    _metric(
        "Genotype-status accuracy (given detected)",
        "status-correct detected events / detected events",
        "Among the insertions a caller detected, the fraction whose zygosity/state "
        "(homozygous, heterozygous, or somatic) was called correctly. It is "
        "**conditional on detection** — it says nothing about missed events, so "
        "always read it next to recall.",
    )
    _metric(
        "Exact-TSD accuracy (given detected)",
        "detected events with exact-matching TSD / detected events",
        "Among detected insertions, the fraction where the caller's inferred TSD "
        "string exactly equals the truth TSD. Also conditional on detection. "
        "**Interpret per TE group:** elements with no TSD (Helitron) can never "
        "score here, so a caller that detects many Helitrons is penalized on the "
        "*pooled* number even though it is accurate on TSD-bearing elements — "
        "compare groups on the TE groups page rather than the single overall value.",
    )
    _metric(
        "Overall precision",
        "matched calls / total calls",
        "Of everything the caller reported, the fraction that is a real insertion. "
        "The complement of the false-discovery rate. A per-sample measure over all "
        "calls; it is not attributed to individual TE groups (an unmatched call "
        "has no unambiguous truth group).",
    )
    _metric(
        "False-discovery rate (FDR)",
        "false-positive calls / total calls  =  1 − precision",
        "The fraction of reported calls that are spurious. Lower is better.",
    )
    _metric(
        "False-positive calls",
        "count of calls matching no truth event",
        "The raw number of spurious calls per sample (before dividing by anything). "
        "Useful to compare absolute noise levels across callers and coverages.",
    )
    st.markdown(
        """
**A note on "false-positive rate" (FPR).** A true FPR — false positives divided
by the number of true-negative opportunities — is **not computed here**, because
there is no defined negative set (an insertion can be called at effectively any
genomic position, so there is no finite true-negative denominator). Use
**FDR** and **false-positive counts** as the specificity measures. A dedicated
FPR would require negative-control genomes with no simulated insertions.
"""
    )

    st.header("How to read the plots")
    _plot(
        "Overview & Accuracy — coverage curves",
        "Lines show a metric versus coverage (5×/15×/30×), one colour per caller, "
        "faceted by biological class. Higher/steeper is better; the y-axis is 0–100%.",
    )
    _plot(
        "Direct caller comparison (head-to-head) — grouped bars",
        "Grouped bars compare callers side by side for one metric. **Each bar is "
        "the mean detection recall across the active slice** (replicates × groups × "
        "fractions), on a 0–100% axis. If a bar ever exceeds the tick labels, the "
        "underlying rows are not being averaged — the bars are means, not sums.",
    )
    _plot(
        "Somatic recall — cellular-fraction curves",
        "Recall versus cellular fraction (0.05 → 0.2), faceted by coverage. This "
        "isolates the low-VAF regime where callers differ most.",
    )
    _plot(
        "TE groups — faceted curves + heatmap (riceTElib only)",
        "Small multiples show a metric versus coverage for each of the 10 TE "
        "groups (shared axes: one 'Coverage (x)' title, one metric title). The "
        "heatmap summarizes the mean per caller × group. Read groups separately — "
        "Class I retroelements (LTR/LINE/SINE) and no-TSD Helitrons behave very "
        "differently from TIR DNA transposons.",
    )
    _plot(
        "Resources — runtime & memory",
        "Mean wall-clock time and peak memory per caller and coverage. Useful "
        "context, independent of accuracy.",
    )

    st.info(
        "Every number here traces back to the authoritative per-sample count "
        "tables (`correctness.tsv`, `precision.tsv`); the plots only aggregate "
        "those counts. See the Provenance page for the exact source files."
    )


def _metric(name: str, formula: str, description: str) -> None:
    st.subheader(name)
    st.markdown(f"**Definition:** `{formula}`\n\n{description}")


def _plot(name: str, description: str) -> None:
    st.markdown(f"**{name}.** {description}")


if __name__ == "__main__":
    main()
