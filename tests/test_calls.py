import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.calls import parse_characterized_txt, NORMALIZED_HEADER


class TestCalls(unittest.TestCase):
    def test_parse(self):
        text = (
            "strain\tTE\tTSD\tchromosome.pos\tstrand\tavg_flankers\tspanners\tstatus\n"
            "S1\tmPing\tTTA\tChr1:1000..1002\t+\t5\t2\thomozygous\n"
            "S1\tmPing\tTAA\tChr1:2000..2002\t-\t3\t0\tsomatic\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(text); path = fh.name
        rows = list(parse_characterized_txt(path, caller="relocate3", sample="S1"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["chrom"], "Chr1")
        self.assertEqual(rows[0]["position"], 1000)
        self.assertEqual(rows[0]["te_family"], "mPing")
        self.assertEqual(rows[0]["status"], "homozygous")
        self.assertEqual(rows[0]["caller"], "relocate3")
        self.assertEqual(rows[1]["position"], 2000)

    def test_sample_named_strain_not_dropped(self):
        # Header skip must not silently drop a data row whose strain name
        # starts with "strain"; the coord column disambiguates header vs data.
        text = (
            "strain\tTE\tTSD\tchromosome.pos\tstrand\tavg_flankers\tspanners\tstatus\n"
            "strainA\tmPing\tTTA\tChr1:1000..1002\t+\t5\t2\thomozygous\n"
        )
        with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as fh:
            fh.write(text); path = fh.name
        rows = list(parse_characterized_txt(path, caller="relocate2", sample="strainA"))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["position"], 1000)

    def test_header_constant(self):
        self.assertEqual(
            NORMALIZED_HEADER,
            ["chrom", "position", "te_family", "tsd", "strand", "status", "caller", "sample"],
        )


if __name__ == "__main__":
    unittest.main()
