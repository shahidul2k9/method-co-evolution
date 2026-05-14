import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

import mhc.main as mhc_main
import mhc.method_scanner as ms
import mhc.util as util


class MethodCodeGenerationTestCase(unittest.TestCase):
    def test_error_markers_can_be_treated_as_completed_when_retry_disabled(self):
        cache_df = pd.DataFrame(
            [
                {
                    **{col: None for col in ms.METHOD_CODE_CACHE_COLUMNS},
                    ms.METHOD_CODE_KEY_COLUMN: "broken-url",
                    ms.METHOD_CODE_FLAG_COLUMN: ms.METHOD_CODE_ERROR_MARKER,
                },
                {
                    **{col: None for col in ms.METHOD_CODE_CACHE_COLUMNS},
                    ms.METHOD_CODE_KEY_COLUMN: "ok-url",
                },
            ],
            columns=ms.METHOD_CODE_CACHE_COLUMNS,
        )

        self.assertEqual(
            {"ok-url"},
            ms._completed_method_code_keys(cache_df),
        )
        self.assertEqual(
            {"broken-url", "ok-url"},
            ms._completed_method_code_keys(cache_df, retry_errors=False),
        )

    def test_generate_method_code_extracts_code_from_checked_out_repository(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            data_directory = Path(temp_directory) / "data"
            repository_directory = root / "repositories"
            input_file = Path(util.format_method_list_file(str(data_directory), "commons-io"))
            input_file.parent.mkdir(parents=True, exist_ok=True)
            source_file = repository_directory / "commons-io" / "src" / "main" / "java" / "org" / "example" / "CopyUtils.java"
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text(
                "\n".join(
                    [
                        "package org.example;",
                        "class CopyUtils {",
                        "    void helper() {",
                        "        int a = 1;",
                        "    }",
                        "",
                        "    void copy() {",
                        "        int b = 2;",
                        "        int c = 3;",
                        "    }",
                        "}",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            pd.DataFrame(
                [
                    {
                        "project": "commons-io",
                        "name": "copy",
                        "url": "https://example.test/copy#L10",
                        "artifact": "#main-code",
                        "start_line": 7.0,
                        "end_line": 10.0,
                        "expression": "method",
                        "file": "src/main/java/org/example/CopyUtils.java",
                    }
                ]
            ).to_csv(input_file, index=False)

            repository_df = pd.DataFrame(
                [
                    {
                        "project": "commons-io",
                        "url": "https://github.com/example/commons-io",
                        "updated_hash": "abc123",
                    }
                ]
            )

            with patch.object(ms, "clone_and_checkout_commit") as mock_checkout:
                output_files = ms.generate_method_code(
                    repository_df,
                    str(repository_directory),
                    str(data_directory),
                )

            output_file = Path(output_files[0])
            self.assertEqual(
                output_file,
                Path(util.format_method_code_file(str(data_directory), "commons-io")),
            )
            self.assertTrue(output_file.exists())
            mock_checkout.assert_called_once_with(
                "https://github.com/example/commons-io",
                str(repository_directory / "commons-io"),
                "abc123",
            )

            output_df = pd.read_csv(output_file)
            self.assertEqual(output_df.columns.tolist(), ms.METHOD_CODE_COLUMNS)
            self.assertEqual(output_df.iloc[0].to_dict()["project"], "commons-io")
            self.assertEqual(int(output_df.iloc[0].to_dict()["start_line"]), 7)
            self.assertEqual(int(output_df.iloc[0].to_dict()["end_line"]), 10)
            self.assertEqual(
                output_df.iloc[0].to_dict()["code"],
                "\n".join(
                    [
                        "    void copy() {",
                        "        int b = 2;",
                        "        int c = 3;",
                        "    }",
                    ]
                ),
            )

    def test_generate_method_code_skips_non_utf8_source_files(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            data_directory = root / "data"
            repository_directory = root / "repositories"
            input_file = Path(util.format_method_list_file(str(data_directory), "argouml"))
            input_file.parent.mkdir(parents=True, exist_ok=True)
            source_file = (
                repository_directory
                / "argouml"
                / "src"
                / "main"
                / "java"
                / "org"
                / "example"
                / "Diagram.java"
            )
            source_file.parent.mkdir(parents=True, exist_ok=True)
            source_file.write_text(
                "\n".join(
                    [
                        "package org.example;",
                        "class Diagram {",
                        "    void helper() {",
                        "        int a = 1;",
                        "    }",
                        "",
                        "    void label() {",
                        '        String text = "canción";',
                        "    }",
                        "}",
                    ]
                )
                + "\n",
                encoding="cp1252",
            )

            pd.DataFrame(
                [
                    {
                        "project": "argouml",
                        "name": "label",
                        "url": "https://example.test/label#L7",
                        "artifact": "#main-code",
                        "start_line": 7.0,
                        "end_line": 9.0,
                        "expression": "method",
                        "file": "src/main/java/org/example/Diagram.java",
                    }
                ]
            ).to_csv(input_file, index=False)

            repository_df = pd.DataFrame(
                [
                    {
                        "project": "argouml",
                        "url": "https://github.com/example/argouml",
                        "updated_hash": "be952fc",
                    }
                ]
            )

            with patch.object(ms, "clone_and_checkout_commit"):
                output_files = ms.generate_method_code(
                    repository_df,
                    str(repository_directory),
                    str(data_directory),
                )

            output_df = pd.read_csv(output_files[0], keep_default_na=False)
            self.assertEqual(output_df.iloc[0].to_dict()["code"], "")

    @patch("mhc.main.MethodHistoryCollector")
    def test_main_dispatches_method_code_command(self, mock_collector_cls):
        mock_collector = mock_collector_cls.return_value
        test_args = [
            "main.py",
            "method-code",
            "--workspace-directory",
            "/tmp/cache",
            "--repository-directory",
            "/tmp/repository",
            "--data-directory",
            "/tmp/data",
            "--jar-directory",
            "/tmp/jar",
            "--project",
            "commons-io",
        ]

        with patch.object(sys, "argv", test_args):
            mhc_main.main()

        mock_collector.generate_method_code.assert_called_once_with(
            ["commons-io"],
            1,
            1,
            False,
            False,
            False,
            False,
            False,
            True,
            10000,
            900,
        )

    @patch("mhc.main.MethodHistoryCollector")
    def test_main_requires_project_for_method_code(self, mock_collector_cls):
        test_args = [
            "main.py",
            "method-code",
            "--workspace-directory",
            "/tmp/cache",
            "--repository-directory",
            "/tmp/repository",
            "--data-directory",
            "/tmp/data",
            "--jar-directory",
            "/tmp/jar",
        ]

        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as raised:
                mhc_main.main()

        self.assertEqual(raised.exception.code, 1)
        mock_collector_cls.return_value.generate_method_code.assert_not_called()

    def test_finalize_method_code_writes_errors_and_deletes_cache_and_lock(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".method-code" / "demo.csv"
            lock_file = root / ".method-code" / "demo.lock"
            output_file = root / "data" / "method-code" / "demo.csv"
            error_file = root / ".method-code-error" / "demo.csv"
            cache_file.parent.mkdir(parents=True)
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [
                    {
                        **{col: None for col in ms.METHOD_CODE_CACHE_COLUMNS},
                        "project": "demo",
                        "name": "ok",
                        "url": "ok-url",
                        "file": "src/Ok.java",
                        "code": "void ok() {}",
                        ms.METHOD_CODE_KEY_COLUMN: "ok-url",
                    },
                    {
                        **{col: None for col in ms.METHOD_CODE_CACHE_COLUMNS},
                        "project": "demo",
                        "name": "broken",
                        "url": "broken-url",
                        "file": "src/Broken.java",
                        ms.METHOD_CODE_KEY_COLUMN: "broken-url",
                        ms.METHOD_CODE_FLAG_COLUMN: ms.METHOD_CODE_ERROR_MARKER,
                        ms.METHOD_CODE_ERROR_COLUMN: "x" * 300,
                    },
                ],
                columns=ms.METHOD_CODE_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = ms._finalize_method_code_outputs(
                str(cache_file),
                str(output_file),
                str(error_file),
                {"ok-url", "broken-url"},
                str(lock_file),
            )

            self.assertTrue(merged)
            self.assertFalse(cache_file.exists())
            self.assertFalse(lock_file.exists())
            output_df = pd.read_csv(output_file)
            self.assertEqual(["ok-url"], output_df["url"].tolist())
            self.assertNotIn(ms.METHOD_CODE_FLAG_COLUMN, output_df.columns)
            error_df = pd.read_csv(error_file)
            self.assertEqual(["broken-url"], error_df["url"].tolist())
            self.assertEqual([ms.METHOD_CODE_ERROR_MARKER], error_df[ms.METHOD_CODE_FLAG_COLUMN].tolist())
            self.assertEqual(ms.METHOD_CODE_ERROR_MAX_LENGTH, len(error_df[ms.METHOD_CODE_ERROR_COLUMN].iloc[0]))

    def test_finalize_method_code_waits_until_all_methods_are_tried(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".method-code" / "demo.csv"
            lock_file = root / ".method-code" / "demo.lock"
            output_file = root / "data" / "method-code" / "demo.csv"
            error_file = root / ".method-code-error" / "demo.csv"
            cache_file.parent.mkdir(parents=True)
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [
                    {
                        **{col: None for col in ms.METHOD_CODE_CACHE_COLUMNS},
                        "project": "demo",
                        "name": "ok",
                        "url": "ok-url",
                        "file": "src/Ok.java",
                        "code": "void ok() {}",
                        ms.METHOD_CODE_KEY_COLUMN: "ok-url",
                    },
                ],
                columns=ms.METHOD_CODE_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = ms._finalize_method_code_outputs(
                str(cache_file),
                str(output_file),
                str(error_file),
                {"ok-url", "missing-url"},
                str(lock_file),
            )

            self.assertFalse(merged)
            self.assertTrue(cache_file.exists())
            self.assertTrue(lock_file.exists())
            self.assertFalse(output_file.exists())


if __name__ == "__main__":
    unittest.main()
