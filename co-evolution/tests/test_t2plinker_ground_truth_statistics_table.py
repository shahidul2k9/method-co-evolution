from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.plot.t2plinker_ground_truth_statistics_table import (
    build_statistics_table,
    calculate_ground_truth_statistics,
    main,
    render_latex_table,
)


class TestT2PLinkerGroundTruthStatisticsTable(unittest.TestCase):
    def ground_truth_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {"from_url": "test-a", "to_url": "method-1", "candidate": 1, "label": 1, "tags": ""},
                {"from_url": "test-a", "to_url": "method-1", "candidate": 1, "label": 1, "tags": ""},
                {"from_url": "test-a", "to_url": "method-2", "candidate": 0, "label": 1, "tags": ""},
                {"from_url": "test-b", "to_url": "method-3", "candidate": 1, "label": 0, "tags": "#implicit-production-method"},
                {"from_url": "test-c", "to_url": "method-4", "candidate": 1, "label": 0, "tags": "#implicit-method-call"},
            ]
        )

    def test_calculates_calls_median_and_links_from_ground_truth(self):
        statistics = calculate_ground_truth_statistics(self.ground_truth_df())
        self.assertEqual(2, statistics["method_calls"])
        self.assertEqual(1.0, statistics["median_method_calls"])
        self.assertEqual(2, statistics["ground_truth_links"])

    def test_fully_filtered_tests_contribute_zero_to_median(self):
        ground_truth_df = pd.DataFrame(
            [
                {"from_url": "a", "to_url": "1", "candidate": 1, "label": 0, "tags": ""},
                {"from_url": "a", "to_url": "2", "candidate": 1, "label": 0, "tags": ""},
                {"from_url": "b", "to_url": "3", "candidate": 0, "label": 0, "tags": ""},
            ]
        )
        self.assertEqual(1.0, calculate_ground_truth_statistics(ground_truth_df)["median_method_calls"])

    def test_exact_implicit_production_method_tag_is_required(self):
        ground_truth_df = pd.DataFrame(
            [
                {"from_url": "a", "to_url": "1", "candidate": 1, "label": 0, "tags": "#implicit-production-method-extra"},
                {"from_url": "a", "to_url": "2", "candidate": 1, "label": 0, "tags": "#other #implicit-production-method"},
            ]
        )
        self.assertEqual(1, calculate_ground_truth_statistics(ground_truth_df)["method_calls"])

    def test_builds_rows_in_filename_order_and_matches_projects_case_insensitively(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self.ground_truth_df().to_csv(root / "zeta.csv", index=False)
            self.ground_truth_df().to_csv(root / "Alpha.csv", index=False)
            method_statistics_df = pd.DataFrame(
                [
                    {"project": "alpha", "prod_methods": 100, "tests": 20},
                    {"project": "ZETA", "prod_methods": 200, "tests": 30},
                ]
            )
            table_df = build_statistics_table(method_statistics_df, list(root.glob("*.csv")))
            self.assertEqual(["Alpha", "zeta"], table_df["project"].tolist())
            self.assertEqual([100, 200], table_df["prod_methods"].tolist())

    def test_renders_booktabs_formatting_and_total_row(self):
        table_df = pd.DataFrame(
            [
                {"project": "project_a", "prod_methods": 1234, "tests": 20, "method_calls": 10, "median_method_calls": 2.5, "ground_truth_links": 3},
                {"project": "project-b", "prod_methods": 2000, "tests": 30, "method_calls": 20, "median_method_calls": 3.5, "ground_truth_links": 4},
            ]
        )
        latex = render_latex_table(table_df)
        self.assertIn(r"\begin{table*}", latex)
        self.assertIn(r"project\_a & 1,234 & 20 & 10 & 2.5 & 3 \\", latex)
        self.assertIn(r"\textbf{Total} & 3,234 & 50 & 30 & 3.0 & 7 \\", latex)
        self.assertEqual(2, latex.count(r"\midrule"))

    def test_validation_errors_are_helpful(self):
        with self.assertRaisesRegex(ValueError, "Ground-truth CSV is missing required"):
            calculate_ground_truth_statistics(self.ground_truth_df().drop(columns=["candidate"]))
        with self.assertRaisesRegex(ValueError, "No ground-truth CSV"):
            build_statistics_table(pd.DataFrame([{"project": "a", "prod_methods": 1, "tests": 1}]), [])
        with tempfile.TemporaryDirectory() as tmpdir:
            ground_truth_file = Path(tmpdir) / "unknown.csv"
            self.ground_truth_df().to_csv(ground_truth_file, index=False)
            with self.assertRaisesRegex(ValueError, "Missing method-call statistics row"):
                build_statistics_table(
                    pd.DataFrame([{"project": "a", "prod_methods": 1, "tests": 1}]),
                    [ground_truth_file],
                )

    def test_main_writes_default_and_explicit_output_paths(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace = root / "workspace"
            statistics_file = root / "data" / "main" / "method-call-statistics.csv"
            ground_truth_directory = root / "data" / "t2plinker" / "t2p-ground-truth"
            statistics_file.parent.mkdir(parents=True)
            ground_truth_directory.mkdir(parents=True)
            pd.DataFrame([{"project": "alpha", "prod_methods": 10, "tests": 2}]).to_csv(statistics_file, index=False)
            self.ground_truth_df().to_csv(ground_truth_directory / "alpha.csv", index=False)

            default_output = main(["--project-directory", str(root), "--workspace-directory", str(workspace), "--experiment-name", "demo"])
            explicit_output = main(["--project-directory", str(root), "--workspace-directory", str(workspace), "--experiment-name", "demo", "--output-directory", "paper/figure"])

            self.assertEqual(workspace / "experiment" / "demo" / "figure" / "t2plinker-ground-truth-statistics-table.tex", default_output)
            self.assertEqual(root / "paper" / "figure" / "t2plinker-ground-truth-statistics-table.tex", explicit_output)
            self.assertTrue(default_output.exists())
            self.assertTrue(explicit_output.exists())


if __name__ == "__main__":
    unittest.main()
