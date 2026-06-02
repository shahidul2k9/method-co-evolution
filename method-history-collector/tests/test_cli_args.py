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
    def test_experiment_derives_default_runtime_directories(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "method-code",
                "--workspace-directory",
                "/tmp/workspace",
                "--experiment-name",
                "exp-a",
                "--project",
                "checkstyle",
            ]
        )

        mock_build_collector.assert_called_once_with(
            "/tmp/workspace",
            "/tmp/workspace/experiment/exp-a",
            "/tmp/workspace/experiment/exp-a/repository",
            "/tmp/workspace/jar",
            "/tmp/workspace/experiment/exp-a/history",
        )

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
            1,
            None,
            True,
            0,
            0,
            2000,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_callgraph_accepts_max_cache_size(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "method-callgraph",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--jar-directory",
                "workspace/jar",
                "--tool-name",
                "methodParser",
                "--project",
                "checkstyle",
                "--max-cache-size",
                "512",
            ]
        )

        mock_mhc_instance.generate_callgraph.assert_called_once_with(
            ["checkstyle"],
            ["methodParser"],
            False,
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
            512,
            1,
            None,
            2000,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_max_workers_is_threaded_to_supported_commands(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        common_args = [
            "--workspace-directory",
            "workspace",
            "--repository-directory",
            "workspace/repository",
            "--jar-directory",
            "workspace/jar",
            "--project",
            "checkstyle",
            "--max-workers",
            "3",
        ]

        mhc_main.main(["method-scan", *common_args])
        mock_mhc_instance.scan_method.assert_called_once_with(
            ["checkstyle"], None, False, 1, 1, False, False, False, False, True, 10000, 900, 3, None, True, 0, 0, 2000
        )
        mock_mhc_instance.scan_method.reset_mock()

        mhc_main.main(["class-scan", *common_args])
        mock_mhc_instance.scan_class.assert_called_once_with(
            ["checkstyle"], None, False, 1, 1, False, False, False, False, True, 10000, 900, 3
        )
        mock_mhc_instance.scan_class.reset_mock()

        mhc_main.main(["method-callgraph", *common_args, "--tool-name", "methodParser"])
        mock_mhc_instance.generate_callgraph.assert_called_once_with(
            ["checkstyle"],
            ["methodParser"],
            False,
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
            256,
            3,
            None,
            2000,
        )
        mock_mhc_instance.generate_callgraph.reset_mock()

        mhc_main.main(["method-code", *common_args])
        mock_mhc_instance.generate_method_code.assert_called_once_with(
            ["checkstyle"], 1, 1, False, False, False, False, False, True, 10000, 900, 3
        )
        mock_mhc_instance.generate_method_code.reset_mock()

        mhc_main.main(["method-history", *common_args, "--tool-name", "codeShovel"])
        mock_mhc_instance.collect_method_history.assert_called_once_with(
            ["checkstyle"],
            ["codeShovel"],
            None,
            None,
            1800,
            1,
            1,
            10000,
            False,
            False,
            False,
            False,
            3,
        )
        mock_mhc_instance.collect_method_history.reset_mock()

        mhc_main.main(["artifact-update", *common_args])
        mock_mhc_instance.update_artifacts.assert_called_once_with(
            ["checkstyle"], None, None, ["method", "class"], False, False, False, 3
        )
        mock_mhc_instance.update_artifacts.reset_mock()

        mhc_main.main(["test-smell", *common_args, "--tool-name", "jnose"])
        mock_mhc_instance.run_test_smell.assert_called_once_with(
            ["checkstyle"], "jnose", "all", "callgraph", 3
        )

    @patch("mhc.main._build_method_history_collector")
    def test_workers_alias_is_rejected(self, mock_build_collector):
        with self.assertRaises(SystemExit) as cm:
            mhc_main.main(
                [
                    "method-scan",
                    "--workspace-directory",
                    "workspace",
                    "--repository-directory",
                    "workspace/repository",
                    "--jar-directory",
                    "workspace/jar",
                    "--project",
                    "checkstyle",
                    "--workers",
                    "3",
                ]
            )

        self.assertEqual(cm.exception.code, 2)
        mock_build_collector.assert_not_called()

    @patch("mhc.main._build_method_history_collector")
    def test_scanner_reset_alias_is_rejected(self, mock_build_collector):
        with self.assertRaises(SystemExit) as cm:
            mhc_main.main(
                [
                    "method-scan",
                    "--workspace-directory",
                    "workspace",
                    "--repository-directory",
                    "workspace/repository",
                    "--jar-directory",
                    "workspace/jar",
                    "--project",
                    "checkstyle",
                    "--scanner-reset-interval",
                    "500",
                ]
            )

        self.assertEqual(cm.exception.code, 2)
        mock_build_collector.assert_not_called()

    @patch("mhc.main._build_method_history_collector")
    def test_init_reset_interval_files_is_threaded_to_scan_and_callgraph(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        common_args = [
            "--workspace-directory",
            "workspace",
            "--repository-directory",
            "workspace/repository",
            "--jar-directory",
            "workspace/jar",
            "--project",
            "checkstyle",
            "--init-reset-interval-files",
            "500",
        ]

        mhc_main.main(["method-scan", *common_args])
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
            10000,
            900,
            1,
            None,
            True,
            0,
            0,
            500,
        )
        mock_mhc_instance.scan_method.reset_mock()

        mhc_main.main(["method-callgraph", *common_args, "--tool-name", "methodParser"])
        mock_mhc_instance.generate_callgraph.assert_called_once_with(
            ["checkstyle"],
            ["methodParser"],
            False,
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
            256,
            1,
            None,
            500,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_init_reset_interval_files_must_be_non_negative(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        with self.assertRaises(SystemExit) as cm:
            mhc_main.main(
                [
                    "method-scan",
                    "--workspace-directory",
                    "workspace",
                    "--repository-directory",
                    "workspace/repository",
                    "--jar-directory",
                    "workspace/jar",
                    "--project",
                    "checkstyle",
                    "--init-reset-interval-files",
                    "-1",
                ]
            )

        self.assertEqual(cm.exception.code, 1)
        mock_mhc_instance.scan_method.assert_not_called()

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
            1,
            None,
            True,
            0,
            0,
            2000,
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
            256,
            1,
            None,
            2000,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_test_smell_accepts_stage_and_callgraph_dir(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "commons-lang"}])

        mhc_main.main(
            [
                "test-smell",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--jar-directory",
                "workspace/jar",
                "--tool-name",
                "jnose",
                "--stage",
                "preprocess",
                "--callgraph-dir",
                "t2p-candidate-filtered",
                "--project",
                "commons-lang",
            ]
        )

        mock_mhc_instance.run_test_smell.assert_called_once_with(
            ["commons-lang"],
            "jnose",
            "preprocess",
            "t2p-candidate-filtered",
            1,
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
            1,
            None,
            True,
            0,
            0,
            2000,
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
            1,
            None,
            True,
            0,
            0,
            2000,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_scan_method_accepts_enable_symbol_solver_false(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "method-scan",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--jar-directory",
                "workspace/jar",
                "--project",
                "checkstyle",
                "--enable-symbol-solver",
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
            True,
            10000,
            900,
            1,
            None,
            False,
            0,
            0,
            2000,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_scan_method_accepts_cache_evict_intervals(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])

        mhc_main.main(
            [
                "method-scan",
                "--workspace-directory",
                "workspace",
                "--repository-directory",
                "workspace/repository",
                "--jar-directory",
                "workspace/jar",
                "--project",
                "checkstyle",
                "--cache-evict-interval-seconds",
                "300",
                "--cache-evict-interval-files",
                "10000",
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
            10000,
            900,
            1,
            None,
            True,
            300,
            10000,
            2000,
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
            1,
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
            1,
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
            "workspace/experiment/main",
            "workspace/repository",
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
            1,
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
            1,
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
            1,
        )


if __name__ == "__main__":
    unittest.main()
