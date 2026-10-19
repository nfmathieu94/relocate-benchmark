import importlib.util
from pathlib import Path
import tempfile
import unittest


spec = importlib.util.spec_from_file_location(
    "r2validation", "callers/relocate2/validate.py"
)
validation = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validation)


def fixture(root):
    raw = root / "raw"
    results = raw / "repeat/results"
    results.mkdir(parents=True)
    for step, kind, script in ((5, "nonref", "insertion"), (6, "ref", "absence")):
        folder = raw / "shellscripts" / f"step_{step}"
        folder.mkdir(parents=True)
        (folder / "0.sh").write_text(
            f"python /usr/local/bin/relocaTE_{script}Finder.py /data/test.bam Chr1 /ref.fa repeat\n"
        )
        for ext in ("txt", "gff"):
            (results / f"Chr1.repeat.all_{kind}_insert.{ext}").touch()
    (results / "ALL.all_nonref_insert.characTErized.txt").write_text(
        "strain\tTE\tTSD\tchromosome.pos\tstrand\tavg_flankers\tspanners\tstatus\n"
    )
    return results


class ValidationTests(unittest.TestCase):
    def test_true_zero_call_run_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            validation.validate(root)

    def test_header_only_does_not_hide_missing_worker(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = fixture(root)
            (results / "Chr1.repeat.all_nonref_insert.txt").unlink()
            with self.assertRaisesRegex(ValueError, "Missing chromosome"):
                validation.validate(root)

    def test_missing_reference_worker_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            results = fixture(root)
            (results / "Chr1.repeat.all_ref_insert.gff").unlink()
            with self.assertRaisesRegex(ValueError, "Missing chromosome"):
                validation.validate(root)

    def test_internal_traceback_rejected_even_with_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            (root / "relocate2.driver.log").write_text(
                "Traceback (most recent call last):\n"
            )
            with self.assertRaisesRegex(ValueError, "Internal R2"):
                validation.validate(root)

    def test_absent_worker_manifest_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "No step"):
                validation.validate(Path(tmp))

    def test_duplicate_worker_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            fixture(root)
            source = root / "raw/shellscripts/step_5/0.sh"
            source.with_name("1.sh").write_text(source.read_text())
            with self.assertRaisesRegex(ValueError, "Duplicate"):
                validation.validate(root)
