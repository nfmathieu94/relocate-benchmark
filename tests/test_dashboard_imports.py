import importlib
import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path


HAS_UI_DEPS = all(
    importlib.util.find_spec(package) is not None for package in ("plotly", "streamlit")
)


@unittest.skipUnless(HAS_UI_DEPS, "dashboard UI dependencies are not installed")
class TestDashboardImports(unittest.TestCase):
    def test_application_import_does_not_run_main(self):
        module = importlib.import_module("dashboard.app")
        self.assertTrue(callable(module.main))

    def test_page_modules_import_without_browser(self):
        pages = (
            path
            for path in Path("dashboard/pages").glob("*.py")
            if path.name != "__init__.py"
        )
        for path in pages:
            with self.subTest(page=path.name):
                spec = importlib.util.spec_from_file_location(path.stem, path)
                module = importlib.util.module_from_spec(spec)
                self.assertIsNotNone(spec.loader)
                spec.loader.exec_module(module)
                self.assertTrue(callable(module.main))

    def test_pages_bootstrap_repo_root_from_streamlit_context(self):
        pages_dir = Path("dashboard/pages").resolve()
        environment = os.environ.copy()
        environment.pop("PYTHONPATH", None)
        for path in sorted(pages_dir.glob("[0-9]*.py")):
            with self.subTest(page=path.name):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        (
                            "import runpy; "
                            f"runpy.run_path({path.name!r}, run_name='page_import_test')"
                        ),
                    ],
                    cwd=pages_dir,
                    env=environment,
                    capture_output=True,
                    text=True,
                    timeout=20,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
