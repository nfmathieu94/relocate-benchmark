"""The checkpoint source manifest must match this tree's benchmark files.

callers/relocate3-checkpoint-213a0df/verify_source.py fails every checkpoint
task when a pinned benchmark file changed; this catches a missing re-pin at
test time instead. RelocaTE3 source hashes (``source_sha256``) belong to
another repository and are not checked here.
"""
import hashlib
import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "config" / "checkpoint-213a0df.source.json"
PRE_DEV_REPLAY = REPO_ROOT / "config" / "checkpoint-213a0df.pre-dev-replay.source.json"


class CheckpointSourceManifestTest(unittest.TestCase):
    def test_benchmark_hashes_match_working_tree(self):
        pinned = json.loads(MANIFEST.read_text())["benchmark_sha256"]
        self.assertTrue(pinned)
        for path, digest in sorted(pinned.items()):
            with self.subTest(path=path):
                # Same hashing as verify_source.py: sha256 of the raw bytes.
                actual = hashlib.sha256((REPO_ROOT / path).read_bytes()).hexdigest()
                self.assertEqual(actual, digest, f"re-pin {path} in {MANIFEST.name}")

    def test_repin_kept_relocate3_pin(self):
        # Re-pins refresh benchmark-side hashes only; the RelocaTE3 pin is fixed.
        current = json.loads(MANIFEST.read_text())
        original = json.loads(PRE_DEV_REPLAY.read_text())
        for key in ("repo", "revision", "source_sha256"):
            with self.subTest(key=key):
                self.assertEqual(current[key], original[key])
        self.assertEqual(set(current["benchmark_sha256"]),
                         set(original["benchmark_sha256"]))


if __name__ == "__main__":
    unittest.main()
