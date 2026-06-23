from pathlib import Path
import sys
import tempfile
import unittest

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from ptc.plot.t2p_correlation_cdf import (
    PAPER_CORRELATION_COLOR,
    PAPER_CORRELATION_LABEL_SIZE,
    PAPER_CORRELATION_LINE_WIDTH,
    PAPER_CORRELATION_TICK_LABEL_SIZE,
    main,
    plot_correlation_only_axis,
)


class TestT2PCorrelationCdf(unittest.TestCase):
    def test_correlation_only_axis_uses_paper_labels_and_colored_line_without_markers(self):
        df = pd.DataFrame(
            [
                {"change": "diff", "corr": -0.5},
                {"change": "diff", "corr": 0.0},
                {"change": "diff", "corr": 0.5},
                {"change": "all", "corr": 0.9},
            ]
        )

        fig, ax = plt.subplots()
        try:
            plot_correlation_only_axis(ax, df, ["diff"])

            self.assertEqual("Correlation Coefficient", ax.get_xlabel())
            self.assertEqual("CDF", ax.get_ylabel())
            self.assertEqual((-0.55, 0.55), ax.get_xlim())
            self.assertEqual(1, len(ax.lines))
            self.assertEqual(PAPER_CORRELATION_COLOR, ax.lines[0].get_color())
            self.assertEqual(PAPER_CORRELATION_LINE_WIDTH, ax.lines[0].get_linewidth())
            self.assertEqual("None", ax.lines[0].get_marker())
            self.assertEqual(PAPER_CORRELATION_LABEL_SIZE, ax.xaxis.label.get_fontsize())
            self.assertEqual(PAPER_CORRELATION_LABEL_SIZE, ax.yaxis.label.get_fontsize())
            self.assertEqual(PAPER_CORRELATION_TICK_LABEL_SIZE, ax.xaxis.get_ticklabels()[0].get_fontsize())
            self.assertEqual(PAPER_CORRELATION_TICK_LABEL_SIZE, ax.yaxis.get_ticklabels()[0].get_fontsize())
            self.assertAlmostEqual(0.2, ax.xaxis.get_major_locator()._edge.step)
            self.assertAlmostEqual(0.2, ax.yaxis.get_major_locator()._edge.step)
            self.assertAlmostEqual(0.1, ax.xaxis.get_minor_locator()._edge.step)
            self.assertAlmostEqual(0.1, ax.yaxis.get_minor_locator()._edge.step)
        finally:
            plt.close(fig)

    def test_main_writes_correlation_only_plot_with_strategy_in_filename(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            experiment_dir = root / "workspace" / "experiment" / "demo"
            aggregate_file = experiment_dir / "aggregate" / "t2p-correlation.csv"
            aggregate_file.parent.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "project": "project-a",
                        "tool": "historyFinder",
                        "strategy": "omc--nc",
                        "size": 3,
                        "change": "diff",
                        "corr": -0.2,
                        "corr_p": 0.4,
                        "mwu_p": 0.1,
                        "mwu_size": "small",
                    },
                    {
                        "project": "project-b",
                        "tool": "historyFinder",
                        "strategy": "omc--nc",
                        "size": 3,
                        "change": "diff",
                        "corr": 0.5,
                        "corr_p": 0.2,
                        "mwu_p": 0.3,
                        "mwu_size": "negligible",
                    },
                    {
                        "project": "project-a",
                        "tool": "historyFinder",
                        "strategy": "nc",
                        "size": 3,
                        "change": "diff",
                        "corr": 0.8,
                        "corr_p": 0.1,
                        "mwu_p": 0.6,
                        "mwu_size": "large",
                    },
                    {
                        "project": "all",
                        "tool": "historyFinder",
                        "strategy": "omc--nc",
                        "size": 6,
                        "change": "diff",
                        "corr": 0.9,
                        "corr_p": 0.0,
                        "mwu_p": 0.0,
                        "mwu_size": "large",
                    },
                ]
            ).to_csv(aggregate_file, index=False)
            output_directory = root / "paper" / "figure"

            main(
                [
                    "--project-directory",
                    str(root),
                    "--workspace-directory",
                    str(root / "workspace"),
                    "--experiment-name",
                    "demo",
                    "--tools",
                    "historyFinder",
                    "--strategies",
                    "omc--nc",
                    "--revision-types",
                    "ch_diff",
                    "--correlation-only",
                    "--output-directory",
                    "paper/figure",
                ]
            )

            self.assertTrue(
                (output_directory / "t2p-correlation-cdf--historyFinder--omc--nc.pdf").exists()
            )
            self.assertFalse((output_directory / "t2p-correlation-cdf--historyFinder--nc.pdf").exists())
            self.assertFalse((experiment_dir / "figure" / "t2p-correlation-cdf--historyFinder.pdf").exists())


if __name__ == "__main__":
    unittest.main()
