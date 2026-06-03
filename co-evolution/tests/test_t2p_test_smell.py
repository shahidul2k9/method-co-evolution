from pathlib import Path
import sys
import tempfile
import unittest
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

from mhc.command_util import load_test_smell_acronyms, load_test_smell_names, resolve_smell_detector
from ptc.generator.t2p_test_smell import (
    REVISION_GROUP_1,
    REVISION_GROUP_2,
    REVISION_GROUP_3,
    assign_revision_group,
    build_project_frame,
    main as generator_main,
    output_directory,
)
from ptc.plot.t2p_test_smell import (
    ALL_GROUPS,
    plot_boxplot_axis,
    plot_composition_axis,
    boxplot_values,
    load_generated_frames,
    main as plot_main,
    selected_revision_groups,
    smell_composition,
)


@unittest.skipIf(pd is None, "pandas is required for test smell tests")
class TestT2PTestSmell(unittest.TestCase):
    def test_smell_config_loads_acronym_and_full_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test-smell.yml"
            config_file.write_text(
                "\n".join(
                    [
                        "smell_detectors:",
                        "  jnose:",
                        "    smells:",
                        "      Assertion Roulette: AR",
                    ]
                ),
                encoding="utf-8",
            )

            self.assertEqual({"Assertion Roulette": "AR"}, load_test_smell_acronyms("jnose", config_file))
            self.assertEqual({"AR": "Assertion Roulette"}, load_test_smell_names("jnose", config_file))

    def test_smell_detector_defaults_to_jnose(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertEqual("jnose", resolve_smell_detector())

    def test_assign_revision_group_uses_min_t2p_revision(self):
        self.assertEqual(REVISION_GROUP_1, assign_revision_group(2, 3, min_t2p_revision=5))
        self.assertEqual(REVISION_GROUP_3, assign_revision_group(15, 10, min_t2p_revision=5))
        self.assertEqual(REVISION_GROUP_2, assign_revision_group(14, 10, min_t2p_revision=5))

    def test_build_project_frame_schema_smells_and_multiple_links(self):
        project_df = pd.DataFrame(
            [
                self.row("demo", "test://A", "prod://A1", 2, 3, 20, 1),
                self.row("demo", "test://A", "prod://A2", 15, 10, 20, 1),
                self.row("demo", "test://B", "prod://B", 14, 10, 1, 4),
            ]
        )
        smell_df = pd.DataFrame(
            [
                {"url": "test://A", "smell": "ET"},
                {"url": "test://A", "smell": "AR"},
                {"url": "test://A", "smell": "AR"},
                {"url": "test://B", "smell": "VT"},
            ]
        )

        output_df = build_project_frame(
            project_df,
            smell_df,
            ["ch_diff", "ch_all"],
            project="demo",
            min_t2p_revision=5,
        )

        self.assertEqual(
            [
                "project",
                "from_url",
                "to_url",
                "from_ch_diff",
                "to_ch_diff",
                "from_ch_all",
                "to_ch_all",
                "smells",
                "revision_group_ch_diff",
                "revision_group_ch_all",
            ],
            output_df.columns.tolist(),
        )
        self.assertEqual(["prod://A1", "prod://A2"], output_df[output_df["from_url"] == "test://A"]["to_url"].tolist())
        self.assertEqual(["AR ET", "AR ET"], output_df[output_df["from_url"] == "test://A"]["smells"].tolist())
        self.assertEqual([REVISION_GROUP_1, REVISION_GROUP_3, REVISION_GROUP_2], output_df["revision_group_ch_diff"].tolist())

    def test_generator_rejects_min_t2p_links(self):
        with self.assertRaises(SystemExit):
            generator_main(["--min-t2p-links", "2"])

    def test_generator_writes_one_row_project_and_skips_missing_smell_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change(
                experiment_dir,
                "demo",
                [
                    self.row("demo", "test://A", "prod://A", 2, 3, 20, 1),
                ],
            )
            self.write_t2p_change(
                experiment_dir,
                "missing-smell",
                [self.row("missing-smell", "test://missing", "prod://missing", 30, 1, 30, 1)],
            )
            self.write_smells(experiment_dir, "demo", [{"url": "test://A", "smell": "AR"}])

            with self.assertWarnsRegex(UserWarning, "Test smell CSV not found"):
                generator_main(
                    [
                        "--workspace-directory",
                        tmpdir,
                        "--experiment-name",
                        "demo-exp",
                        "--tools",
                        "historyFinder",
                        "--strategies",
                        "nc",
                        "--revision-types",
                        "ch_diff,ch_all",
                        "--min-t2p-revision",
                        "5",
                        "--smell-detector",
                        "jnose",
                    ]
                )

            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            self.assertTrue((output_dir / "demo.csv").exists())
            self.assertFalse((output_dir / "missing-smell.csv").exists())
            output_df = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual([REVISION_GROUP_1], output_df["revision_group_ch_diff"].tolist())

    def test_selected_revision_groups_validates_input(self):
        self.assertEqual([REVISION_GROUP_2, REVISION_GROUP_3], selected_revision_groups("RT,RRT"))
        with self.assertRaises(ValueError):
            selected_revision_groups("RT,unknown")

    def test_smell_composition_uses_revision_group_denominator(self):
        frame = pd.DataFrame(
            [
                {"smells": "AR ET", "revision_group_ch_diff": REVISION_GROUP_2},
                {"smells": "AR", "revision_group_ch_diff": REVISION_GROUP_2},
                {"smells": "", "revision_group_ch_diff": REVISION_GROUP_2},
                {"smells": "VT", "revision_group_ch_diff": REVISION_GROUP_3},
            ]
        )

        composition = smell_composition(
            frame,
            "ch_diff",
            [REVISION_GROUP_2, REVISION_GROUP_3],
            {"AR": "Assertion Roulette", "ET": "Eager Test", "VT": "Verbose Test"},
        )

        rt_all = composition[
            (composition["group"] == REVISION_GROUP_2)
            & (composition["smell_name"] == "All smells")
        ].iloc[0]
        rt_ar = composition[
            (composition["group"] == REVISION_GROUP_2)
            & (composition["smell_name"] == "Assertion Roulette")
        ].iloc[0]
        self.assertAlmostEqual(66.666, rt_all["percent"], places=2)
        self.assertAlmostEqual(66.666, rt_ar["percent"], places=2)

    def test_load_generated_frames_applies_min_t2p_links(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {"project": "large", "from_url": "test://A", "to_url": "prod://A", "smells": "AR"},
                    {"project": "large", "from_url": "test://B", "to_url": "prod://B", "smells": "VT"},
                ]
            ).to_csv(output_dir / "large.csv", index=False)
            pd.DataFrame(
                [{"project": "small", "from_url": "test://small", "to_url": "prod://small", "smells": "ET"}]
            ).to_csv(output_dir / "small.csv", index=False)

            with self.assertWarnsRegex(UserWarning, "below min_t2p_links=2"):
                frame = load_generated_frames(
                    experiment_dir,
                    "historyFinder",
                    "nc",
                    "jnose",
                    None,
                    min_t2p_links=2,
                )

            self.assertEqual(["large"], sorted(frame["project"].unique()))

    def test_plot_composition_axis_prints_nonzero_percent_labels(self):
        composition = pd.DataFrame(
            [
                {"group": REVISION_GROUP_2, "smell_name": "All smells", "percent": 50.0},
                {"group": REVISION_GROUP_2, "smell_name": "Assertion Roulette", "percent": 0.0},
            ]
        )
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        try:
            plot_composition_axis(ax, composition, [REVISION_GROUP_2])
            labels = [text.get_text() for text in ax.texts]
        finally:
            plt.close(fig)

        self.assertIn("50.0%", labels)
        self.assertNotIn("0.0%", labels)

    def test_plot_boxplot_axis_uses_smell_labels_once_and_group_legend(self):
        frame = pd.DataFrame(
            [
                {"smells": "AR", "from_ch_diff": 10, "revision_group_ch_diff": REVISION_GROUP_3},
                {"smells": "AR", "from_ch_diff": 5, "revision_group_ch_diff": REVISION_GROUP_2},
                {"smells": "VT", "from_ch_diff": 4, "revision_group_ch_diff": REVISION_GROUP_2},
            ]
        )
        rows = boxplot_values(
            frame,
            "ch_diff",
            [REVISION_GROUP_2, REVISION_GROUP_3],
            {"AR": "Assertion Roulette", "VT": "Verbose Test"},
        )
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        try:
            plot_boxplot_axis(ax, rows, [REVISION_GROUP_2, REVISION_GROUP_3])
            x_labels = [label.get_text() for label in ax.get_xticklabels()]
            legend_labels = [text.get_text() for text in ax.get_legend().get_texts()]
        finally:
            plt.close(fig)

        self.assertEqual(["Assertion Roulette", "Verbose Test"], x_labels)
        self.assertIn(ALL_GROUPS, legend_labels)
        self.assertIn("Revision-Prone Test (RT)", legend_labels)
        self.assertIn("Recurrent Revision-Prone Test (RRT)", legend_labels)

    def test_plot_reads_generated_csv_and_filters_revision_groups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_url": "test://A",
                        "to_url": "prod://A",
                        "from_ch_diff": 10,
                        "to_ch_diff": 1,
                        "smells": "AR",
                        "revision_group_ch_diff": REVISION_GROUP_3,
                    },
                    {
                        "project": "demo",
                        "from_url": "test://B",
                        "to_url": "prod://B",
                        "from_ch_diff": 5,
                        "to_ch_diff": 1,
                        "smells": "VT",
                        "revision_group_ch_diff": REVISION_GROUP_2,
                    },
                    {
                        "project": "demo",
                        "from_url": "test://C",
                        "to_url": "prod://C",
                        "from_ch_diff": 1,
                        "to_ch_diff": 5,
                        "smells": "ET",
                        "revision_group_ch_diff": REVISION_GROUP_1,
                    },
                ]
            ).to_csv(output_dir / "demo.csv", index=False)

            plot_main(
                [
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
                    "--revision-groups",
                    "RT,RRT",
                    "--min-t2p-links",
                    "0",
                    "--smell-detector",
                    "jnose",
                ]
            )

            self.assertTrue(
                (
                    experiment_dir
                    / "figure"
                    / "t2p-test-smell--historyFinder--nc--jnose--ch_diff.pdf"
                ).exists()
            )

    def create_experiment(self, workspace_dir: str) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo-exp"
        (experiment_dir / "t2p-change" / "historyFinder" / "nc").mkdir(parents=True)
        return experiment_dir

    def write_t2p_change(self, experiment_dir: Path, project: str, rows: list[dict]) -> None:
        output_file = experiment_dir / "t2p-change" / "historyFinder" / "nc" / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output_file, index=False)

    def write_smells(self, experiment_dir: Path, project: str, rows: list[dict]) -> None:
        output_file = experiment_dir / "test-smell" / "jnose" / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output_file, index=False)

    def row(
        self,
        project: str,
        from_url: str,
        to_url: str,
        from_ch_diff: int,
        to_ch_diff: int,
        from_ch_all: int,
        to_ch_all: int,
    ) -> dict:
        return {
            "project": project,
            "from_url": from_url,
            "to_url": to_url,
            "from_ch_diff": from_ch_diff,
            "to_ch_diff": to_ch_diff,
            "from_ch_all": from_ch_all,
            "to_ch_all": to_ch_all,
        }


if __name__ == "__main__":
    unittest.main()
