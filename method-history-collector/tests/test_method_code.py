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
                        "artifact": "production",
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

    @patch("mhc.main.MethodHistoryCollector")
    def test_main_dispatches_method_code_command(self, mock_collector_cls):
        mock_collector = mock_collector_cls.return_value
        test_args = [
            "main.py",
            "method-code",
            "--cache-directory",
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

        mock_collector.generate_method_code.assert_called_once_with(["commons-io"])

    @patch("mhc.main.MethodHistoryCollector")
    def test_main_requires_project_for_method_code(self, mock_collector_cls):
        test_args = [
            "main.py",
            "method-code",
            "--cache-directory",
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


if __name__ == "__main__":
    unittest.main()
