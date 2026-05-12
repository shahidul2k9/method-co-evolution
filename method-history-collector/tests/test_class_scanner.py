import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

import mhc.class_scanner as cs


class ClassScannerCacheTestCase(unittest.TestCase):
    def test_error_markers_can_be_treated_as_completed_when_retry_disabled(self):
        cache_df = pd.DataFrame(
            [
                cs._build_class_scan_error_marker(
                    "demo-project",
                    "src/Broken.java",
                    "abc123",
                    "parse failed",
                ),
                cs._build_class_scan_marker("demo-project", "src/Done.java", "abc123"),
            ],
            columns=cs.CLASS_SCAN_CACHE_COLUMNS,
        )

        self.assertEqual(
            {"src/Done.java"},
            cs._completed_class_scan_files(cache_df),
        )
        self.assertEqual(
            {"src/Broken.java", "src/Done.java"},
            cs._completed_class_scan_files(cache_df, retry_errors=False),
        )

    def test_finalize_class_scan_writes_errors_and_deletes_cache_and_lock(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".class" / "demo-project.csv"
            lock_file = root / ".class" / "demo-project.lock"
            output_file = root / "data" / "class" / "demo-project.csv"
            error_file = root / ".class-error" / "demo-project.csv"
            cache_file.parent.mkdir(parents=True)
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [
                    {
                        **{col: None for col in cs.CLASS_SCAN_CACHE_COLUMNS},
                        "project": "demo-project",
                        "name": "Alpha",
                        "file": "src/Alpha.java",
                        "hash": "abc123",
                    },
                    cs._build_class_scan_error_marker(
                        "demo-project",
                        "src/Broken.java",
                        "abc123",
                        "x" * 300,
                    ),
                ],
                columns=cs.CLASS_SCAN_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = cs._finalize_class_scan_outputs(
                str(cache_file),
                str(output_file),
                str(error_file),
                {"src/Alpha.java", "src/Broken.java"},
                str(lock_file),
            )

            self.assertTrue(merged)
            self.assertFalse(cache_file.exists())
            self.assertFalse(lock_file.exists())
            output_df = pd.read_csv(output_file)
            self.assertEqual(["src/Alpha.java"], output_df["file"].tolist())
            self.assertNotIn(cs.CLASS_SCAN_FLAG_COLUMN, output_df.columns)
            error_df = pd.read_csv(error_file)
            self.assertEqual(["src/Broken.java"], error_df["file"].tolist())
            self.assertEqual([cs.CLASS_SCAN_ERROR_MARKER], error_df[cs.CLASS_SCAN_FLAG_COLUMN].tolist())
            self.assertEqual(cs.CLASS_SCAN_ERROR_MAX_LENGTH, len(error_df[cs.CLASS_SCAN_ERROR_COLUMN].iloc[0]))

    def test_finalize_class_scan_waits_until_all_files_are_tried(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".class" / "demo-project.csv"
            lock_file = root / ".class" / "demo-project.lock"
            output_file = root / "data" / "class" / "demo-project.csv"
            error_file = root / ".class-error" / "demo-project.csv"
            cache_file.parent.mkdir(parents=True)
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [cs._build_class_scan_marker("demo-project", "src/Alpha.java", "abc123")],
                columns=cs.CLASS_SCAN_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = cs._finalize_class_scan_outputs(
                str(cache_file),
                str(output_file),
                str(error_file),
                {"src/Alpha.java", "src/Missing.java"},
                str(lock_file),
            )

            self.assertFalse(merged)
            self.assertTrue(cache_file.exists())
            self.assertTrue(lock_file.exists())
            self.assertFalse(output_file.exists())

    def test_finalize_class_scan_removes_float_suffix_from_integer_columns(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".class" / "demo-project.csv"
            output_file = root / "data" / "class" / "demo-project.csv"
            error_file = root / ".class-error" / "demo-project.csv"
            cache_file.parent.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        **{col: None for col in cs.CLASS_SCAN_CACHE_COLUMNS},
                        "project": "demo-project",
                        "name": "Alpha",
                        "fqn": "demo.Alpha",
                        "file": "src/Alpha.java",
                        "start_line": "72.0",
                        "end_line": 80.0,
                        "abstract": "0.0",
                        "hash": "abc123",
                    },
                    cs._build_class_scan_marker("demo-project", "src/Alpha.java", "abc123"),
                ],
                columns=cs.CLASS_SCAN_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = cs._finalize_class_scan_outputs(
                str(cache_file),
                str(output_file),
                str(error_file),
                {"src/Alpha.java"},
            )

            self.assertTrue(merged)
            output_text = output_file.read_text(encoding="utf-8")
            self.assertNotIn("72.0", output_text)
            output_df = pd.read_csv(output_file, dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual("72", output_df.loc[0, "start_line"])
            self.assertEqual("80", output_df.loc[0, "end_line"])
            self.assertEqual("0", output_df.loc[0, "abstract"])


if __name__ == "__main__":
    unittest.main()
