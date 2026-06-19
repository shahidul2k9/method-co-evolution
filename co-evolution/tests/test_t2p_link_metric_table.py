from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.plot.t2p_link_metric_table import (
    DATASET_LABELS,
    main,
    render_latex_table,
    select_average_rows,
)


class TestT2PLinkMetricTable(unittest.TestCase):
    def metric_df(self) -> pd.DataFrame:
        rows = []
        for experiment in DATASET_LABELS:
            for strategy, values in [
                ("nc", (2, 1, 3, 0.67, 0.40, 0.50, 0.45, None)),
                ("tarantula", (4, 2, 1, 0.67, 0.80, 0.73, 0.70, 0.75)),
            ]:
                rows.append(
                    {
                        "project": f"avg-{experiment}",
                        "experiment": experiment,
                        "strategy": strategy,
                        **dict(zip(("tp", "fp", "fn", "precision", "recall", "f1", "map", "auc"), values)),
                    }
                )
            rows.append(
                {
                    "project": "project-a",
                    "experiment": experiment,
                    "strategy": "nc",
                    "tp": 99,
                    "fp": 0,
                    "fn": 0,
                    "precision": 1,
                    "recall": 1,
                    "f1": 1,
                    "map": 1,
                    "auc": 1,
                }
            )
        return pd.DataFrame(rows)

    def test_selects_only_average_rows_in_dataset_and_strategy_order(self):
        result_df = select_average_rows(self.metric_df(), ["tarantula", "nc"])

        self.assertEqual(
            [experiment for experiment in DATASET_LABELS for _ in range(2)],
            result_df["experiment"].tolist(),
        )
        self.assertEqual(["tarantula", "nc"] * len(DATASET_LABELS), result_df["strategy"].tolist())
        self.assertNotIn(99, result_df["tp"].tolist())

    def test_renders_mappings_booktabs_bolding_and_missing_values(self):
        table_df = select_average_rows(self.metric_df(), ["nc", "tarantula"])

        latex = render_latex_table(table_df)

        self.assertTrue(latex.startswith(r"\begin{tabular}{llrrrrrrrr}"))
        self.assertNotIn(r"\begin{table}", latex)
        self.assertNotIn(r"\begin{table*}", latex)
        self.assertNotIn(r"\centering", latex)
        self.assertNotIn(r"\caption", latex)
        self.assertNotIn(r"\label", latex)
        self.assertIn(r"TCTracer ICSE~\cite{white_establishing_2020}", latex)
        self.assertIn(r"TCTracer ESE~\cite{white_tctracer_2022}", latex)
        self.assertIn(r"TestLinker TSE~\cite{sun_method-level_2024}", latex)
        self.assertIn(r"\multirow{2}{*}{Ours}", latex)
        self.assertIn(r"NC & 2 & 1 & 3 & \textbf{0.67}", latex)
        self.assertIn(r"Tarantula & 4 & 2 & 1 & \textbf{0.67}", latex)
        self.assertIn(r"\textbf{0.75}", latex)
        self.assertIn(" -- \\\\", latex)
        self.assertEqual(len(DATASET_LABELS), latex.count(r"\multirow{2}{*}"))
        self.assertEqual(len(DATASET_LABELS), latex.count(r"\midrule"))

    def test_validation_errors_are_helpful(self):
        with self.assertRaisesRegex(ValueError, "Missing display mapping"):
            select_average_rows(self.metric_df(), ["unknown"])

        with self.assertRaisesRegex(ValueError, "Unknown strategy for dataset"):
            select_average_rows(self.metric_df(), ["combined"])

        with self.assertRaisesRegex(ValueError, "Missing aggregate metric"):
            select_average_rows(
                self.metric_df()[self.metric_df()["experiment"] != "t2plinker-plus"],
                ["nc"],
            )

        with self.assertRaisesRegex(ValueError, "Missing required metric column"):
            select_average_rows(self.metric_df().drop(columns=["auc"]), ["nc"])

    def test_main_writes_to_explicit_output_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = root / "workspace"
            input_file = workspace / "t2p_link_overall_metric.csv"
            input_file.parent.mkdir(parents=True)
            self.metric_df().to_csv(input_file, index=False)

            output_file = main(
                [
                    "--project-directory",
                    str(root),
                    "--workspace-directory",
                    str(workspace),
                    "--experiment-name",
                    "demo",
                    "--strategies",
                    "tarantula,nc",
                    "--output-directory",
                    "paper/figure",
                ]
            )

            self.assertEqual(root / "paper" / "figure" / "t2p-link-metric-table.tex", output_file)
            self.assertTrue(output_file.exists())

    def test_main_writes_to_default_experiment_figure_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = root / "workspace"
            input_file = workspace / "t2p_link_overall_metric.csv"
            input_file.parent.mkdir(parents=True)
            self.metric_df().to_csv(input_file, index=False)

            output_file = main(
                [
                    "--project-directory",
                    str(root),
                    "--workspace-directory",
                    str(workspace),
                    "--experiment-name",
                    "demo",
                    "--strategies",
                    "nc",
                ]
            )

            self.assertEqual(
                workspace / "experiment" / "demo" / "figure" / "t2p-link-metric-table.tex",
                output_file,
            )


if __name__ == "__main__":
    unittest.main()
