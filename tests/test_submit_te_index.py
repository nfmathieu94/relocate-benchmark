"""submit_benchmark.sh activates RelocaTE3's env only to build TE indexes.

BLAT needs no TE index, so a blat-only selection (the dev tier, the default
callers) must not activate pixi on the login node. The script is never run
here: the selection function is extracted from its text and run alone.
"""
import re
import subprocess
import unittest
from pathlib import Path

SUBMIT = Path(__file__).resolve().parents[1] / "pipeline" / "submit_benchmark.sh"
FUNCTION = "te_aligners_needing_index"


def function_source() -> str:
    text = SUBMIT.read_text()
    match = re.search(rf"^{FUNCTION}\(\) \{{\n.*?^\}}\n", text, re.S | re.M)
    if match is None:
        raise AssertionError(f"{FUNCTION}() not defined in {SUBMIT}")
    return match.group(0)


def needing_index(*aligners: str) -> list[str]:
    script = function_source() + f"{FUNCTION}\n"
    result = subprocess.run(["bash", "-c", script], input="".join(f"{a}\n" for a in aligners),
                            capture_output=True, text=True, check=True)
    return result.stdout.split()


class TeIndexSelectionTest(unittest.TestCase):
    def test_blat_only_needs_no_index(self):
        self.assertEqual(needing_index("blat", "blat"), [])

    def test_no_aligners_needs_no_index(self):
        self.assertEqual(needing_index(), [])
        self.assertEqual(needing_index(""), [])

    def test_indexed_aligners_are_kept_unique_and_sorted(self):
        self.assertEqual(needing_index("minimap2", "blat", "bwa", "minimap2", "bowtie2"),
                         ["bowtie2", "bwa", "minimap2"])

    def test_trailing_blat_exits_zero_under_pipefail(self):
        script = "set -euo pipefail\n" + function_source() + \
            f"printf 'bwa\\nblat\\n' | {FUNCTION}\n"
        result = subprocess.run(["bash", "-c", script], capture_output=True, text=True)
        self.assertEqual((result.returncode, result.stdout), (0, "bwa\n"))

    def test_unknown_aligner_is_kept_for_its_warning(self):
        self.assertEqual(needing_index("blat", "novel"), ["novel"])

    def test_env_is_sourced_only_when_an_index_is_needed(self):
        text = SUBMIT.read_text()
        self.assertEqual(text.count("source callers/relocate3/env.sh"), 1)
        guard = text.index('if ((${#INDEX_ALIGNERS[@]})); then')
        source = text.index("source callers/relocate3/env.sh")
        self.assertLess(guard, source)
        self.assertNotIn("\nfi\n", text[guard:source])


if __name__ == "__main__":
    unittest.main()
