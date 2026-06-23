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
from ptc.generator.filter_artifact import main as filter_artifact_main
from ptc.generator.artifact_revision_mww import (
    MIN_REVISION_METHODS_FOR_MWU,
    build_stat_row,
    classify_method_kind,
    main,
    subsequent_revision_series,
)


@unittest.skipIf(pd is None, "pandas is required for generate_revision_mwu tests")
class TestGenerateRevisionMwu(unittest.TestCase):
    def test_classifies_test_case_methods_as_test_methods(self):
        self.assertEqual("test-case-method", classify_method_kind("#test-code #test-case-method"))
        self.assertIsNone(classify_method_kind("#test-code"))
        self.assertIsNone(classify_method_kind("#test-code #test-helper-method"))
        self.assertEqual("main-code", classify_method_kind("#main-code"))

    def test_subsequent_revision_series_excludes_introduction(self):
        series = pd.Series([0, 1, 2, 11])

        self.assertEqual([0, 0, 1, 10], subsequent_revision_series(series).tolist())

    def test_build_stat_row_compares_post_introduction_revisions(self):
        project_df = pd.DataFrame(
            [
                {"method_kind": "main-code", "ch_diff": 1},
                {"method_kind": "main-code", "ch_diff": 2},
                {"method_kind": "test-case-method", "ch_diff": 0},
                {"method_kind": "test-case-method", "ch_diff": 2},
            ]
        )

        row = build_stat_row("demo", "historyFinder", "ch_diff", project_df)

        self.assertIsNotNone(row)
        self.assertEqual(4, row["size"])
        self.assertEqual(2, row["main_size"])
        self.assertEqual(2, row["test_size"])
        self.assertEqual(0.0, row["d_value"])
        self.assertEqual("=", row["d_sign"])

    def test_generates_revision_mwu_rows_and_markers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_method_history_rows(
                experiment_dir,
                "historyFinder",
                "demo",
                main_values=list(range(30, 46)),
                test_values=list(range(15)),
            )
            method_code_file = experiment_dir / "method-code" / "demo.csv"
            method_code_df = pd.read_csv(method_code_file, keep_default_na=False, na_filter=False)
            method_code_df.loc[method_code_df["url"].str.endswith("Method0.java#L1"), "code"] = ""
            method_code_df.to_csv(method_code_file, index=False)

            pd.DataFrame([{"project": "demo"}]).to_csv(experiment_dir / "project.csv", index=False)
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                filter_artifact_main(["--workspace-directory", tmpdir, "--experiment-name", "demo"])
                main(["--workspace-directory", tmpdir, "--experiment-name", "demo"])

            output_df = pd.read_csv(
                experiment_dir / "aggregate" / "artifact-revision-mww.csv",
                keep_default_na=False,
            )
            self.assertIn("demo", set(output_df["project"]))
            self.assertIn(ALL_REPOSITORY, set(output_df["project"]))
            self.assertNotIn("strategy", output_df.columns)
            self.assertNotIn("corr", output_df.columns)
            self.assertNotIn("corr_p", output_df.columns)

            diff_row = output_df[(output_df["project"] == "demo") & (output_df["change"] == "diff")].iloc[0]
            self.assertEqual("historyFinder", diff_row["tool"])
            self.assertEqual(MIN_REVISION_METHODS_FOR_MWU, diff_row["size"])
            self.assertEqual(MIN_REVISION_METHODS_FOR_MWU // 2, diff_row["main_size"])
            self.assertEqual(MIN_REVISION_METHODS_FOR_MWU // 2, diff_row["test_size"])
            self.assertIn(diff_row["effect_size"], {"negligible", "small", "medium", "large"})
            marked_columns = [column for column in ["N", "S", "M", "L"] if diff_row[column] == "x"]
            self.assertEqual(1, len(marked_columns))
            self.assertIn(
                "project=demo: 1 invalid abstract values out of 35 methods.",
                [str(warning.message) for warning in caught_warnings],
            )
            self.assertIn(
                "Dropping 1 method-history rows with missing method code in project=demo.",
                [str(warning.message) for warning in caught_warnings],
            )

    def test_skips_below_threshold_and_missing_group_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_rows(
                experiment_dir,
                "historyFinder",
                "small",
                [
                    {"artifact": "#main-code", "abstract": 0, "ch_all": 1, "ch_diff": 1},
                    {"artifact": "#test-code #test-case-method", "abstract": 0, "ch_all": 2, "ch_diff": 2},
                ],
            )
            self.write_rows(
                experiment_dir,
                "historyFinder",
                "mainOnly",
                [
                    {"artifact": "#main-code", "abstract": 0, "ch_all": 1, "ch_diff": 1},
                    {"artifact": "#main-code", "abstract": 0, "ch_all": 2, "ch_diff": 2},
                    {"artifact": "#main-code", "abstract": 0, "ch_all": 3, "ch_diff": 3},
                ],
            )

            pd.DataFrame([{"project": "small"}, {"project": "mainOnly"}]).to_csv(
                experiment_dir / "project.csv",
                index=False,
            )
            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                filter_artifact_main(["--workspace-directory", tmpdir, "--experiment-name", "demo"])
                main(["--workspace-directory", tmpdir, "--experiment-name", "demo"])

            output_df = pd.read_csv(experiment_dir / "aggregate" / "artifact-revision-mww.csv")
            self.assertNotIn("small", set(output_df["project"]))
            self.assertNotIn("mainOnly", set(output_df["project"]))
            self.assertTrue(any("project=small" in str(warning.message) for warning in caught_warnings))

    def create_experiment(self, workspace_dir: str) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo"
        (experiment_dir / "method-history").mkdir(parents=True)
        pd.DataFrame(columns=["project"]).to_csv(experiment_dir / "project.csv", index=False)
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
            rows.append({"artifact": "#main-code", "abstract": 0, "ch_all": value, "ch_diff": value})
        for value in test_values:
            rows.append({"artifact": "#test-code #test-case-method", "abstract": 0, "ch_all": value, "ch_diff": value})
        rows.extend(
            [
                {"artifact": "#main-code", "abstract": 1, "ch_all": 999, "ch_diff": 999},
                {"artifact": "#test-code #test-case-method", "abstract": 1, "ch_all": 999, "ch_diff": 999},
                {"artifact": "#test-code #test-helper-method", "abstract": 0, "ch_all": 997, "ch_diff": 997},
                {"artifact": "#main-code", "abstract": "", "ch_all": 998, "ch_diff": 998},
            ]
        )
        self.write_rows(experiment_dir, tool, project, rows)

    def write_rows(self, experiment_dir: Path, tool: str, project: str, rows: list[dict]) -> None:
        output_file = experiment_dir / "method-history" / tool / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        full_rows = [
            {
                "project": project,
                "name": f"method{index}",
                "url": f"https://example.test/{project}/Method{index}.java#L1",
                "artifact": row["artifact"],
                "abstract": row["abstract"],
                "ch_all": row["ch_all"],
                "ch_diff": row["ch_diff"],
            }
            for index, row in enumerate(rows)
        ]
        pd.DataFrame(full_rows).to_csv(output_file, index=False)
        method_file = experiment_dir / "method" / f"{project}.csv"
        method_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(full_rows).to_csv(method_file, index=False)
        self.write_method_code_rows(experiment_dir, project, full_rows)

    def write_method_code_rows(self, experiment_dir: Path, project: str, rows: list[dict]) -> None:
        output_file = experiment_dir / "method-code" / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "project": project,
                    "name": row["name"],
                    "url": row["url"],
                    "artifact": "#method-code-artifact-must-not-be-used",
                    "start_line": 1,
                    "end_line": 1,
                    "code": f"public int {row['name']}() {{ return 1; }}",
                }
                for row in rows
            ]
        ).to_csv(output_file, index=False)


if __name__ == "__main__":
    unittest.main()
