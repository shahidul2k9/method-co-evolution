from pathlib import Path
import sys
import tempfile
import unittest
import warnings

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.generator.method_call_statistics import STAT_COLUMNS, build_stat_row, main


class TestMethodCallStatistics(unittest.TestCase):
    def test_build_stat_row_classifies_methods_and_deduplicates_calls(self):
        method_df = pd.DataFrame(
            [
                {"url": "prod-a", "artifact": "#main-code"},
                {"url": "prod-b", "artifact": "#main-code"},
                {"url": "test-a", "artifact": "#test-code #test-case-method"},
                {"url": "test-b", "artifact": "#test-code #test-case-method"},
                {"url": "test-c", "artifact": "#test-code #test-case-method"},
                {"url": "helper", "artifact": "#test-code #test-helper-method"},
                {"url": "prod-a", "artifact": "#main-code"},
            ]
        )
        callgraph_df = pd.DataFrame(
            [
                {"from_url": "test-a", "to_url": "prod-a"},
                {"from_url": "test-a", "to_url": "prod-a"},
                {"from_url": "test-a", "to_url": "helper"},
                {"from_url": "test-b", "to_url": "prod-b"},
                {"from_url": "test-b", "to_url": "external"},
                {"from_url": "helper", "to_url": "prod-a"},
            ]
        )

        row = build_stat_row("demo", method_df, callgraph_df)

        self.assertEqual(
            {
                "project": "demo",
                "prod_methods": 2,
                "tests": 3,
                "unique_calls": 3,
                "median_calls": 1.0,
            },
            row,
        )

    def test_zero_call_tests_are_included_in_median(self):
        method_df = pd.DataFrame(
            [
                {"url": "prod-a", "artifact": "#main-code"},
                {"url": "test-a", "artifact": "#test-code #test-case-method"},
                {"url": "test-b", "artifact": "#test-code #test-case-method"},
                {"url": "test-c", "artifact": "#test-code #test-case-method"},
                {"url": "test-d", "artifact": "#test-code #test-case-method"},
            ]
        )
        callgraph_df = pd.DataFrame(
            [
                {"from_url": "test-a", "to_url": "prod-a"},
                {"from_url": "test-b", "to_url": "prod-a"},
            ]
        )

        row = build_stat_row("demo", method_df, callgraph_df)

        self.assertEqual(0.5, row["median_calls"])

    def test_main_filters_projects_skips_missing_inputs_and_orders_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir, ["zeta", "alpha", "missing"])
            self.write_project_inputs(experiment_dir, "zeta")
            self.write_project_inputs(experiment_dir, "alpha")
            (experiment_dir / "method").mkdir(exist_ok=True)
            pd.DataFrame([{"url": "test", "artifact": "#test-code #test-case-method"}]).to_csv(
                experiment_dir / "method" / "missing.csv",
                index=False,
            )

            with warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                output_file = main(
                    [
                        "--workspace-directory",
                        tmpdir,
                        "--experiment-name",
                        "demo",
                        "--projects",
                        "zeta,missing,alpha",
                    ]
                )

            output_df = pd.read_csv(output_file)
            self.assertEqual(STAT_COLUMNS, output_df.columns.tolist())
            self.assertEqual(["alpha", "zeta"], output_df["project"].tolist())
            self.assertTrue(any("missing callgraph file" in str(item.message) for item in caught))
            self.assertEqual(experiment_dir / "aggregate" / "method-call-statistics.csv", output_file)

    def test_main_no_replace_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir, ["demo"])
            output_file = experiment_dir / "aggregate" / "method-call-statistics.csv"
            output_file.parent.mkdir(parents=True)
            output_file.write_text("sentinel\n")

            main(["--workspace-directory", tmpdir, "--experiment-name", "demo", "--no-replace"])

            self.assertEqual("sentinel\n", output_file.read_text())

    def create_experiment(self, workspace_dir: str, projects: list[str]) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo"
        experiment_dir.mkdir(parents=True)
        pd.DataFrame({"project": projects}).to_csv(experiment_dir / "project.csv", index=False)
        return experiment_dir

    def write_project_inputs(self, experiment_dir: Path, project: str) -> None:
        method_file = experiment_dir / "method" / f"{project}.csv"
        callgraph_file = experiment_dir / "callgraph" / f"{project}.csv"
        method_file.parent.mkdir(parents=True, exist_ok=True)
        callgraph_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {"url": f"{project}-prod", "artifact": "#main-code"},
                {"url": f"{project}-test", "artifact": "#test-code #test-case-method"},
            ]
        ).to_csv(method_file, index=False)
        pd.DataFrame(
            [{"from_url": f"{project}-test", "to_url": f"{project}-prod"}]
        ).to_csv(callgraph_file, index=False)


if __name__ == "__main__":
    unittest.main()
