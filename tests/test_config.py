import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lib.config import load_config


class TestConfig(unittest.TestCase):
    def test_interpolation(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write('[dataset]\nroot = "/data"\nref = "${dataset.root}/ref.fa"\n')
            path = fh.name
        cfg = load_config(path)
        self.assertEqual(cfg["dataset"]["ref"], "/data/ref.fa")

    def test_nested_and_plain(self):
        with tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False) as fh:
            fh.write('[a]\nx = "1"\n[b]\ny = "${a.x}-${a.x}"\nz = "plain"\n')
            path = fh.name
        cfg = load_config(path)
        self.assertEqual(cfg["b"]["y"], "1-1")
        self.assertEqual(cfg["b"]["z"], "plain")


if __name__ == "__main__":
    unittest.main()
