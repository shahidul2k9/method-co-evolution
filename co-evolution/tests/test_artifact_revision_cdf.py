from pathlib import Path
import sys
import tempfile
import unittest
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from ptc.plot.artifact_revision_cdf import (
    build_project_stats,
    classify_method_kind,
    main,
    plot_change_axis,
    subsequent_revision_series,
)
from ptc.util.helper import filter_concrete_methods


class TestArtifactRevisionCdf(unittest.TestCase):
    def test_abstract_methods_are_excluded_from_cdf_population_and_counts(self):
        df = pd.DataFrame(
            [
                {"name": "concrete-main", "artifact": "#main-code", "abstract": 0, "ch_diff": 2},
                {"name": "abstract-main", "artifact": "#main-code", "abstract": 1, "ch_diff": 99},
                {"name": "concrete-test", "artifact": "#test-code #test-case-method", "abstract": 0, "ch_diff": 3},
                {"name": "concrete-helper", "artifact": "#test-code", "abstract": 0, "ch_diff": 4},
                {"name": "abstract-test", "artifact": "#test-code #test-case-method", "abstract": 1, "ch_diff": 98},
                {"name": "invalid-test", "artifact": "#test-code #test-case-method", "abstract": "", "ch_diff": 97},
            ]
        )

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            concrete_df = filter_concrete_methods(df)
        concrete_df["method_kind"] = concrete_df["artifact"].map(classify_method_kind)

        method_df = concrete_df[concrete_df["method_kind"].isin(["test-code", "main-code"])]

        self.assertEqual(["concrete-main", "concrete-test", "concrete-helper"], method_df["name"].tolist())
        self.assertEqual({"total": 3, "test": 2, "production": 1}, build_project_stats(method_df))
        self.assertEqual([2, 3, 4], method_df["ch_diff"].tolist())
        self.assertEqual(
            ["project=<unknown>: 1 invalid abstract values out of 6 methods."],
            [str(warning.message) for warning in caught_warnings],
        )

    def test_main_warns_and_generates_cdf_with_valid_rows_from_affected_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = Path(tmpdir) / "experiment" / "demo"
            history_file = experiment_dir / "method-history" / "historyFinder" / "projectA.csv"
            history_file.parent.mkdir(parents=True)
            pd.DataFrame(
                [
                    {"project": "projectA", "artifact": "#main-code", "abstract": 0, "ch_diff": 2},
                    {"project": "projectA", "artifact": "#test-code #test-case-method", "abstract": 0, "ch_diff": 3},
                    {"project": "projectA", "artifact": "#test-code", "abstract": 0, "ch_diff": 4},
                    {"project": "projectA", "artifact": "#main-code", "abstract": "", "ch_diff": 99},
                ]
            ).to_csv(history_file, index=False)

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                main(
                    [
                        "--workspace-directory",
                        tmpdir,
                        "--experiment-name",
                        "demo",
                        "--tools",
                        "historyFinder",
                    ]
                )

            self.assertTrue(
                (experiment_dir / "figure" / "artifact-revision-cdf--historyFinder.pdf").exists()
            )
            self.assertIn(
                "project=projectA: 1 invalid abstract values out of 4 methods.",
                [str(warning.message) for warning in caught_warnings],
            )

    def test_all_projects_only_writes_paper_plot_to_output_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = Path(tmpdir) / "experiment" / "demo"
            self.write_history_file(
                experiment_dir,
                "historyFinder",
                "projectA",
                [
                    {"artifact": "#main-code", "abstract": 0, "ch_all": 20, "ch_diff": 12},
                    {"artifact": "#test-code #test-case-method", "abstract": 0, "ch_all": 4, "ch_diff": 2},
                    {"artifact": "#test-code", "abstract": 0, "ch_all": 30, "ch_diff": 30},
                ],
            )
            self.write_history_file(
                experiment_dir,
                "historyFinder",
                "projectB",
                [
                    {"artifact": "#main-code", "abstract": 0, "ch_all": 1, "ch_diff": 1},
                    {"artifact": "#test-code #test-case-method", "abstract": 0, "ch_all": 2, "ch_diff": 15},
                ],
            )
            output_directory = Path(tmpdir) / "paper-figure"

            main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--tools",
                    "historyFinder",
                    "--revision-types",
                    "ch_diff",
                    "--all-projects-only",
                    "--output-directory",
                    str(output_directory),
                ]
            )

            self.assertTrue((output_directory / "artifact-revision-cdf--historyFinder.pdf").exists())
            self.assertFalse((experiment_dir / "figure" / "artifact-revision-cdf--historyFinder.pdf").exists())

    def test_paper_plot_axis_labels_ticks_legend_and_title(self):
        df = pd.DataFrame(
            [
                {"method_kind": "main-code", "ch_diff": 0},
                {"method_kind": "main-code", "ch_diff": 1},
                {"method_kind": "main-code", "ch_diff": 11},
                {"method_kind": "test-code", "ch_diff": 1},
                {"method_kind": "test-code", "ch_diff": 2},
                {"method_kind": "test-code", "ch_diff": 11},
            ]
        )
        fig, ax = plt.subplots()
        try:
            plot_change_axis(ax, df, "ch_diff", 0, paper_mode=True)

            self.assertEqual("", ax.get_title())
            self.assertEqual("# Method Revisions", ax.get_xlabel())
            self.assertEqual("CDF", ax.get_ylabel())
            self.assertEqual(
                [str(value) for value in range(10)] + ["10+"],
                [tick.get_text() for tick in ax.get_xticklabels()],
            )
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            self.assertEqual(
                ["Test Method", "Production Method"],
                [text.get_text() for text in legend.get_texts()],
            )
            self.assertEqual([0, 1, 10], ax.lines[0].get_xdata().tolist())
            self.assertEqual([0, 10], ax.lines[1].get_xdata().tolist())
        finally:
            plt.close(fig)

    def test_default_plot_uses_integer_ticks_and_ten_plus_clip(self):
        df = pd.DataFrame(
            [
                {"method_kind": "main-code", "ch_diff": 1},
                {"method_kind": "main-code", "ch_diff": 12},
                {"method_kind": "test-code", "ch_diff": 2},
                {"method_kind": "test-code", "ch_diff": 11},
            ]
        )
        fig, ax = plt.subplots()
        try:
            plot_change_axis(ax, df, "ch_diff", 0, paper_mode=False)

            self.assertEqual("ch_diff", ax.get_title())
            self.assertEqual(
                [str(value) for value in range(10)] + ["10+"],
                [tick.get_text() for tick in ax.get_xticklabels()],
            )
            self.assertEqual((0.0, 10.0), ax.get_xlim())
            self.assertEqual([1, 10], ax.lines[0].get_xdata().tolist())
            self.assertEqual([0, 10], ax.lines[1].get_xdata().tolist())
        finally:
            plt.close(fig)

    def test_subsequent_revision_series_excludes_introduction(self):
        series = pd.Series([0, 1, 2, 11])

        self.assertEqual([0, 0, 1, 10], subsequent_revision_series(series).tolist())

    def write_history_file(
        self,
        experiment_dir: Path,
        tool: str,
        project: str,
        rows: list[dict],
    ) -> None:
        history_file = experiment_dir / "method-history" / tool / f"{project}.csv"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "project": project,
                    "artifact": row["artifact"],
                    "abstract": row["abstract"],
                    "ch_all": row["ch_all"],
                    "ch_diff": row["ch_diff"],
                }
                for row in rows
            ]
        ).to_csv(history_file, index=False)


if __name__ == "__main__":
    unittest.main()
