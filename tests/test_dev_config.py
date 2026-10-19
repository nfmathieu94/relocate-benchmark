"""The committed development-tier config and replay manifest."""
import importlib.util
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "config_env", REPO_ROOT / "pipeline" / "config_env.py")
config_env = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(config_env)
CONFIG = REPO_ROOT / "config" / "benchmark.dev.toml"
MANIFEST = REPO_ROOT / "config" / "replay" / "checkpoint-213a0df.json"


class DevConfigTest(unittest.TestCase):
    def run_mode(self, *args):
        return config_env.run(["--config", str(CONFIG), *args])

    def test_only_frozen_r2_and_replay_r3_are_enabled(self):
        self.assertEqual(self.run_mode("callers").split(),
                         ["relocate2-frozen", "relocate3-replay"])

    def test_outputs_are_isolated_and_scored_like_the_checkpoint(self):
        globals_ = self.run_mode("globals")
        self.assertIn("WORK_ROOT='runs/dev'", globals_)
        self.assertIn("REPORT_ROOT='reports/dev'", globals_)
        self.assertIn("SCORING_COORDINATE_POLICY='tsd-interval'", globals_)

    def test_replay_matches_checkpoint_parity_settings(self):
        env = self.run_mode("caller-env", "relocate3-replay")
        for expected in ("RT3_GENOME_ALIGNER='bwaaln'", "TSD_PATTERN='UNK'",
                         "RT3_REQUIRE_BOTH_JUNCTIONS='1'",
                         "RT3_REPLAY_MANIFEST='config/replay/checkpoint-213a0df.json'"):
            self.assertIn(expected, env)

    def test_manifest_covers_every_dataset_from_the_checkpoint(self):
        data = json.loads(MANIFEST.read_text())
        self.assertEqual(data["source_caller"], "relocate3-blat-bwaaln")
        self.assertEqual(data["run_root"], "runs/checkpoint-213a0df")
        self.assertTrue(data["source_rev"].startswith("213a0df"))
        self.assertEqual(data["source_rev"],
                         "213a0df99af71a57fffad726138593b152fc9a77")
        self.assertEqual(data["te_aligner"], "blat")
        datasets = self.run_mode("--dataset", "full", "datasets")
        names = {line.split("\t")[0] for line in datasets.splitlines()}
        self.assertEqual(set(data["te_library_sha256"]), names)

    def test_replay_te_aligner_equals_manifest_te_aligner(self):
        data = json.loads(MANIFEST.read_text())
        env = self.run_mode("caller-env", "relocate3-replay")
        self.assertIn(f"RT3_TE_ALIGNER='{data['te_aligner']}'", env)
