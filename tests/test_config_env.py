import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Load pipeline/config_env.py by path (pipeline/ is not an importable package).
_spec = importlib.util.spec_from_file_location(
    "config_env", REPO_ROOT / "pipeline" / "config_env.py"
)
config_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config_env)

MANIFEST = (
    "sample\tcoverage\treplicate\tr1\tr2\tcontrol_r1\tcontrol_r2\n"
    "s1\t5\t1\treads/s1/R1.fastq\treads/s1/R2.fastq\treads/s1c/R1.fastq\treads/s1c/R2.fastq\n"
    "s2\t15\t2\treads/s2/R1.fastq\treads/s2/R2.fastq\treads/s2c/R1.fastq\treads/s2c/R2.fastq\n"
)


def _make_config(tmp: Path) -> Path:
    panel_root = tmp / "panel"
    panel_root.mkdir()
    (panel_root / "panel_manifest.tsv").write_text(MANIFEST)

    cfg = tmp / "benchmark.toml"
    cfg.write_text(
        f"""
[dataset]
panel_root   = "{panel_root}"
reference    = "/ref/genome.fa"
te_library   = "/te/lib.fa"
repeatmasker = "/rm/out.out"
te_name      = "mPing"

[run]
work_root = "runs"
threads   = 8

[scoring]
match_window = 10

[callers.relocate2]
enabled  = true
adapter  = "callers/relocate2"
aligner  = "blat"
size     = 250
mismatch = 2

[callers.relocate3]
enabled = true
adapter = "callers/relocate3"
repo    = "/some/rt3/repo"
tsd     = "..."
"""
    )
    return cfg, panel_root


class TestConfigEnv(unittest.TestCase):
    def test_globals(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(["--config", str(cfg), "globals"])
            self.assertIn("REFERENCE='/ref/genome.fa'", out)
            self.assertIn("TE_LIBRARY='/te/lib.fa'", out)
            self.assertIn("REPEATMASKER='/rm/out.out'", out)
            self.assertIn("TE_NAME='mPing'", out)
            self.assertIn("PANEL_ROOT=", out)
            self.assertIn("WORK_ROOT='runs'", out)
            self.assertIn("THREADS='8'", out)
            self.assertIn("MATCH_WINDOW='10'", out)

    def test_callers_sorted(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(["--config", str(cfg), "callers"])
            names = out.split()
            self.assertEqual(names, ["relocate2", "relocate3"])

    def test_caller_env_relocate3(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(["--config", str(cfg), "caller-env", "relocate3"])
            self.assertIn("RT3_REPO='/some/rt3/repo'", out)
            self.assertIn("TSD_PATTERN='...'", out)

    def test_caller_env_relocate2(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(["--config", str(cfg), "caller-env", "relocate2"])
            self.assertIn("RT2_ALIGNER='blat'", out)
            self.assertIn("RT2_SIZE='250'", out)
            self.assertIn("RT2_MISMATCH='2'", out)

    def test_caller_env_unknown(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(["--config", str(cfg), "caller-env", "nope"])
            self.assertEqual(out.strip(), "")

    def test_tasks(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, panel_root = _make_config(Path(td))
            out = config_env.run(["--config", str(cfg), "tasks"])
            lines = [ln for ln in out.splitlines() if ln]
            self.assertEqual(len(lines), 4)  # 2 callers x 2 samples

            # Outer loop = callers sorted, inner = manifest order.
            first = lines[0].split("\t")
            self.assertEqual(first[0], "relocate2")
            self.assertEqual(first[1], "s1")
            self.assertEqual(first[2], "5")
            self.assertEqual(first[3], "1")
            self.assertEqual(first[4], str(panel_root / "reads/s1/R1.fastq"))
            self.assertEqual(first[5], str(panel_root / "reads/s1/R2.fastq"))

            self.assertTrue(lines[0].startswith("relocate2\ts1"))
            self.assertTrue(lines[1].startswith("relocate2\ts2"))
            self.assertTrue(lines[2].startswith("relocate3\ts1"))
            self.assertTrue(lines[3].startswith("relocate3\ts2"))

    def test_count(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(["--config", str(cfg), "count"])
            self.assertEqual(out.strip(), "4")

    # Canonical task order (2 callers x 2 samples):
    #   0: relocate2 s1 cov5  rep1
    #   1: relocate2 s2 cov15 rep2
    #   2: relocate3 s1 cov5  rep1
    #   3: relocate3 s2 cov15 rep2
    def test_indices_no_filter(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(["--config", str(cfg), "indices"])
            self.assertEqual(out.strip(), "0,1,2,3")

    def test_indices_caller(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(
                ["--config", str(cfg), "indices", "--caller", "relocate3"]
            )
            self.assertEqual(out.strip(), "2,3")

    def test_indices_coverage(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(
                ["--config", str(cfg), "indices", "--coverage", "5"]
            )
            self.assertEqual(out.strip(), "0,2")

    def test_indices_combined(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(
                [
                    "--config",
                    str(cfg),
                    "indices",
                    "--caller",
                    "relocate3",
                    "--coverage",
                    "15",
                ]
            )
            self.assertEqual(out.strip(), "3")

    def test_indices_sample(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(
                ["--config", str(cfg), "indices", "--sample", "s2"]
            )
            self.assertEqual(out.strip(), "1,3")

    def test_indices_replicate(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(
                ["--config", str(cfg), "indices", "--replicate", "1"]
            )
            self.assertEqual(out.strip(), "0,2")

    def test_indices_comma_list(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(
                ["--config", str(cfg), "indices", "--coverage", "5,15"]
            )
            self.assertEqual(out.strip(), "0,1,2,3")

    def test_indices_no_match(self):
        with tempfile.TemporaryDirectory() as td:
            cfg, _ = _make_config(Path(td))
            out = config_env.run(
                ["--config", str(cfg), "indices", "--caller", "nope"]
            )
            self.assertEqual(out.strip(), "")


def _make_variant_config(tmp: Path):
    panel_root = tmp / "panel"
    panel_root.mkdir()
    (panel_root / "panel_manifest.tsv").write_text(MANIFEST)
    cfg = tmp / "benchmark.toml"
    cfg.write_text(
        f"""
[dataset]
panel_root   = "{panel_root}"
reference    = "/ref/genome.fa"
te_library   = "/te/lib.fa"
repeatmasker = "/rm/out.out"
te_name      = "mPing"

[run]
work_root = "runs"
threads   = 8

[scoring]
match_window = 10

[callers.relocate3-bwa-bwa]
enabled        = true
adapter        = "callers/relocate3"
repo           = "/some/rt3/repo"
tsd            = "..."
te_aligner     = "bwa"
genome_aligner = "bwa"
label          = "RelocaTE3-bwa/bwa"
"""
    )
    return cfg


class TestAlignerVariants(unittest.TestCase):
    def test_caller_env_variant_has_aligners(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = _make_variant_config(Path(td))
            out = config_env.run(["--config", str(cfg), "caller-env", "relocate3-bwa-bwa"])
            self.assertIn("RT3_REPO='/some/rt3/repo'", out)
            self.assertIn("RT3_TE_ALIGNER='bwa'", out)
            self.assertIn("RT3_GENOME_ALIGNER='bwa'", out)

    def test_adapter_command(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = _make_variant_config(Path(td))
            out = config_env.run(["--config", str(cfg), "adapter", "relocate3-bwa-bwa"])
            self.assertEqual(out.strip(), "callers/relocate3")

    def test_adapter_default(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = _make_variant_config(Path(td))
            # a caller with no explicit adapter defaults to callers/<name>
            out = config_env.run(["--config", str(cfg), "adapter", "somecaller"])
            self.assertEqual(out.strip(), "callers/somecaller")

    def test_labels_command(self):
        with tempfile.TemporaryDirectory() as td:
            cfg = _make_variant_config(Path(td))
            out = config_env.run(["--config", str(cfg), "labels"])
            self.assertIn("relocate3-bwa-bwa\tRelocaTE3-bwa/bwa", out)

    def test_pretty_caller(self):
        self.assertEqual(config_env.pretty_caller("relocate2"), "RelocaTE2")
        self.assertEqual(
            config_env.pretty_caller("relocate3-bwa-bwa"), "RelocaTE3-bwa/bwa"
        )
        self.assertEqual(
            config_env.pretty_caller("relocate3-minimap2-minimap2"),
            "RelocaTE3-minimap2/minimap2",
        )


class TestMultipleDatasets(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.panels = {}
        for name in ("mping", "ricetelib"):
            panel = root / name
            panel.mkdir()
            (panel / "panel_manifest.tsv").write_text(MANIFEST)
            self.panels[name] = panel
        self.config = root / "multi.toml"
        self.config.write_text(
            f"""
[benchmark]
default_dataset = "mping"

[datasets.mping]
label = "mPing only"
panel_root = "{self.panels['mping']}"
reference = "/ref.fa"
te_library = "/mping.fa"
repeatmasker = "/rm.out"
te_name = "mPing"

[datasets.ricetelib]
label = "riceTElib multi-TE"
panel_root = "{self.panels['ricetelib']}"
reference = "/ref.fa"
te_library = "/rice.fa"
repeatmasker = "cache/full.out"
repeatmasker_gff = "/full.gff"
te_name = "riceTElib"

[run]
work_root = "runs"
report_root = "reports"
truth_root = "truth"
threads = 8

[scoring]
match_window = 10

[callers.relocate2]
enabled = true
adapter = "callers/relocate2"
"""
        )

    def tearDown(self):
        self.temp.cleanup()

    def test_default_and_full_dataset_selection(self):
        default = config_env.run(["--config", str(self.config), "datasets"])
        self.assertTrue(default.startswith("mping\tmPing only\t"))
        full = config_env.run(
            ["--config", str(self.config), "--dataset", "full", "datasets"]
        )
        self.assertEqual(
            [line.split("\t")[0] for line in full.splitlines()],
            ["mping", "ricetelib"],
        )

    def test_tasks_are_dataset_qualified(self):
        output = config_env.run(
            ["--config", str(self.config), "--dataset", "full", "tasks"]
        )
        rows = [line.split("\t") for line in output.splitlines()]
        self.assertEqual(len(rows), 4)
        self.assertEqual([row[0] for row in rows], ["mping", "mping", "ricetelib", "ricetelib"])
        self.assertEqual(rows[0][1:3], ["relocate2", "s1"])

    def test_dataset_env_has_isolated_roots(self):
        output = config_env.run(
            ["--config", str(self.config), "dataset-env", "ricetelib"]
        )
        self.assertIn("DATASET_WORK_ROOT='runs/ricetelib'", output)
        self.assertIn("DATASET_REPORT_ROOT='reports/datasets/ricetelib'", output)
        self.assertIn("DATASET_TRUTH_ROOT='truth/ricetelib'", output)
        self.assertIn("REPEATMASKER_GFF='/full.gff'", output)
        self.assertIn("TE_LIBRARY_SOURCE='/rice.fa'", output)
        self.assertIn(
            "TE_LIBRARY='cache/te_libraries/ricetelib/library.fa'", output
        )


if __name__ == "__main__":
    unittest.main()
