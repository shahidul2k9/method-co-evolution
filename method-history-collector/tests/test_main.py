import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

import mhc.main as mhc_main
from mhc.config import (
    WORKSPACE_DIRECTORY,
    REPOSITORY_DIRECTORY,
    JAR_DIRECTORY,
    HISTORY_DIRECTORY,
    EXPERIMENT_DIRECTORY,
)




class TestMhcScript(unittest.TestCase):
    @patch("mhc.main._build_method_history_collector")
    def test_history_command_success(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])
        mock_mhc_instance.collect_method_history.return_value = None

        test_args = [
            "main.py",
            "method-history",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--tool-name",
            "codeShovel",
            "--project",
            "checkstyle",
        ]

        with patch.object(sys, "argv", test_args):
            try:
                mhc_main.main()
            except SystemExit as exc:
                self.fail(f"main() exited unexpectedly with {exc}")

        mock_build_collector.assert_called_once_with(
            WORKSPACE_DIRECTORY,
            EXPERIMENT_DIRECTORY,
            REPOSITORY_DIRECTORY,
            JAR_DIRECTORY,
            HISTORY_DIRECTORY,
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
            False,
            False,
            False,
            False,
            1,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_history_command_missing_tool_or_project(self, mock_build_collector):
        mock_build_collector.return_value.repository_df = pd.DataFrame([{"project": "checkstyle"}])
        test_args = [
            "main.py",
            "method-history",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
        ]

        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                mhc_main.main()
            self.assertEqual(cm.exception.code, 1)

        mock_build_collector.assert_called_once()

    @patch("mhc.main._build_method_history_collector")
    def test_unknown_command(self, mock_build_collector):
        mock_build_collector.return_value.repository_df = pd.DataFrame([{"project": "checkstyle"}])
        test_args = [
            "main.py",
            "unknown",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
        ]

        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                mhc_main.main()
            self.assertEqual(cm.exception.code, 1)

        mock_build_collector.assert_called_once()

    @patch("mhc.main._build_method_history_collector")
    def test_callgraph_generation(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "checkstyle"}])
        mock_mhc_instance.generate_callgraph.return_value = None

        test_args = [
            "main.py",
            "method-callgraph",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--tool-name",
            "methodParser",
            "--project",
            "checkstyle",
        ]

        with patch.object(sys, "argv", test_args):
            try:
                mhc_main.main()
            except SystemExit as exc:
                self.fail(f"main() exited unexpectedly with {exc}")

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
        )

    @patch("mhc.main._build_method_history_collector")
    def test_history_command_accepts_project_index_slice(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame(
            [{"project": "ant"}, {"project": "checkstyle"}, {"project": "commons-io"}]
        )

        test_args = [
            "main.py",
            "method-history",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--tool-name",
            "codeShovel",
            "--project-index",
            "1:",
            "--shards",
            "4",
            "--shard",
            "2",
        ]

        with patch.object(sys, "argv", test_args):
            mhc_main.main()

        mock_mhc_instance.collect_method_history.assert_called_once_with(
            ["checkstyle", "commons-io"],
            ["codeShovel"],
            None,
            None,
            1800,
            4,
            2,
            10000,
            False,
            False,
            False,
            False,
            1,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_project_index_colon_selects_all_projects(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame(
            [{"project": "ant"}, {"project": "checkstyle"}, {"project": "commons-io"}]
        )

        test_args = [
            "main.py",
            "method-scan",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--project-index",
            ":",
        ]

        with patch.object(sys, "argv", test_args):
            mhc_main.main()

        mock_mhc_instance.scan_method.assert_called_once_with(
            ["ant", "checkstyle", "commons-io"],
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
        )

    @patch("mhc.main._build_method_history_collector")
    def test_project_index_accepts_open_ended_bounds(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame(
            [{"project": "ant"}, {"project": "checkstyle"}, {"project": "commons-io"}]
        )

        test_args = [
            "main.py",
            "method-scan",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--project-index",
            ":2",
        ]

        with patch.object(sys, "argv", test_args):
            mhc_main.main()

        mock_mhc_instance.scan_method.assert_called_once_with(
            ["ant", "checkstyle"],
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
        )

    @patch("mhc.main._build_method_history_collector")
    def test_project_index_accepts_negative_index(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame(
            [{"project": "ant"}, {"project": "checkstyle"}, {"project": "commons-io"}]
        )

        test_args = [
            "main.py",
            "method-scan",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--project-index",
            "-1",
        ]

        with patch.object(sys, "argv", test_args):
            mhc_main.main()

        mock_mhc_instance.scan_method.assert_called_once_with(
            ["commons-io"],
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
        )

    @patch("mhc.main._build_method_history_collector")
    def test_artifact_update_command_has_no_mode_argument(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "jgit"}])

        test_args = [
            "main.py",
            "artifact-update",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--artifact-config-path",
            "/tmp/artifact-detection",
            "--project",
            "jgit",
            "--target",
            "method,class",
            "--backup",
        ]

        with patch.object(sys, "argv", test_args):
            mhc_main.main()

        mock_mhc_instance.update_artifacts.assert_called_once_with(
            ["jgit"],
            None,
            "/tmp/artifact-detection",
            ["method", "class"],
            False,
            True,
            False,
            1,
        )

    @patch("mhc.main._build_method_history_collector")
    def test_artifact_update_rejects_mode_argument(self, mock_build_collector):
        test_args = [
            "main.py",
            "artifact-update",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--project",
            "jgit",
            "--mode",
            "precise",
        ]

        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                mhc_main.main()
            self.assertEqual(cm.exception.code, 2)

        mock_build_collector.assert_not_called()

    @patch("mhc.main._build_method_history_collector")
    def test_method_complexity_command_runs_complexity_analyzer(self, mock_build_collector):
        mock_mhc_instance = mock_build_collector.return_value
        mock_mhc_instance.repository_df = pd.DataFrame([{"project": "jgit"}])

        test_args = [
            "main.py",
            "method-complexity",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--tool-name",
            "complexityAnalyzer",
            "--project",
            "jgit",
        ]

        with patch.object(sys, "argv", test_args):
            mhc_main.main()

        mock_mhc_instance.run_complexity_analyzer.assert_called_once_with(
            ["jgit"],
            "complexityAnalyzer",
        )

    @patch("mhc.main._build_method_history_collector")
    def test_old_complexity_analyzer_command_is_rejected(self, mock_build_collector):
        mock_build_collector.return_value.repository_df = pd.DataFrame([{"project": "jgit"}])
        test_args = [
            "main.py",
            "complexity-analyzer",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--tool-name",
            "complexityAnalyzer",
            "--project",
            "jgit",
        ]

        with patch.object(sys, "argv", test_args):
            with self.assertRaises(SystemExit) as cm:
                mhc_main.main()
            self.assertEqual(cm.exception.code, 1)

        mock_build_collector.return_value.run_complexity_analyzer.assert_not_called()

    @unittest.skip("Legacy llm-m2m-link CLI path is no longer covered in mhc.main.")
    @patch("mhc.main.subprocess.run")
    @patch("mhc.main.importlib.util.find_spec", return_value=object())
    @patch("mhc.main._build_method_history_collector")
    def test_llm_classification_uses_project_to_resolve_input_file(
        self,
        mock_build_collector,
        _mock_find_spec,
        mock_subprocess_run,
    ):
        test_args = [
            "main.py",
            "llm-m2m-link",
            "--workspace-directory",
            WORKSPACE_DIRECTORY,
            "--repository-directory",
            REPOSITORY_DIRECTORY,
            "--jar-directory",
            JAR_DIRECTORY,
            "--project",
            "commons-io",
            "--input-kind",
            "t2p",
            "--model-name-or-path",
            "openai/gpt-oss-20b",
            "--batch-size",
            "8",
        ]

        with patch.object(sys, "argv", test_args):
            try:
                mhc_main.main()
            except SystemExit as exc:
                self.fail(f"main() exited unexpectedly with {exc}")

        mock_build_collector.assert_not_called()
        mock_subprocess_run.assert_called_once()
        command = mock_subprocess_run.call_args.args[0]
        self.assertIn("ptc.llm.main", command)
        self.assertIn(WORKSPACE_DIRECTORY, command)
        self.assertIn("commons-io", command)
        self.assertIn("openai/gpt-oss-20b", command)
        self.assertIn("t2p", command)


if __name__ == "__main__":
    unittest.main()
