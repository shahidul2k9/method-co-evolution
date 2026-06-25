from pathlib import Path
import sys
import tempfile
import unittest
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

from ptc.plot.t2p_revision_delta_cdf import (
    PAPER_LABEL_SIZE,
    PAPER_MAX_DISPLAY_DELTA,
    PAPER_SERIES_COLOR,
    PAPER_TICK_LABEL_SIZE,
    clipped_delta_cdf,
    delta_cdf,
    delta_threshold,
    draw_row_info_axis,
    main,
    plot_paper_delta_axis,
    revision_delta_group_counts,
)


@unittest.skipIf(pd is None, "pandas is required for t2p revision delta plot tests")
class TestT2PRevisionDeltaPlot(unittest.TestCase):
    def test_delta_cdf_uses_test_minus_production(self):
        df = pd.DataFrame(
            [
                {"from_ch_all": 5, "to_ch_all": 0},
                {"from_ch_all": 1, "to_ch_all": 1},
                {"from_ch_all": 0, "to_ch_all": 2},
                {"from_ch_all": 1, "to_ch_all": 3},
            ]
        )

        cdf = delta_cdf(df, "ch_all")

        self.assertEqual(
            {-2: 0.5, -1: 0.5, 0: 0.75, 1: 0.75, 2: 0.75, 3: 0.75, 4: 0.75, 5: 1.0},
            cdf.to_dict(),
        )

    def test_delta_threshold_uses_first_integer_at_80_percent(self):
        df = pd.DataFrame(
            [
                {"from_ch_all": -2, "to_ch_all": 0},
                {"from_ch_all": -1, "to_ch_all": 0},
                {"from_ch_all": 0, "to_ch_all": 0},
                {"from_ch_all": 1, "to_ch_all": 0},
                {"from_ch_all": 2, "to_ch_all": 0},
            ]
        )

        threshold = delta_threshold(df, "ch_all")

        self.assertIsNotNone(threshold)
        self.assertEqual(1, threshold.x)
        self.assertAlmostEqual(80.0, threshold.covered_pct)
        self.assertAlmostEqual(40.0, threshold.tail_pct)

    def test_delta_threshold_ties_can_cover_more_than_80_percent(self):
        df = pd.DataFrame(
            [
                {"from_ch_all": 0, "to_ch_all": 0},
                {"from_ch_all": 0, "to_ch_all": 0},
                {"from_ch_all": 0, "to_ch_all": 0},
                {"from_ch_all": 0, "to_ch_all": 0},
                {"from_ch_all": 0, "to_ch_all": 0},
                {"from_ch_all": 1, "to_ch_all": 0},
            ]
        )

        threshold = delta_threshold(df, "ch_all")

        self.assertIsNotNone(threshold)
        self.assertEqual(0, threshold.x)
        self.assertAlmostEqual(83.33333333333334, threshold.covered_pct)
        self.assertAlmostEqual(100.0, threshold.tail_pct)

    def test_delta_threshold_returns_none_for_empty_numeric_pairs(self):
        df = pd.DataFrame(
            [
                {"from_ch_all": "not-a-number", "to_ch_all": 0},
                {"from_ch_all": 1, "to_ch_all": "not-a-number"},
            ]
        )

        self.assertIsNone(delta_threshold(df, "ch_all"))

    def test_paper_delta_cdf_clips_extremes_and_counts_revision_groups(self):
        delta = pd.Series([-15, -1, 0, 1, 4, 5, 20])

        cdf = clipped_delta_cdf(delta)
        groups = revision_delta_group_counts(delta)

        self.assertEqual(-10, cdf.index.min())
        self.assertEqual(PAPER_MAX_DISPLAY_DELTA, cdf.index.max())
        self.assertAlmostEqual(1 / 7, cdf.loc[-10])
        self.assertAlmostEqual(6 / 7, cdf.loc[5])
        self.assertAlmostEqual(1.0, cdf.loc[PAPER_MAX_DISPLAY_DELTA])
        self.assertEqual(
            [
                ("NTR", "<=0", 3, 42.9),
                ("ATR", "1-4", 2, 28.6),
                ("HTR", "5+", 2, 28.6),
            ],
            [(code, label, count, round(percent, 1)) for code, label, count, percent in groups],
        )

    def test_paper_delta_axis_uses_linear_clipped_axis_and_tenth_y_ticks(self):
        df = pd.DataFrame(
            [
                {"from_ch_diff": -15, "to_ch_diff": 0},
                {"from_ch_diff": 0, "to_ch_diff": 0},
                {"from_ch_diff": 4, "to_ch_diff": 0},
                {"from_ch_diff": 5, "to_ch_diff": 0},
            ]
        )

        fig, ax = plt.subplots()
        try:
            plot_paper_delta_axis(ax, df, "ch_diff")

            self.assertEqual("# Test - Production Revisions", ax.get_xlabel())
            self.assertEqual("CDF", ax.get_ylabel())
            self.assertEqual((-10.0, 10.0), ax.get_xlim())
            self.assertEqual([0.1, 0.2, 0.3], [round(value, 1) for value in ax.get_yticks()[:3]])
            self.assertGreaterEqual(len(ax.lines), 1)
            self.assertEqual(PAPER_SERIES_COLOR, ax.lines[0].get_color())
            self.assertEqual(PAPER_LABEL_SIZE, ax.xaxis.label.get_fontsize())
            self.assertEqual(PAPER_LABEL_SIZE, ax.yaxis.label.get_fontsize())
            self.assertEqual(PAPER_TICK_LABEL_SIZE, ax.xaxis.get_ticklabels()[0].get_fontsize())
            self.assertEqual(PAPER_TICK_LABEL_SIZE, ax.yaxis.get_ticklabels()[0].get_fontsize())
            self.assertIn("NTR (<=0): 2 (50.0%)", ax.texts[0].get_text())
            self.assertIn("ATR (1-4): 1 (25.0%)", ax.texts[0].get_text())
            self.assertIn("HTR (5+): 1 (25.0%)", ax.texts[0].get_text())
        finally:
            plt.close(fig)

    def test_delta_axis_shows_revision_group_summary_by_default(self):
        df = pd.DataFrame(
            [
                {"from_ch_diff": 0, "to_ch_diff": 0},
                {"from_ch_diff": 4, "to_ch_diff": 0},
                {"from_ch_diff": 5, "to_ch_diff": 0},
            ]
        )

        fig, ax = plt.subplots()
        try:
            plot_paper_delta_axis(ax, df, "ch_diff")

            self.assertIn("NTR (<=0): 1 (33.3%)", ax.texts[0].get_text())
            self.assertIn("ATR (1-4): 1 (33.3%)", ax.texts[0].get_text())
            self.assertIn("HTR (5+): 1 (33.3%)", ax.texts[0].get_text())
        finally:
            plt.close(fig)

    def test_generates_cdf_plot_for_selected_filters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "nc", "projectA")
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "other", "projectA")
            self.write_t2p_change_rows(experiment_dir, "codeShovel", "nc", "projectA")
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "nc", "projectB")

            main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--tools",
                    "historyFinder",
                    "--strategies",
                    "nc",
                    "--projects",
                    "projectA",
                    "--min-t2p-links",
                    "0",
                ]
            )

            selected_plot = experiment_dir / "figure" / "t2p-revision-delta-cdf--historyFinder--nc.pdf"
            unselected_strategy_plot = (
                experiment_dir / "figure" / "t2p-revision-delta-cdf--historyFinder--other.pdf"
            )
            unselected_tool_plot = experiment_dir / "figure" / "t2p-revision-delta-cdf--codeShovel--nc.pdf"

            self.assertTrue(selected_plot.exists())
            self.assertFalse(unselected_strategy_plot.exists())
            self.assertFalse(unselected_tool_plot.exists())

    def test_all_projects_only_writes_paper_plot_to_output_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "omc--nc", "projectA")
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "omc--nc", "projectB")
            output_directory = Path(tmpdir) / "paper-figure"

            main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--tools",
                    "historyFinder",
                    "--strategies",
                    "omc--nc",
                    "--revision-types",
                    "ch_diff",
                    "--all-projects-only",
                    "--min-t2p-links",
                    "0",
                    "--output-directory",
                    str(output_directory),
                ]
            )

            self.assertTrue(
                (
                    output_directory
                    / "t2p-revision-delta-cdf--historyFinder--omc--nc.pdf"
                ).exists()
            )
            self.assertFalse(
                (experiment_dir / "figure" / "t2p-revision-delta-cdf--historyFinder--omc--nc.pdf").exists()
            )

    def test_row_info_axis_hides_revision_groups_and_test_production_counts(self):
        df = pd.DataFrame(
            [
                {"from_ch_diff": 0, "to_ch_diff": 2},
                {"from_ch_diff": 0, "to_ch_diff": 0},
                {"from_ch_diff": 4, "to_ch_diff": 0},
                {"from_ch_diff": 10, "to_ch_diff": 0},
            ]
        )

        fig, ax = plt.subplots()
        try:
            draw_row_info_axis(ax, "projectA", df)

            info_text = ax.texts[1].get_text()
            self.assertIn("total=4", info_text)
            self.assertNotIn("NTR", info_text)
            self.assertNotIn("ATR", info_text)
            self.assertNotIn("HTR", info_text)
            self.assertNotIn("test=", info_text)
            self.assertNotIn("production=", info_text)
            self.assertIsNone(ax.get_legend())
        finally:
            plt.close(fig)

    def test_codeshovel_unsupported_change_still_generates_plot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "codeShovel", "nc", "projectA")

            main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--tools",
                    "codeShovel",
                    "--strategies",
                    "nc",
                    "--projects",
                    "projectA",
                    "--min-t2p-links",
                    "0",
                ]
            )

            self.assertTrue(
                (experiment_dir / "figure" / "t2p-revision-delta-cdf--codeShovel--nc.pdf").exists()
            )

    def test_min_t2p_links_skips_small_projects_with_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "nc", "projectA")

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
                        "--strategies",
                        "nc",
                        "--projects",
                        "projectA",
                        "--min-t2p-links",
                        "4",
                    ]
                )

            self.assertFalse(
                (experiment_dir / "figure" / "t2p-revision-delta-cdf--historyFinder--nc.pdf").exists()
            )
            self.assertTrue(
                any("t2p_links=3 is below min_t2p_links=4" in str(warning.message) for warning in caught_warnings)
            )

    def create_experiment(self, workspace_dir: str) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo"
        (experiment_dir / "t2p-change").mkdir(parents=True)
        return experiment_dir

    def write_t2p_change_rows(
        self,
        experiment_dir: Path,
        tool: str,
        strategy: str,
        project: str,
    ) -> None:
        output_file = experiment_dir / "t2p-change" / tool / strategy / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "project": project,
                "from_ch_all": 5,
                "to_ch_all": 0,
                "from_ch_diff": 2,
                "to_ch_diff": 4,
                "from_ch_documentation": 1,
                "to_ch_documentation": 3,
            },
            {
                "project": project,
                "from_ch_all": 1,
                "to_ch_all": 1,
                "from_ch_diff": 0,
                "to_ch_diff": 1,
                "from_ch_documentation": 0,
                "to_ch_documentation": 2,
            },
            {
                "project": project,
                "from_ch_all": 0,
                "to_ch_all": 2,
                "from_ch_diff": 2,
                "to_ch_diff": 0,
                "from_ch_documentation": 4,
                "to_ch_documentation": 1,
            },
        ]
        pd.DataFrame(rows).to_csv(output_file, index=False)


if __name__ == "__main__":
    unittest.main()
