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
                "method-scan",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
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
            1,
            1,
            False,
            False,
            False,
            False,
            True,
            10000,
            900,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_scan_method_accepts_replace(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "method-scan",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
                "--project",
                "checkstyle",
                "--replace",
            ]
        )

        mock_mhc_instance.scan_method.assert_called_once_with(
            ["checkstyle"],
            None,
            True,
            1,
            1,
            False,
            False,
            False,
            False,
            True,
            10000,
            900,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_callgraph_accepts_replace(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "method-callgraph",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
                "--tool-name",
                "methodParser",
                "--project",
                "checkstyle",
                "--replace",
            ]
        )

        mock_mhc_instance.generate_callgraph.assert_called_once_with(
            ["checkstyle"],
            ["methodParser"],
            True,
            None,
            1,
            1,
            False,
            False,
            False,
            False,
            True,
            10000,
            900,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_scan_method_accepts_retry_errors_false(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "method-scan",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
                "--project",
                "checkstyle",
                "--retry-errors",
                "false",
            ]
        )

        mock_mhc_instance.scan_method.assert_called_once_with(
            ["checkstyle"],
            None,
            False,
            1,
            1,
            False,
            False,
            False,
            False,
            False,
            10000,
            900,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_scan_method_accepts_merge_threshold_and_interval(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "method-scan",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
                "--project",
                "checkstyle",
                "--merge-threshold",
                "-1",
                "--merge-interval-seconds",
                "60",
            ]
        )

        mock_mhc_instance.scan_method.assert_called_once_with(
            ["checkstyle"],
            None,
            False,
            1,
            1,
            False,
            False,
            False,
            False,
            True,
            -1,
            60,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_history_accepts_project_list_and_shards(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame(
            [{"project": "checkstyle"}, {"project": "commons-io"}]
        )

        mhc_main.main(
            [
                "method-history",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
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
    def test_history_project_index_can_filter_project_list(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame(
            [{"project": "ant"}, {"project": "checkstyle"}, {"project": "commons-io"}]
        )

        mhc_main.main(
            [
                "method-history",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
                "--tool-name",
                "codeShovel",
                "--projects",
                "checkstyle,commons-io",
                "--project-index",
                "1",
                "--shards",
                "10",
                "--shard",
                "3",
            ]
        )

        mock_mhc_instance.collect_method_history.assert_called_once_with(
            ["commons-io"],
            ["codeShovel"],
            None,
            None,
            1800,
            10,
            3,
            10000,
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
                "method-history",
                "--workspace-directory",
                "workspace",
                "--history-directory",
                "/scratch/history-json",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
                "--tool-name",
                "codeShovel",
                "--project",
                "checkstyle",
            ]
        )

        mock_build_collector.assert_called_once_with(
            "workspace",
            "workspace/repository",
            "workspace/data",
            "workspace/jar",
            "/scratch/history-json",
        )

    @patch("mhc.main._build_method_history_collector")
    def test_history_accepts_negative_merge_threshold(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "method-history",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
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
                "method-history",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
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
                "method-history",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--data-directory",
                "workspace/data",
                "--jar-directory",
                "workspace/jar",
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
