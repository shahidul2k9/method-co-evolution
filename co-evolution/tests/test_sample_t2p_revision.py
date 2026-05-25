from pathlib import Path
import sys
import tempfile
import unittest
import warnings
from unittest import mock

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

from mhc.command_util import build_experiment_parser
from ptc.sample.sample_t2p_revision import (
    DEFAULT_MIN_T2P_REVISION,
    REVIEW_COLUMNS,
    build_parser,
    main,
    normalize_argv,
)


@unittest.skipIf(pd is None, "pandas is required for sample_t2p_revision tests")
class TestSampleT2PRevision(unittest.TestCase):
    def test_experiment_parser_exposes_revision_types_when_enabled(self):
        with mock.patch.dict("os.environ", {"ME_REVISION_TYPES": "ch_diff"}):
            parser = build_experiment_parser("demo", include_revision_types=True)

        args = parser.parse_args([])
        explicit_args = parser.parse_args(["--revision-types", "ch_all"])

        self.assertEqual("ch_diff", args.revision_types)
        self.assertEqual("ch_all", explicit_args.revision_types)

    def test_parser_defaults(self):
        with mock.patch.dict("os.environ", {"ME_REVISION_TYPES": "ch_diff", "ME_MIN_T2P_LINKS": "30"}):
            parser = build_parser()

        args = parser.parse_args([])

        self.assertEqual("ch_diff", args.revision_types)
        self.assertEqual(30, args.min_t2p_links)
        self.assertEqual(DEFAULT_MIN_T2P_REVISION, args.min_t2p_revision)

    def test_notebook_key_value_arguments_are_normalized(self):
        self.assertEqual(
            ["--tools", "historyFinder", "--strategies", "nc", "--min-t2p-revision", "10"],
            normalize_argv(["tools=historyFinder,strategies=nc,min-t2p-revision=10"]),
        )

    def test_rows_qualify_by_revision_delta(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(
                experiment_dir,
                "historyFinder",
                "nc",
                "demo",
                [
                    self.row("demo", "testA", "prodA", "test://A", "prod://A", 15, 4),
                    self.row("demo", "testB", "prodB", "test://B", "prod://B", 11, 2),
                    self.row("demo", "testC", "prodC", "test://C", "prod://C", 3, 0),
                ],
            )

            main([
                "--workspace-directory",
                tmpdir,
                "--experiment-name",
                "demo-exp",
                "--tools",
                "historyFinder",
                "--strategies",
                "nc",
                "--projects",
                "demo",
                "--revision-types",
                "ch_diff",
                "--min-t2p-links",
                "0",
                "--min-t2p-revision",
                "9",
            ])

            output_df = self.read_review_csv(experiment_dir, "historyFinder", "nc", "demo")

            self.assertEqual(REVIEW_COLUMNS, output_df.columns.tolist())
            self.assertEqual(["test://A", "test://B"], output_df["from_url"].tolist())
            self.assertEqual(["", ""], output_df["label"].tolist())
            self.assertEqual(["", ""], output_df["tags"].tolist())
            self.assertEqual(["", ""], output_df["notes"].tolist())

    def test_project_below_min_t2p_links_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(
                experiment_dir,
                "historyFinder",
                "nc",
                "small",
                [self.row("small", "testA", "prodA", "test://A", "prod://A", 20, 0)],
            )

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                main([
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo-exp",
                    "--tools",
                    "historyFinder",
                    "--strategies",
                    "nc",
                    "--projects",
                    "small",
                    "--revision-types",
                    "ch_diff",
                    "--min-t2p-links",
                    "2",
                ])

            self.assertFalse(self.review_csv(experiment_dir, "historyFinder", "nc", "small").exists())
            self.assertTrue(
                any("t2p_links=1 is below min_t2p_links=2" in str(warning.message) for warning in caught_warnings)
            )

    def test_no_qualifying_rows_does_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(
                experiment_dir,
                "historyFinder",
                "nc",
                "demo",
                [self.row("demo", "testA", "prodA", "test://A", "prod://A", 5, 0)],
            )

            main([
                "--workspace-directory",
                tmpdir,
                "--experiment-name",
                "demo-exp",
                "--tools",
                "historyFinder",
                "--strategies",
                "nc",
                "--projects",
                "demo",
                "--revision-types",
                "ch_diff",
                "--min-t2p-links",
                "0",
                "--min-t2p-revision",
                "10",
            ])

            self.assertFalse(self.review_csv(experiment_dir, "historyFinder", "nc", "demo").exists())

    def test_existing_rows_are_preserved_and_duplicates_skipped(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(
                experiment_dir,
                "historyFinder",
                "nc",
                "demo",
                [
                    self.row("demo", "testA", "prodA", "test://A", "prod://A", 20, 0),
                    self.row("demo", "testB", "prodB", "test://B", "prod://B", 20, 0),
                ],
            )
            existing_file = self.review_csv(experiment_dir, "historyFinder", "nc", "demo")
            existing_file.parent.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_name": "manualTestA",
                        "to_name": "manualProdA",
                        "from_url": "test://A",
                        "to_url": "prod://A",
                        "label": "1",
                        "tags": "reviewed",
                        "notes": "keep me",
                    }
                ],
                columns=REVIEW_COLUMNS,
            ).to_csv(existing_file, index=False)

            main([
                "--workspace-directory",
                tmpdir,
                "--experiment-name",
                "demo-exp",
                "--tools",
                "historyFinder",
                "--strategies",
                "nc",
                "--projects",
                "demo",
                "--revision-types",
                "ch_diff",
                "--min-t2p-links",
                "0",
            ])

            output_df = self.read_review_csv(experiment_dir, "historyFinder", "nc", "demo")

            self.assertEqual(["test://A", "test://B"], output_df["from_url"].tolist())
            preserved = output_df[output_df["from_url"] == "test://A"].iloc[0]
            self.assertEqual("manualTestA", preserved["from_name"])
            self.assertEqual("1", str(preserved["label"]))
            self.assertEqual("reviewed", preserved["tags"])
            self.assertEqual("keep me", preserved["notes"])
            added = output_df[output_df["from_url"] == "test://B"].iloc[0]
            self.assertEqual("", added["label"])

    def test_multiple_revision_types_add_row_once(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(
                experiment_dir,
                "historyFinder",
                "nc",
                "demo",
                [
                    self.row(
                        "demo",
                        "testA",
                        "prodA",
                        "test://A",
                        "prod://A",
                        20,
                        0,
                        from_ch_all=30,
                        to_ch_all=0,
                    )
                ],
            )

            main([
                "--workspace-directory",
                tmpdir,
                "--experiment-name",
                "demo-exp",
                "--tools",
                "historyFinder",
                "--strategies",
                "nc",
                "--projects",
                "demo",
                "--revision-types",
                "ch_diff,ch_all",
                "--min-t2p-links",
                "0",
            ])

            output_df = self.read_review_csv(experiment_dir, "historyFinder", "nc", "demo")

            self.assertEqual(1, len(output_df))
            self.assertEqual(["test://A"], output_df["from_url"].tolist())

    def test_missing_revision_columns_warn_and_do_not_create_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            output_file = experiment_dir / "t2p-change" / "historyFinder" / "nc" / "demo.csv"
            output_file.parent.mkdir(parents=True)
            pd.DataFrame([{"project": "demo", "from_url": "test://A", "to_url": "prod://A"}]).to_csv(
                output_file,
                index=False,
            )

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                main([
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo-exp",
                    "--tools",
                    "historyFinder",
                    "--strategies",
                    "nc",
                    "--projects",
                    "demo",
                    "--revision-types",
                    "ch_diff",
                    "--min-t2p-links",
                    "0",
                ])

            self.assertFalse(self.review_csv(experiment_dir, "historyFinder", "nc", "demo").exists())
            self.assertTrue(any("missing required columns" in str(warning.message) for warning in caught_warnings))

    def create_experiment(self, workspace_dir: str) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo-exp"
        (experiment_dir / "t2p-change").mkdir(parents=True)
        return experiment_dir

    def write_t2p_change_rows(
        self,
        experiment_dir: Path,
        tool: str,
        strategy: str,
        project: str,
        rows: list[dict],
    ) -> None:
        output_file = experiment_dir / "t2p-change" / tool / strategy / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output_file, index=False)

    def row(
        self,
        project: str,
        from_name: str,
        to_name: str,
        from_url: str,
        to_url: str,
        from_ch_diff: int,
        to_ch_diff: int,
        *,
        from_ch_all: int = 0,
        to_ch_all: int = 0,
    ) -> dict:
        return {
            "project": project,
            "from_name": from_name,
            "to_name": to_name,
            "from_url": from_url,
            "to_url": to_url,
            "from_ch_diff": from_ch_diff,
            "to_ch_diff": to_ch_diff,
            "from_ch_all": from_ch_all,
            "to_ch_all": to_ch_all,
        }

    def review_csv(self, experiment_dir: Path, tool: str, strategy: str, project: str) -> Path:
        return experiment_dir / "t2p-revision-review" / tool / strategy / f"{project}.csv"

    def read_review_csv(self, experiment_dir: Path, tool: str, strategy: str, project: str) -> pd.DataFrame:
        return pd.read_csv(
            self.review_csv(experiment_dir, tool, strategy, project),
            keep_default_na=False,
            na_filter=False,
        )


if __name__ == "__main__":
    unittest.main()
