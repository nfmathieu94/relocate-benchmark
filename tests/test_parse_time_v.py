import csv, sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scoring.parse_time_v import main


TIME_V = """\tCommand being timed: "relocate3"
\tUser time (seconds): 12.34
\tSystem time (seconds): 5.67
\tPercent of CPU this job got: 250%
\tElapsed (wall clock) time (h:mm:ss or m:ss): 1:23.45
\tMaximum resident set size (kbytes): 2048000
\tExit status: 0
"""

TIME_V_HMMSS = """\tUser time (seconds): 1.0
\tSystem time (seconds): 2.0
\tPercent of CPU this job got: 99%
\tElapsed (wall clock) time (h:mm:ss or m:ss): 1:02:03
\tMaximum resident set size (kbytes): 100
"""


class TestParseTimeV(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp())

    def _run(self, text, **over):
        tv = self.d / "time.txt"
        tv.write_text(text)
        out = self.d / "out.tsv"
        argv = [
            "--time-v", str(tv),
            "--sample", over.get("sample", "cov5x_rep1"),
            "--caller", over.get("caller", "relocate3"),
            "--coverage", over.get("coverage", "5"),
            "--replicate", over.get("replicate", "1"),
            "--out", str(out),
        ]
        rc = main(argv)
        self.assertEqual(rc, 0)
        with open(out) as fh:
            rows = list(csv.DictReader(fh, delimiter="\t"))
        return rows

    def test_single_row_and_values(self):
        rows = self._run(TIME_V)
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["caller"], "relocate3")
        self.assertEqual(row["sample"], "cov5x_rep1")
        self.assertEqual(row["coverage"], "5")
        self.assertEqual(row["replicate"], "1")
        self.assertAlmostEqual(float(row["wall_seconds"]), 83.45, places=2)
        self.assertEqual(row["max_rss_kb"], "2048000")
        self.assertEqual(float(row["user_seconds"]), 12.34)
        self.assertEqual(float(row["system_seconds"]), 5.67)
        self.assertEqual(row["percent_cpu"], "250%")

    def test_caller_is_first_column(self):
        tv = self.d / "t.txt"
        tv.write_text(TIME_V)
        out = self.d / "o.tsv"
        main(["--time-v", str(tv), "--sample", "s", "--caller", "relocate2",
              "--coverage", "5", "--replicate", "1", "--out", str(out)])
        header = out.read_text().splitlines()[0].split("\t")
        self.assertEqual(header[0], "caller")

    def test_hmmss_wall_clock(self):
        rows = self._run(TIME_V_HMMSS)
        self.assertAlmostEqual(float(rows[0]["wall_seconds"]), 3723.0, places=2)


if __name__ == "__main__":
    unittest.main()
