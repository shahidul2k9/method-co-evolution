import contextlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.generator import t2p_evaluation


class TestT2PLinkEvaluation(unittest.TestCase):
    def write_config(self, root: Path) -> Path:
        config_file = root / "config.yml"
        config_file.write_text(
            "\n".join(
                [
                    "experiments:",
                    "  exp-a:",
                    "    - exp-a",
                    "  exp-b:",
                    "    - exp-b",
                    "  missing-exp:",
                    "    - missing-exp",
                    "",
                    "groups:",
                    "  plus:",
                    "    - exp-a",
                    "    - exp-b",
                    "  plus-with-missing:",
                    "    - exp-a",
                    "    - missing-exp",
                    "",
                ]
            )
        )
        return config_file

    def write_links(self, directory: Path, rows: list[dict[str, str]]) -> None:
        directory.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(directory, index=False)

    def create_project(self, root: Path, workspace: Path, experiment: str, project: str, rows: list[dict[str, str]]) -> None:
        gt_file = root / "data" / experiment / "t2p-ground-truth" / f"{project}.csv"
        pred_file = workspace / "experiment" / experiment / "t2p-link" / "strategy-a" / f"{project}.csv"
        self.write_links(gt_file, rows)
        self.write_links(pred_file, rows)

    def test_load_ground_truth_df_filters_zero_label_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            gt_file = Path(temp_dir) / "ground-truth.csv"
            self.write_links(
                gt_file,
                [
                    {"from_url": "test-a", "to_url": "prod-a", "label": "1"},
                    {"from_url": "test-a", "to_url": "prod-b", "label": "0"},
                    {"from_url": "test-a", "to_url": "prod-c", "label": ""},
                ],
            )

            result_df = t2p_link_evaluation.load_ground_truth_df(gt_file)

        self.assertEqual([("test-a", "prod-a")], list(result_df[["from_url", "to_url"]].itertuples(index=False, name=None)))

    def test_load_config_treats_experiments_as_single_member_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = t2p_link_evaluation.load_ground_truth_config(self.write_config(Path(temp_dir)))

        self.assertEqual(["exp-a"], t2p_link_evaluation.resolve_experiment_group(config, "exp-a"))
        self.assertEqual(["exp-a", "exp-b"], t2p_link_evaluation.resolve_experiment_group(config, "plus"))

    def test_unknown_group_raises_helpful_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = t2p_link_evaluation.load_ground_truth_config(self.write_config(Path(temp_dir)))

        with self.assertRaisesRegex(ValueError, "Unknown experiment group 'nope'"):
            t2p_link_evaluation.resolve_experiment_group(config, "nope")

    def test_resolve_selected_groups_accepts_all_and_comma_separated_lists(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            config = t2p_link_evaluation.load_ground_truth_config(self.write_config(Path(temp_dir)))

        all_groups = t2p_link_evaluation.resolve_selected_groups(config, "all")
        self.assertEqual(["exp-a", "exp-b", "missing-exp", "plus", "plus-with-missing"], all_groups.names)
        self.assertEqual("all", all_groups.output_name)

        selected_groups = t2p_link_evaluation.resolve_selected_groups(config, "exp-a, plus,exp-a")
        self.assertEqual(["exp-a", "plus"], selected_groups.names)
        self.assertEqual("multi-group", selected_groups.output_name)

    def test_single_experiment_outputs_member_and_average_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            config_file = self.write_config(root)
            self.create_project(
                root,
                workspace,
                "exp-a",
                "shared",
                [{"from_url": "test-a", "to_url": "prod-a"}],
            )

            with mock.patch.object(t2p_link_evaluation, "PROJECT_DIRECTORY", str(root)):
                t2p_link_evaluation.main(
                    [
                        "--workspace-directory",
                        str(workspace),
                        "--experiment-name",
                        "exp-a",
                        "--ground-truth-config",
                        str(config_file),
                    ]
                )

            result_df = pd.read_csv(workspace / "t2p_link_overall_metric.csv")

        self.assertEqual(t2p_link_evaluation.METRIC_COLUMNS, result_df.columns.tolist())
        self.assertEqual(
            [("avg-exp-a", "exp-a"), ("shared", "exp-a")],
            list(result_df[["project", "experiment"]].itertuples(index=False, name=None)),
        )

    def test_evaluation_uses_only_positive_ground_truth_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            config_file = self.write_config(root)
            gt_file = root / "data" / "exp-a" / "t2p-ground-truth" / "project-a.csv"
            pred_file = workspace / "experiment" / "exp-a" / "t2p-link" / "strategy-a" / "project-a.csv"
            self.write_links(
                gt_file,
                [
                    {"from_url": "test-a", "to_url": "prod-a", "label": "1"},
                    {"from_url": "test-a", "to_url": "prod-b", "label": "0"},
                ],
            )
            self.write_links(
                pred_file,
                [
                    {"from_url": "test-a", "to_url": "prod-a"},
                    {"from_url": "test-a", "to_url": "prod-b"},
                ],
            )

            with mock.patch.object(t2p_link_evaluation, "PROJECT_DIRECTORY", str(root)):
                t2p_link_evaluation.main(
                    [
                        "--workspace-directory",
                        str(workspace),
                        "--experiment-name",
                        "exp-a",
                        "--ground-truth-config",
                        str(config_file),
                    ]
                )

            result_df = pd.read_csv(workspace / "t2p_link_overall_metric.csv")

        project_row = result_df[result_df["project"] == "project-a"].iloc[0]
        self.assertEqual(1, project_row["gt_links"])
        self.assertEqual(2, project_row["pred_links"])
        self.assertEqual(1, project_row["tp"])
        self.assertEqual(1, project_row["fp"])

    def test_group_keeps_overlapping_projects_distinct_and_writes_average(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            config_file = self.write_config(root)
            self.create_project(
                root,
                workspace,
                "exp-a",
                "shared",
                [{"from_url": "test-a", "to_url": "prod-a"}],
            )
            self.create_project(
                root,
                workspace,
                "exp-b",
                "shared",
                [{"from_url": "test-b", "to_url": "prod-b"}],
            )

            with mock.patch.object(t2p_link_evaluation, "PROJECT_DIRECTORY", str(root)):
                t2p_link_evaluation.main(
                    [
                        "--workspace-directory",
                        str(workspace),
                        "--experiment-name",
                        "exp-a",
                        "--experiment-group",
                        "plus",
                        "--ground-truth-config",
                        str(config_file),
                    ]
                )

            result_df = pd.read_csv(workspace / "t2p_link_overall_metric.csv")

        self.assertEqual(t2p_link_evaluation.METRIC_COLUMNS, result_df.columns.tolist())
        self.assertEqual(
            [("shared", "exp-a"), ("shared", "exp-b"), ("avg-plus", "plus")],
            list(result_df[["project", "experiment"]].itertuples(index=False, name=None)),
        )
        avg_row = result_df[result_df["project"] == "avg-plus"].iloc[0]
        self.assertEqual(2, avg_row["gt_links"])
        self.assertEqual(2, avg_row["pred_links"])

    def test_comma_separated_groups_emit_shared_member_rows_once(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            config_file = self.write_config(root)
            self.create_project(
                root,
                workspace,
                "exp-a",
                "shared",
                [{"from_url": "test-a", "to_url": "prod-a"}],
            )
            self.create_project(
                root,
                workspace,
                "exp-b",
                "shared",
                [{"from_url": "test-b", "to_url": "prod-b"}],
            )

            with mock.patch.object(t2p_link_evaluation, "PROJECT_DIRECTORY", str(root)):
                t2p_link_evaluation.main(
                    [
                        "--workspace-directory",
                        str(workspace),
                        "--experiment-name",
                        "exp-a",
                        "--experiment-group",
                        "exp-a,plus",
                        "--ground-truth-config",
                        str(config_file),
                    ]
                )

            result_df = pd.read_csv(workspace / "t2p_link_overall_metric.csv")
            metric_dir_exists = (workspace / "experiment" / "multi-group" / "t2p-link-metric").is_dir()

        self.assertEqual(
            [("avg-exp-a", "exp-a"), ("shared", "exp-a"), ("shared", "exp-b"), ("avg-plus", "plus")],
            list(result_df[["project", "experiment"]].itertuples(index=False, name=None)),
        )
        self.assertTrue(metric_dir_exists)

    def test_all_groups_outputs_every_configured_average(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            config_file = self.write_config(root)
            self.create_project(
                root,
                workspace,
                "exp-a",
                "shared",
                [{"from_url": "test-a", "to_url": "prod-a"}],
            )
            self.create_project(
                root,
                workspace,
                "exp-b",
                "shared",
                [{"from_url": "test-b", "to_url": "prod-b"}],
            )

            stdout = io.StringIO()
            with mock.patch.object(t2p_link_evaluation, "PROJECT_DIRECTORY", str(root)):
                with contextlib.redirect_stdout(stdout):
                    t2p_link_evaluation.main(
                        [
                            "--workspace-directory",
                            str(workspace),
                            "--experiment-name",
                            "exp-a",
                            "--experiment-group",
                            "all",
                            "--ground-truth-config",
                            str(config_file),
                        ]
                    )

            result_df = pd.read_csv(workspace / "t2p_link_overall_metric.csv")
            metric_dir_exists = (workspace / "experiment" / "all" / "t2p-link-metric").is_dir()

        self.assertEqual(
            [
                ("avg-exp-a", "exp-a"),
                ("shared", "exp-a"),
                ("avg-exp-b", "exp-b"),
                ("shared", "exp-b"),
                ("avg-plus", "plus"),
                ("avg-plus-with-missing", "plus-with-missing"),
            ],
            list(result_df[["project", "experiment"]].itertuples(index=False, name=None)),
        )
        self.assertIn("missing ground-truth directory for experiment missing-exp", stdout.getvalue())
        self.assertIn("experiment group missing-exp produced no rows", stdout.getvalue())
        self.assertTrue(metric_dir_exists)

    def test_missing_member_directories_are_skipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            config_file = self.write_config(root)
            self.create_project(
                root,
                workspace,
                "exp-a",
                "project-a",
                [{"from_url": "test-a", "to_url": "prod-a"}],
            )

            stdout = io.StringIO()
            with mock.patch.object(t2p_link_evaluation, "PROJECT_DIRECTORY", str(root)):
                with contextlib.redirect_stdout(stdout):
                    t2p_link_evaluation.main(
                        [
                            "--workspace-directory",
                            str(workspace),
                            "--experiment-name",
                            "exp-a",
                            "--experiment-group",
                            "plus-with-missing",
                            "--ground-truth-config",
                            str(config_file),
                        ]
                    )

            result_df = pd.read_csv(workspace / "t2p_link_overall_metric.csv")

        self.assertEqual(["exp-a", "plus-with-missing"], result_df["experiment"].tolist())
        self.assertEqual(["project-a", "avg-plus-with-missing"], result_df["project"].tolist())
        self.assertIn("missing ground-truth directory for experiment missing-exp", stdout.getvalue())

    def test_missing_project_and_ground_truth_csv_print_warnings(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            workspace = root / "workspace"
            config_file = self.write_config(root)
            pred_file = workspace / "experiment" / "exp-a" / "t2p-link" / "strategy-a" / "project-a.csv"
            self.write_links(pred_file, [{"from_url": "test-a", "to_url": "prod-a"}])
            (root / "data" / "exp-a" / "t2p-ground-truth").mkdir(parents=True)

            stdout = io.StringIO()
            with mock.patch.object(t2p_link_evaluation, "PROJECT_DIRECTORY", str(root)):
                with contextlib.redirect_stdout(stdout):
                    t2p_link_evaluation.main(
                        [
                            "--workspace-directory",
                            str(workspace),
                            "--experiment-name",
                            "exp-a",
                            "--ground-truth-config",
                            str(config_file),
                            "--filters",
                            "--projects",
                            "project-a,missing-project",
                        ]
                    )

        output = stdout.getvalue()
        self.assertIn("selected project 'missing-project' has no prediction CSV", output)
        self.assertIn("missing ground-truth CSV for experiment exp-a", output)
        self.assertIn("No results: experiment groups=exp-a", output)


if __name__ == "__main__":
    unittest.main()
