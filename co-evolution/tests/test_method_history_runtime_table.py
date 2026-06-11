from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

import pandas as pd

from ptc.plot.method_history_runtime_table import (
    calculate_runtime_statistics,
    main,
    render_latex_table,
)


class TestMethodHistoryRuntimeTable(unittest.TestCase):
    def test_calculates_seconds_for_all_runtime_columns_in_input_order(self):
        metric_df = pd.DataFrame(
            {
                "project": ["a", "b", "c"],
                "historyFinder_runtime": [1000, 2000, 6000],
                "codeShovel_runtime": [2000, 4000, 9000],
            }
        )

        stats_df = calculate_runtime_statistics(metric_df)

        self.assertEqual(["historyFinder", "codeShovel"], stats_df["tool"].tolist())
        self.assertEqual(3.0, stats_df.iloc[0]["mean"])
        self.assertEqual(2.0, stats_df.iloc[0]["median"])
        self.assertEqual(6.0, stats_df.iloc[0]["max"])

    def test_ignores_missing_runtime_values(self):
        metric_df = pd.DataFrame({"historyFinder_runtime": [1000, None, 3000]})

        stats_df = calculate_runtime_statistics(metric_df)

        self.assertEqual(2.0, stats_df.iloc[0]["mean"])
        self.assertEqual(2.0, stats_df.iloc[0]["median"])
        self.assertEqual(3.0, stats_df.iloc[0]["max"])

    def test_excludes_intellij_runtime_because_histories_were_generated_manually(self):
        metric_df = pd.DataFrame(
            {
                "historyFinder_runtime": [1000, 3000],
                "intelliJ_runtime": [1, 2],
                "gitFuncName_runtime": [100, 300],
            }
        )

        stats_df = calculate_runtime_statistics(metric_df)

        self.assertEqual(["historyFinder", "gitFuncName"], stats_df["tool"].tolist())

    def test_renders_lowest_statistics_in_bold(self):
        stats_df = pd.DataFrame(
            [
                {"tool": "historyFinder", "mean": 1.0, "median": 2.0, "max": 4.0},
                {"tool": "codeShovel", "mean": 2.0, "median": 1.0, "max": 3.0},
            ]
        )

        latex = render_latex_table(stats_df)

        self.assertIn(r"HistoryFinder & \textbf{1.00} & 2.00 & 4.00 \\", latex)
        self.assertIn(r"CodeShovel & 2.00 & \textbf{1.00} & \textbf{3.00} \\", latex)

    def test_main_writes_table_to_experiment_figure_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_directory = Path(tmpdir)
            workspace_directory = project_directory / "workspace"
            input_file = (
                project_directory
                / "data"
                / "research-question"
                / "rq1"
                / "method-level-revision-history-metric.csv"
            )
            input_file.parent.mkdir(parents=True)
            pd.DataFrame(
                {
                    "historyFinder_runtime": [1000, 3000],
                    "intelliJ_runtime": [1, 2],
                    "gitFuncName_runtime": [100, 300],
                }
            ).to_csv(input_file, index=False)

            output_file = main(
                [
                    "--project-directory",
                    str(project_directory),
                    "--workspace-directory",
                    str(workspace_directory),
                    "--experiment-name",
                    "demo",
                ]
            )

            self.assertEqual(
                workspace_directory
                / "experiment"
                / "demo"
                / "figure"
                / "method-history-runtime-table.tex",
                output_file,
            )
            self.assertTrue(output_file.exists())
            output_text = output_file.read_text(encoding="utf-8")
            self.assertIn("GitFuncName", output_text)
            self.assertNotIn("IntelliJ &", output_text)
            self.assertIn("generated manually", output_text)

    def test_main_writes_table_to_explicit_output_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_directory = Path(tmpdir)
            input_file = (
                project_directory
                / "data"
                / "research-question"
                / "rq1"
                / "method-level-revision-history-metric.csv"
            )
            input_file.parent.mkdir(parents=True)
            pd.DataFrame({"historyFinder_runtime": [1000, 3000]}).to_csv(input_file, index=False)

            output_file = main(
                [
                    "--project-directory",
                    str(project_directory),
                    "--workspace-directory",
                    str(project_directory / "workspace"),
                    "--experiment-name",
                    "demo",
                    "--output-directory",
                    "t2plinker-latex/figure",
                ]
            )

            self.assertEqual(
                project_directory / "t2plinker-latex" / "figure" / "method-history-runtime-table.tex",
                output_file,
            )
            self.assertTrue(output_file.exists())


if __name__ == "__main__":
    unittest.main()
