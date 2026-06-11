from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

import pandas as pd
import matplotlib.pyplot as plt

from ptc.plot.method_history_runtime_boxplot import (
    Y_AXIS_MAX_SECONDS,
    count_values_above_limit,
    draw_runtime_boxplot,
    load_runtime_series,
    main,
)


class TestMethodHistoryRuntimeBoxplot(unittest.TestCase):
    def test_load_runtime_series_excludes_intellij_and_converts_to_seconds(self):
        metric_df = pd.DataFrame(
            {
                "historyFinder_runtime": [1000, 3000],
                "intelliJ_runtime": [1, 2],
                "gitFuncName_runtime": [100, 300],
            }
        )

        series = load_runtime_series(metric_df)

        self.assertEqual(["historyFinder", "gitFuncName"], [item["tool"] for item in series])
        self.assertEqual([1.0, 3.0], series[0]["values"].tolist())
        self.assertEqual([0.1, 0.3], series[1]["values"].tolist())

    def test_counts_values_above_visible_limit(self):
        runtime_series = [
            {"values": pd.Series([1.0, 12.0, 12.1, 30.0])},
            {"values": pd.Series([0.1, 2.0])},
        ]

        counts = count_values_above_limit(runtime_series, Y_AXIS_MAX_SECONDS)

        self.assertEqual([2, 0], counts)

    def test_draws_linear_axis_and_boundary_marker_only_for_clipped_tool(self):
        runtime_series = [
            {"label": "HistoryFinder", "values": pd.Series([1.0, 2.0, 13.0])},
            {"label": "GitFuncName", "values": pd.Series([0.1, 0.2, 0.3])},
        ]
        fig, ax = plt.subplots()

        draw_runtime_boxplot(ax, runtime_series)

        self.assertEqual("linear", ax.get_yscale())
        self.assertEqual((0.0, 12.0), ax.get_ylim())
        self.assertEqual(list(range(13)), ax.get_yticks().tolist())
        self.assertEqual(["n=1"], [text.get_text() for text in ax.texts])
        self.assertEqual(1, len(ax.collections))
        plt.close(fig)

    def test_main_writes_boxplot_to_experiment_figure_directory(self):
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
                    "historyFinder_runtime": [1000, 3000, 5000],
                    "intelliJ_runtime": [1, 1, 1],
                    "gitFuncName_runtime": [100, 300, 500],
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
                / "method-history-runtime-boxplot.pdf",
                output_file,
            )
            self.assertTrue(output_file.exists())
            self.assertGreater(output_file.stat().st_size, 0)

    def test_main_writes_boxplot_to_explicit_output_directory(self):
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
            pd.DataFrame({"historyFinder_runtime": [1000, 3000, 5000]}).to_csv(input_file, index=False)

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
                project_directory / "t2plinker-latex" / "figure" / "method-history-runtime-boxplot.pdf",
                output_file,
            )
            self.assertTrue(output_file.exists())


if __name__ == "__main__":
    unittest.main()
