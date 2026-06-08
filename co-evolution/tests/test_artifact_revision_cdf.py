from pathlib import Path
import sys
import tempfile
import unittest
import warnings

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from ptc.plot.artifact_revision_cdf import build_project_stats, classify_method_kind, main
from ptc.util.helper import filter_concrete_methods


class TestArtifactRevisionCdf(unittest.TestCase):
    def test_abstract_methods_are_excluded_from_cdf_population_and_counts(self):
        df = pd.DataFrame(
            [
                {"name": "concrete-main", "artifact": "#main-code", "abstract": 0, "ch_diff": 2},
                {"name": "abstract-main", "artifact": "#main-code", "abstract": 1, "ch_diff": 99},
                {"name": "concrete-test", "artifact": "#test-code", "abstract": 0, "ch_diff": 3},
                {"name": "abstract-test", "artifact": "#test-code", "abstract": 1, "ch_diff": 98},
                {"name": "invalid-test", "artifact": "#test-code", "abstract": "", "ch_diff": 97},
            ]
        )

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            concrete_df = filter_concrete_methods(df)
        concrete_df["method_kind"] = concrete_df["artifact"].map(classify_method_kind)

        self.assertEqual(["concrete-main", "concrete-test"], concrete_df["name"].tolist())
        self.assertEqual({"total": 2, "test": 1, "production": 1}, build_project_stats(concrete_df))
        self.assertEqual([2, 3], concrete_df["ch_diff"].tolist())
        self.assertEqual(
            ["project=<unknown>: 1 invalid abstract values out of 5 methods."],
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
                    {"project": "projectA", "artifact": "#test-code", "abstract": 0, "ch_diff": 3},
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
                "project=projectA: 1 invalid abstract values out of 3 methods.",
                [str(warning.message) for warning in caught_warnings],
            )


if __name__ == "__main__":
    unittest.main()
