import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

import mhc.main as mhc_main


class TestCliArgs(unittest.TestCase):
    @patch("mhc.main._build_method_history_collector")
    def test_scan_method_accepts_dash_prefixed_java_options(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "scan-method",
                "--cache-directory",
                ".cache",
                "--repository-directory",
                ".cache/repository",
                "--data-directory",
                ".cache/data",
                "--jar-directory",
                ".cache/jar",
                "--java-options",
                "-Xmx2g",
                "--project",
                "checkstyle",
            ]
        )

        mock_mhc_instance.scan_method.assert_called_once_with(
            ["checkstyle"],
            "-Xmx2g",
            False,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_scan_method_accepts_replace(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "scan-method",
                "--cache-directory",
                ".cache",
                "--repository-directory",
                ".cache/repository",
                "--data-directory",
                ".cache/data",
                "--jar-directory",
                ".cache/jar",
                "--project",
                "checkstyle",
                "--replace",
            ]
        )

        mock_mhc_instance.scan_method.assert_called_once_with(
            ["checkstyle"],
            None,
            True,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_call_graph_accepts_replace(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "call-graph",
                "--cache-directory",
                ".cache",
                "--repository-directory",
                ".cache/repository",
                "--data-directory",
                ".cache/data",
                "--jar-directory",
                ".cache/jar",
                "--tool-name",
                "methodParser",
                "--project",
                "checkstyle",
                "--replace",
            ]
        )

        mock_mhc_instance.generate_call_graph.assert_called_once_with(
            ["checkstyle"],
            ["methodParser"],
            True,
            None,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_history_accepts_project_list_and_shards(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame(
            [{"project": "checkstyle"}, {"project": "commons-io"}]
        )

        mhc_main.main(
            [
                "history",
                "--cache-directory",
                ".cache",
                "--repository-directory",
                ".cache/repository",
                "--data-directory",
                ".cache/data",
                "--jar-directory",
                ".cache/jar",
                "--tool-name",
                "codeShovel",
                "--projects",
                "checkstyle,commons-io",
                "--shards",
                "20",
                "--shard",
                "7",
                "--merge-threshold",
                "5000",
            ]
        )

        mock_mhc_instance.collect_method_history.assert_called_once_with(
            ["checkstyle", "commons-io"],
            ["codeShovel"],
            None,
            None,
            1800,
            20,
            7,
            5000,
            False,
            False,
            False,
            False,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_history_accepts_history_directory(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "history",
                "--cache-directory",
                ".cache",
                "--history-directory",
                "/scratch/history-json",
                "--repository-directory",
                ".cache/repository",
                "--data-directory",
                ".cache/data",
                "--jar-directory",
                ".cache/jar",
                "--tool-name",
                "codeShovel",
                "--project",
                "checkstyle",
            ]
        )

        mock_build_collector.assert_called_once_with(
            ".cache",
            ".cache/repository",
            ".cache/data",
            ".cache/jar",
            "/scratch/history-json",
        )

    @patch("mhc.main._build_method_history_collector")
    def test_history_accepts_negative_merge_threshold(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "history",
                "--cache-directory",
                ".cache",
                "--repository-directory",
                ".cache/repository",
                "--data-directory",
                ".cache/data",
                "--jar-directory",
                ".cache/jar",
                "--tool-name",
                "codeShovel",
                "--project",
                "checkstyle",
                "--merge-threshold",
                "-2",
            ]
        )

        mock_mhc_instance.collect_method_history.assert_called_once_with(
            ["checkstyle"],
            ["codeShovel"],
            None,
            None,
            1800,
            1,
            1,
            -2,
            False,
            False,
            False,
            False,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_history_accepts_merge_only(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "history",
                "--cache-directory",
                ".cache",
                "--repository-directory",
                ".cache/repository",
                "--data-directory",
                ".cache/data",
                "--jar-directory",
                ".cache/jar",
                "--tool-name",
                "codeShovel",
                "--project",
                "checkstyle",
                "--merge-only",
            ]
        )

        mock_mhc_instance.collect_method_history.assert_called_once_with(
            ["checkstyle"],
            ["codeShovel"],
            None,
            None,
            1800,
            1,
            1,
            10000,
            True,
            False,
            False,
            False,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_history_accepts_merge_only_cleanup_modes(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "history",
                "--cache-directory",
                ".cache",
                "--repository-directory",
                ".cache/repository",
                "--data-directory",
                ".cache/data",
                "--jar-directory",
                ".cache/jar",
                "--tool-name",
                "codeShovel",
                "--project",
                "checkstyle",
                "--merge-only",
                "delete-empty",
                "delete-tmp",
                "delete-lock",
            ]
        )

        mock_mhc_instance.collect_method_history.assert_called_once_with(
            ["checkstyle"],
            ["codeShovel"],
            None,
            None,
            1800,
            1,
            1,
            10000,
            True,
            True,
            True,
            True,
        )


if __name__ == "__main__":
    unittest.main()
