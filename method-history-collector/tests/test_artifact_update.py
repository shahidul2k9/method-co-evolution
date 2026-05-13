import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc import artifact_update


class TestArtifactUpdateLogging(unittest.TestCase):
    def test_update_csv_reports_already_up_to_date(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_file = Path(tmp) / "sample.csv"
            pd.DataFrame(
                [
                    {
                        "file": "src/test/A.java",
                        "pkg": "example",
                        "name": "m",
                        "start_line": "10",
                        "artifact": "#test-code #test-unit #test-method",
                    }
                ]
            ).to_csv(csv_file, index=False)

            output = self._run_update(
                csv_file,
                is_method=True,
                file_artifacts={("src/test/A.java", "example"): "#test-code #test-unit"},
                method_artifacts={
                    ("src/test/A.java", "example"): {
                        ("m", "10"): "#test-code #test-unit #test-method",
                    }
                },
            )

            self.assertIn("processed 1 row(s), 0 changed, 1 unchanged", output)
            self.assertIn("1 file(s) classified, 1 Java file(s) parsed", output)
            self.assertIn("already up to date, no write performed", output)

    def test_update_csv_reports_changed_rows_and_writes_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_file = Path(tmp) / "sample.csv"
            pd.DataFrame(
                [
                    {
                        "file": "src/main/A.java",
                        "pkg": "example",
                        "artifact": "old",
                    }
                ]
            ).to_csv(csv_file, index=False)

            output = self._run_update(
                csv_file,
                backup=True,
                file_artifacts={("src/main/A.java", "example"): "#production-code"},
            )

            self.assertIn("processed 1 row(s), 1 changed, 0 unchanged", output)
            self.assertIn("wrote updated CSV", output)
            self.assertTrue((Path(tmp) / "bk_sample.csv").exists())
            updated = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual(updated.loc[0, "artifact"], "#production-code")

    def test_update_csv_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_file = Path(tmp) / "sample.csv"
            pd.DataFrame(
                [{"file": "src/main/A.java", "pkg": "example", "artifact": "old"}]
            ).to_csv(csv_file, index=False)

            output = self._run_update(
                csv_file,
                dry_run=True,
                backup=True,
                file_artifacts={("src/main/A.java", "example"): "#production-code"},
            )

            self.assertIn("1 changed", output)
            self.assertIn("dry run, no write performed", output)
            self.assertFalse((Path(tmp) / "bk_sample.csv").exists())
            unchanged = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual(unchanged.loc[0, "artifact"], "old")

    def test_update_csv_replace_writes_when_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_file = Path(tmp) / "sample.csv"
            pd.DataFrame(
                [{"file": "src/main/A.java", "pkg": "example", "artifact": "#production-code"}]
            ).to_csv(csv_file, index=False)

            output = self._run_update(
                csv_file,
                replace=True,
                file_artifacts={("src/main/A.java", "example"): "#production-code"},
            )

            self.assertIn("0 changed", output)
            self.assertIn("wrote CSV because --replace", output)

    def test_update_csv_reports_skipped_missing_file_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_file = Path(tmp) / "sample.csv"
            pd.DataFrame(
                [
                    {"file": "", "pkg": "example", "artifact": "old"},
                    {"file": "src/main/A.java", "pkg": "example", "artifact": "#production-code"},
                ]
            ).to_csv(csv_file, index=False)

            output = self._run_update(
                csv_file,
                file_artifacts={("src/main/A.java", "example"): "#production-code"},
            )

            self.assertIn("processed 1 row(s), 0 changed, 1 unchanged, 1 skipped", output)

    def test_update_csv_reports_fallback_method_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            csv_file = Path(tmp) / "sample.csv"
            pd.DataFrame(
                [
                    {
                        "file": "src/test/A.java",
                        "pkg": "example",
                        "name": "helper",
                        "start_line": "7",
                        "artifact": "old",
                    }
                ]
            ).to_csv(csv_file, index=False)

            output = self._run_update(
                csv_file,
                is_method=True,
                file_artifacts={("src/test/A.java", "example"): "#test-code #test-unit"},
                method_artifacts={("src/test/A.java", "example"): {}},
            )

            self.assertIn("1 fallback", output)
            updated = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual(updated.loc[0, "artifact"], "#test-code #test-unit #test-utility")

    def test_update_csv_reports_missing_file_and_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing.csv"
            missing_output = self._run_update(missing)
            self.assertIn("skipped, CSV file does not exist", missing_output)

            csv_file = Path(tmp) / "sample.csv"
            pd.DataFrame([{"file": "src/main/A.java"}]).to_csv(csv_file, index=False)
            columns_output = self._run_update(csv_file)
            self.assertIn("skipped, required columns are missing", columns_output)

    def test_classify_methods_handles_java_parser_failure(self):
        class FakePath:
            @staticmethod
            def of(value):
                return value

        class FakeDetector:
            def classifyMethodArtifacts(self, _path, _package_name):
                raise RuntimeError("java parser failed")

        output = io.StringIO()
        with (
            patch("jpype.JClass", return_value=FakePath),
            patch("mhc.artifact_update._request_java_gc") as request_gc,
            contextlib.redirect_stdout(output),
        ):
            result = artifact_update._classify_methods(
                FakeDetector(),
                "/repo",
                "src/test/A.java",
                "example",
            )

        self.assertEqual({}, result)
        self.assertIn("src/test/A.java: method artifact parse failed", output.getvalue())
        request_gc.assert_called_once()

    def _run_update(
        self,
        csv_file: Path,
        *,
        is_method: bool = False,
        dry_run: bool = False,
        backup: bool = False,
        replace: bool = False,
        file_artifacts: dict[tuple[str, str], str] | None = None,
        method_artifacts: dict[tuple[str, str], dict[tuple[str, str], str]] | None = None,
    ) -> str:
        file_artifacts = file_artifacts or {}
        method_artifacts = method_artifacts or {}

        def classify_file(_detector, _repo_root, rel_file, pkg):
            return file_artifacts[(rel_file, pkg)]

        def classify_methods(_detector, _repo_root, rel_file, pkg):
            return method_artifacts[(rel_file, pkg)]

        output = io.StringIO()
        with (
            patch("mhc.artifact_update._classify_file", side_effect=classify_file),
            patch("mhc.artifact_update._classify_methods", side_effect=classify_methods),
            contextlib.redirect_stdout(output),
        ):
            artifact_update._update_csv(
                str(csv_file),
                "/repo",
                object(),
                dry_run,
                backup,
                replace,
                is_method,
            )
        return output.getvalue()


if __name__ == "__main__":
    unittest.main()
