"""End-to-end test of the RelocaTE3 adapter's replay branch with stub tools."""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_cache", REPO_ROOT / "callers" / "relocate3-replay" / "check_cache.py")
check_cache = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check_cache)
from test_replay_cache import make_cache, make_rt3_repo  # noqa: E402

STUB_RELOCATE3 = r'''#!{python}
import json, os, sys
from pathlib import Path
args = sys.argv[1:]
with open(os.environ["STUB_LOG"], "a") as log:
    log.write(json.dumps(args) + "\n")
def opt(*names):
    for name in names:
        if name in args:
            return args[args.index(name) + 1]
cmd = args[0]
if cmd in ("run", "trim"):
    out, name = Path(opt("--outdir")), opt("--name")
    (out / "te_containing").mkdir(parents=True, exist_ok=True)
    (out / "te_containing" / f"{name}.read_repeat_name.txt").write_text("r1\tmPing\n")
    (out / "flanking").mkdir(exist_ok=True)
    (out / "flanking" / f"{name}.left.flankingReads.fq").write_text("@r1\nACGT\n+\nIIII\n")
elif cmd == "align-genome":
    out, name = Path(opt("-o")), opt("-n")
    aligner = opt("--genome-aligner")
    (out / f"{name}.repeat.{aligner}.sorted.bam").write_text("bam")
elif cmd == "find-insertions":
    out = Path(opt("--outdir")) / "results"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{opt('--target')}.{opt('--te-name')}.all_nonref_insert.txt").write_text("")
elif cmd == "characterize":
    sites = Path(opt("-s"))
    out = Path(opt("-o"))
    (out / (sites.stem + ".characTErized.txt")).write_text("")
'''

STUB_MARK = "#!/bin/sh\necho \"$(basename \"$0\") $*\" >> \"$STUB_LOG\"\n"
STUB_SAMTOOLS = r'''#!{python}
import os, sys
from pathlib import Path
with open(os.environ["STUB_LOG"], "a") as log:
    log.write("samtools " + " ".join(sys.argv[1:]) + "\n")
if sys.argv[1] == "sort":
    sys.stdin.read()
    Path(sys.argv[sys.argv.index("-o") + 1]).write_text("bam")
'''


class ReplayAdapterTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        root = self.root = Path(self._tmp.name)
        self.repo, rev = make_rt3_repo(root)
        self.cache_sample = make_cache(root, sample="s1")
        stub = root / "stub"
        stub.mkdir()
        for name, text in (
            ("relocaTE3", STUB_RELOCATE3.replace("{python}", sys.executable)),
            ("samtools", STUB_SAMTOOLS.replace("{python}", sys.executable)),
            ("minimap2", STUB_MARK),
            ("bcftools", STUB_MARK),
        ):
            (stub / name).write_text(text)
            (stub / name).chmod(0o755)
        for name in ("python3", "python3.12"):
            (stub / name).symlink_to(sys.executable)
        inputs = root / "in"
        inputs.mkdir()
        for name in ("R1.fq", "R2.fq", "ref.fa", "ref.fa.fai", "ref.fa.mmi",
                     "lib.fa", "rm.out"):
            (inputs / name).write_text(name)
        self.library = inputs / "lib.fa"
        self.manifest = root / "manifest.json"
        check_cache.register(run_root=root / "runs", source_caller="src-caller",
                             source_rev=rev, libraries={"ds": self.library},
                             out=self.manifest)
        self.log = root / "stub.log"
        self.outdir = root / "out" / "s1"
        self.env = {
            "PATH": f"{stub}:/usr/bin:/bin",
            "HOME": str(root),
            "STUB_LOG": str(self.log),
            "DATASET": "ds", "SAMPLE": "s1",
            "R1": str(inputs / "R1.fq"), "R2": str(inputs / "R2.fq"),
            "REFERENCE": str(inputs / "ref.fa"), "TE_LIBRARY": str(self.library),
            "REPEATMASKER": str(inputs / "rm.out"), "TE_NAME": "mPing",
            "OUTDIR": str(self.outdir), "THREADS": "2", "RT3_REPO": str(self.repo),
            "RT3_TE_ALIGNER": "blat", "RT3_GENOME_ALIGNER": "bwaaln",
            "RT3_REPLAY_MANIFEST": str(self.manifest),
        }

    def tearDown(self):
        self._tmp.cleanup()

    def run_adapter(self, script="callers/relocate3-replay/run.sh"):
        return subprocess.run(["bash", script], cwd=REPO_ROOT, env=self.env,
                              capture_output=True, text=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()
                if line.startswith("[")]

    def snapshot(self):
        return sorted((str(p), p.stat().st_mtime_ns, p.stat().st_size)
                      for p in self.cache_sample.rglob("*"))

    def test_replay_trims_cached_bams_and_reuses_genotype_bam(self):
        before = self.snapshot()
        result = self.run_adapter()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        commands = [call[0] for call in self.calls()]
        self.assertNotIn("run", commands)
        self.assertEqual(commands[0], "trim")
        trim = self.calls()[0]
        raw = self.outdir / "raw"
        bam_args = trim[trim.index("--bam") + 1: trim.index("--bam") + 3]
        self.assertEqual(bam_args, [str(raw / "s1.left.bam"), str(raw / "s1.right.bam")])
        self.assertEqual(trim[trim.index("--fastq") + 1: trim.index("--fastq") + 3],
                         [self.env["R1"], self.env["R2"]])
        for side in ("left", "right"):
            link = raw / f"s1.{side}.bam"
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(),
                             (self.cache_sample / "raw" / f"s1.{side}.bam").resolve())
        characterize = next(c for c in self.calls() if c[0] == "characterize")
        self.assertEqual(
            Path(characterize[characterize.index("-b") + 1]).resolve(),
            (self.cache_sample / "raw" / "s1.original_reads.sorted.bam").resolve())
        self.assertNotIn("minimap2", self.log.read_text())
        self.assertTrue((self.outdir / ".run_complete").is_file())
        self.assertEqual(self.snapshot(), before)

    def test_stale_te_search_source_is_refused_before_any_output(self):
        (self.repo / "src/RelocaTE3/aligners.py").write_text("BLAT = 9\n")
        result = self.run_adapter()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("full tier", result.stderr)
        self.assertFalse(self.outdir.exists())

    def test_replay_wrapper_requires_manifest(self):
        del self.env["RT3_REPLAY_MANIFEST"]
        result = self.run_adapter()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.outdir.exists())

    def test_full_tier_without_manifest_still_runs_te_search(self):
        del self.env["RT3_REPLAY_MANIFEST"]
        result = self.run_adapter("callers/relocate3/run.sh")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.calls()[0][0], "run")
        self.assertIn("minimap2", self.log.read_text())

    def test_replay_normalize_delegates_to_relocate3(self):
        wrapper = REPO_ROOT / "callers" / "relocate3-replay" / "normalize.py"
        result = subprocess.run([sys.executable, str(wrapper), "--help"],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--te-name", result.stdout)


if __name__ == "__main__":
    unittest.main()
