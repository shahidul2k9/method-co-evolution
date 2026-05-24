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

from ptc.constants import ALL_REPOSITORY
from ptc.generator.t2p_correlation import DEFAULT_MIN_T2P_LINKS, build_parser, main


@unittest.skipIf(pd is None, "pandas is required for generate_t2p_mwu tests")
class TestGenerateT2PMwu(unittest.TestCase):
    def test_default_min_t2p_links_is_30(self):
        with mock.patch.dict("os.environ", {"ME_MIN_T2P_LINKS": "30"}):
            parser = build_parser()

        args = parser.parse_args([])

        self.assertEqual(30, DEFAULT_MIN_T2P_LINKS)
        self.assertEqual(DEFAULT_MIN_T2P_LINKS, args.min_t2p_links)

    def test_project_below_threshold_is_skipped_with_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "tarantula", "small", 29)

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                with mock.patch.dict("os.environ", {"ME_REVISION_TYPES": "ch_all"}):
                    main([
                        "--workspace-directory",
                        tmpdir,
                        "--experiment-name",
                        "demo",
                        "--strategies",
                        "tarantula",
                    ])

            output_df = pd.read_csv(experiment_dir / "aggregate" / "t2p-mwu.csv")

            self.assertTrue(output_df.empty)
            warning_messages = [str(warning.message) for warning in caught_warnings]
            self.assertTrue(
                any(
                    "project=small" in message
                    and "tool=historyFinder" in message
                    and "strategy=tarantula" in message
                    and "t2p_links=29 is below min_t2p_links=30" in message
                    for message in warning_messages
                )
            )

    def test_project_at_threshold_emits_stat_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(
                experiment_dir,
                "historyFinder",
                "tarantula",
                "threshold",
                DEFAULT_MIN_T2P_LINKS,
            )

            with mock.patch.dict("os.environ", {"ME_REVISION_TYPES": "ch_all"}):
                main([
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--strategies",
                    "tarantula",
                ])

            output_df = pd.read_csv(experiment_dir / "aggregate" / "t2p-mwu.csv")
            project_df = output_df[output_df["project"] == "threshold"]

            self.assertEqual(1, len(project_df))
            self.assertEqual(DEFAULT_MIN_T2P_LINKS, project_df.iloc[0]["size"])
            self.assertEqual("all", project_df.iloc[0]["change"])

    def test_cli_min_t2p_links_allows_smaller_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "tarantula", "small", 29)

            with mock.patch.dict("os.environ", {"ME_REVISION_TYPES": "ch_all"}):
                main([
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--strategies",
                    "tarantula",
                    "--min-t2p-links",
                    "29",
                ])

            output_df = pd.read_csv(experiment_dir / "aggregate" / "t2p-mwu.csv")

            self.assertIn("small", set(output_df["project"]))
            self.assertEqual([29], output_df.loc[output_df["project"] == "small", "size"].tolist())

    def test_env_min_t2p_links_is_used_when_cli_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "tarantula", "small", 29)

            with mock.patch.dict("os.environ", {"ME_MIN_T2P_LINKS": "29", "ME_REVISION_TYPES": "ch_all"}):
                main([
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--strategies",
                    "tarantula",
                ])

            output_df = pd.read_csv(experiment_dir / "aggregate" / "t2p-mwu.csv")

            self.assertIn("small", set(output_df["project"]))

    def test_cli_min_t2p_links_overrides_env(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "tarantula", "small", 29)

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                with mock.patch.dict("os.environ", {"ME_MIN_T2P_LINKS": "29", "ME_REVISION_TYPES": "ch_all"}):
                    main([
                        "--workspace-directory",
                        tmpdir,
                        "--experiment-name",
                        "demo",
                        "--strategies",
                        "tarantula",
                        "--min-t2p-links",
                        "30",
                    ])

            output_df = pd.read_csv(experiment_dir / "aggregate" / "t2p-mwu.csv")

            self.assertTrue(output_df.empty)
            self.assertTrue(
                any("t2p_links=29 is below min_t2p_links=30" in str(warning.message) for warning in caught_warnings)
            )

    def test_mixed_projects_skip_small_and_keep_qualifying_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change_rows(experiment_dir, "historyFinder", "tarantula", "small", 29)
            self.write_t2p_change_rows(
                experiment_dir,
                "historyFinder",
                "tarantula",
                "large",
                DEFAULT_MIN_T2P_LINKS,
            )

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                with mock.patch.dict("os.environ", {"ME_REVISION_TYPES": "ch_all"}):
                    main([
                        "--workspace-directory",
                        tmpdir,
                        "--experiment-name",
                        "demo",
                        "--strategies",
                        "tarantula",
                    ])

            output_df = pd.read_csv(experiment_dir / "aggregate" / "t2p-mwu.csv")

            self.assertNotIn("small", set(output_df["project"]))
            self.assertIn("large", set(output_df["project"]))
            self.assertIn(ALL_REPOSITORY, set(output_df["project"]))
            self.assertEqual(
                [DEFAULT_MIN_T2P_LINKS],
                output_df.loc[output_df["project"] == "large", "size"].tolist(),
            )
            self.assertTrue(
                any("project=small" in str(warning.message) for warning in caught_warnings)
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
        size: int,
    ) -> None:
        output_file = experiment_dir / "t2p-change" / tool / strategy / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        rows = [
            {
                "project": project,
                "from_artifact": "#test-code #test-case-method",
                "to_artifact": "#main-code",
                "from_ch_all": index % 2,
                "to_ch_all": (index + 1) % 2,
            }
            for index in range(size)
        ]
        pd.DataFrame(rows).to_csv(output_file, index=False)


if __name__ == "__main__":
    unittest.main()
