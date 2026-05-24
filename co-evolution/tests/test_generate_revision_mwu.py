from pathlib import Path
import sys
import tempfile
import unittest
import warnings

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

from ptc.constants import ALL_REPOSITORY
from ptc.generator.revision_mww import main


@unittest.skipIf(pd is None, "pandas is required for generate_revision_mwu tests")
class TestGenerateRevisionMwu(unittest.TestCase):
    def test_generates_revision_mwu_rows_and_markers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_method_history_rows(
                experiment_dir,
                "historyFinder",
                "demo",
                main_values=[10, 11, 12],
                test_values=[0, 1, 2],
            )

            main(["--workspace-directory", tmpdir, "--experiment-name", "demo"])

            output_df = pd.read_csv(experiment_dir / "aggregate" / "revision_mwu.csv", keep_default_na=False)
            self.assertIn("demo", set(output_df["project"]))
            self.assertIn(ALL_REPOSITORY, set(output_df["project"]))
            self.assertNotIn("strategy", output_df.columns)
            self.assertNotIn("corr", output_df.columns)
            self.assertNotIn("corr_p", output_df.columns)

            diff_row = output_df[(output_df["project"] == "demo") & (output_df["change"] == "diff")].iloc[0]
            self.assertEqual("historyFinder", diff_row["tool"])
            self.assertEqual(6, diff_row["size"])
            self.assertEqual(3, diff_row["main_size"])
            self.assertEqual(3, diff_row["test_size"])
            self.assertIn(diff_row["mwu_size"], {"negligible", "small", "medium", "large"})
            marked_columns = [column for column in ["N", "S", "M", "L"] if diff_row[column] == "x"]
            self.assertEqual(1, len(marked_columns))

    def test_skips_below_threshold_and_missing_group_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_rows(
                experiment_dir,
                "historyFinder",
                "small",
                [
                    {"artifact": "#main-code", "ch_all": 1, "ch_diff": 1},
                    {"artifact": "#test-code", "ch_all": 2, "ch_diff": 2},
                ],
            )
            self.write_rows(
                experiment_dir,
                "historyFinder",
                "mainOnly",
                [
                    {"artifact": "#main-code", "ch_all": 1, "ch_diff": 1},
                    {"artifact": "#main-code", "ch_all": 2, "ch_diff": 2},
                    {"artifact": "#main-code", "ch_all": 3, "ch_diff": 3},
                ],
            )

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                main(["--workspace-directory", tmpdir, "--experiment-name", "demo"])

            output_df = pd.read_csv(experiment_dir / "aggregate" / "revision_mwu.csv")
            self.assertNotIn("small", set(output_df["project"]))
            self.assertNotIn("mainOnly", set(output_df["project"]))
            self.assertTrue(any("project=small" in str(warning.message) for warning in caught_warnings))

    def create_experiment(self, workspace_dir: str) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo"
        (experiment_dir / "method-history").mkdir(parents=True)
        return experiment_dir

    def write_method_history_rows(
        self,
        experiment_dir: Path,
        tool: str,
        project: str,
        main_values: list[int],
        test_values: list[int],
    ) -> None:
        rows = []
        for value in main_values:
            rows.append({"artifact": "#main-code", "ch_all": value, "ch_diff": value})
        for value in test_values:
            rows.append({"artifact": "#test-code", "ch_all": value, "ch_diff": value})
        self.write_rows(experiment_dir, tool, project, rows)

    def write_rows(self, experiment_dir: Path, tool: str, project: str, rows: list[dict]) -> None:
        output_file = experiment_dir / "method-history" / tool / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        full_rows = [
            {
                "project": project,
                "name": f"method{index}",
                "artifact": row["artifact"],
                "ch_all": row["ch_all"],
                "ch_diff": row["ch_diff"],
            }
            for index, row in enumerate(rows)
        ]
        pd.DataFrame(full_rows).to_csv(output_file, index=False)


if __name__ == "__main__":
    unittest.main()
