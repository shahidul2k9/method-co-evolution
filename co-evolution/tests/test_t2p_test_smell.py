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
from ptc.generator.t2p_test_smell_prevalence_wilcoxon_srt import (
    build_stat_row,
    main as wilcoxon_main,
    paired_smell_values,
    selected_two_revision_groups,
)
from ptc.generator.t2p_test_smell_prevalence import (
    ALL_SMELLS,
    main as prevalence_main,
    prevalence_rows,
)
from ptc.generator.t2p_test_smell_revision import (
    REVISION_GROUP_1,
    REVISION_GROUP_2,
    REVISION_GROUP_3,
    assign_revision_group,
    build_project_frame,
    main as revision_generator_main,
    output_directory,
)
from ptc.plot.t2p_test_smell_barchart import (
    display_smell,
    main as barchart_main,
    plot_prevalence_axis,
)
from ptc.plot.t2p_test_smell_boxplot import (
    ALL_GROUPS,
    boxplot_values,
    load_generated_frames,
    main as boxplot_main,
    plot_boxplot_axis,
    selected_revision_groups,
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
                "rg_ch_diff",
                "rg_ch_all",
            ],
            output_df.columns.tolist(),
        )
        self.assertEqual(["prod://A1", "prod://A2"], output_df[output_df["from_url"] == "test://A"]["to_url"].tolist())
        self.assertEqual(["AR ET", "AR ET"], output_df[output_df["from_url"] == "test://A"]["smells"].tolist())
        self.assertEqual([REVISION_GROUP_1, REVISION_GROUP_3, REVISION_GROUP_2], output_df["rg_ch_diff"].tolist())

    def test_revision_generator_rejects_min_t2p_links(self):
        with self.assertRaises(SystemExit):
            revision_generator_main(["--min-t2p-links", "2"])

    def test_revision_generator_writes_one_row_project_and_skips_missing_smell_file(self):
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
                revision_generator_main(
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
            self.assertEqual([REVISION_GROUP_1], output_df["rg_ch_diff"].tolist())

    def test_revision_generator_unlinks_stale_output_when_smell_file_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change(
                experiment_dir,
                "demo",
                [self.row("demo", "test://A", "prod://A", 2, 3, 20, 1)],
            )
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            stale_output = output_dir / "demo.csv"
            stale_output.write_text("project,from_url\ndemo,stale://test\n", encoding="utf-8")

            with self.assertWarnsRegex(UserWarning, "deleted stale output"):
                revision_generator_main(
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
                        "--smell-detector",
                        "jnose",
                    ]
                )

            self.assertFalse(stale_output.exists())

    def test_revision_generator_unlinks_stale_output_when_revision_columns_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change(
                experiment_dir,
                "demo",
                [{"project": "demo", "from_url": "test://A", "to_url": "prod://A"}],
            )
            self.write_smells(experiment_dir, "demo", [{"url": "test://A", "smell": "AR"}])
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            stale_output = output_dir / "demo.csv"
            stale_output.write_text("project,from_url\ndemo,stale://test\n", encoding="utf-8")

            with self.assertWarnsRegex(UserWarning, "deleted stale output"):
                revision_generator_main(
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
                        "--smell-detector",
                        "jnose",
                    ]
                )

            self.assertFalse(stale_output.exists())

    def test_revision_generator_does_not_unlink_unselected_project_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_t2p_change(
                experiment_dir,
                "selected",
                [self.row("selected", "test://A", "prod://A", 2, 3, 20, 1)],
            )
            self.write_t2p_change(
                experiment_dir,
                "unselected",
                [self.row("unselected", "test://B", "prod://B", 2, 3, 20, 1)],
            )
            self.write_smells(experiment_dir, "selected", [{"url": "test://A", "smell": "AR"}])
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            untouched_output = output_dir / "unselected.csv"
            untouched_output.write_text("project,from_url\nunselected,stale://test\n", encoding="utf-8")

            revision_generator_main(
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
                    "selected",
                    "--revision-types",
                    "ch_diff",
                    "--smell-detector",
                    "jnose",
                ]
            )

            self.assertTrue(untouched_output.exists())

    def test_selected_revision_groups_validates_input(self):
        self.assertEqual([REVISION_GROUP_2, REVISION_GROUP_3], selected_revision_groups("RT,RRT"))
        with self.assertRaises(ValueError):
            selected_revision_groups("RT,unknown")

    def test_prevalence_rows_use_group_denominator_and_include_all(self):
        frame = pd.DataFrame(
            [
                {"from_url": "test://A", "smells": "AR ET", "rg_ch_diff": REVISION_GROUP_2},
                {"from_url": "test://A", "smells": "AR", "rg_ch_diff": REVISION_GROUP_2},
                {"from_url": "test://B", "smells": "", "rg_ch_diff": REVISION_GROUP_2},
                {"from_url": "test://A", "smells": "VT", "rg_ch_diff": REVISION_GROUP_3},
            ]
        )

        rows = prevalence_rows(
            frame,
            strategy="nc",
            tool="historyFinder",
            smell_detector="jnose",
            revision_type="ch_diff",
            revision_groups=[REVISION_GROUP_2, REVISION_GROUP_3],
        )
        prevalence = pd.DataFrame(rows)
        rt_all = prevalence[
            (prevalence["revision_group"] == REVISION_GROUP_2)
            & (prevalence["smell"] == ALL_SMELLS)
        ].iloc[0]
        rt_ar = prevalence[
            (prevalence["revision_group"] == REVISION_GROUP_2)
            & (prevalence["smell"] == "AR")
        ].iloc[0]

        self.assertEqual(3, rt_all["smell_total"])
        self.assertEqual(2, rt_all["methods"])
        self.assertEqual(2, rt_all["smell_n"])
        self.assertEqual(66.67, rt_all["percent"])
        self.assertEqual(3, rt_ar["smell_total"])
        self.assertEqual(2, rt_ar["methods"])
        self.assertEqual(2, rt_ar["smell_n"])
        self.assertEqual(66.67, rt_ar["percent"])
        self.assertEqual(
            [1] * len(prevalence[prevalence["revision_group"] == REVISION_GROUP_3]),
            prevalence[prevalence["revision_group"] == REVISION_GROUP_3]["methods"].tolist(),
        )

    def test_prevalence_rows_warns_and_skips_missing_from_url(self):
        frame = pd.DataFrame([{"smells": "AR", "rg_ch_diff": REVISION_GROUP_2}])

        with self.assertWarnsRegex(UserWarning, "missing generated column from_url"):
            rows = prevalence_rows(
                frame,
                strategy="nc",
                tool="historyFinder",
                smell_detector="jnose",
                revision_type="ch_diff",
            )

        self.assertEqual([], rows)

    def test_prevalence_main_applies_min_t2p_links_and_writes_aggregate_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.generated_row("large", "test://A", "prod://A", 10, 1, "AR", REVISION_GROUP_3),
                    self.generated_row("large", "test://B", "prod://B", 5, 1, "", REVISION_GROUP_2),
                ]
            ).to_csv(output_dir / "large.csv", index=False)
            pd.DataFrame(
                [self.generated_row("small", "test://small", "prod://small", 5, 1, "ET", REVISION_GROUP_2)]
            ).to_csv(output_dir / "small.csv", index=False)

            with self.assertWarnsRegex(UserWarning, "below min_t2p_links=2"):
                prevalence_main(
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
                        "ch_diff",
                        "--min-t2p-links",
                        "2",
                        "--smell-detector",
                        "jnose",
                    ]
                )

            output_df = pd.read_csv(
                experiment_dir / "aggregate" / "t2p-test-smell-prevalence.csv",
                keep_default_na=False,
                na_filter=False,
            )
            self.assertIn(ALL_SMELLS, output_df["smell"].tolist())
            self.assertNotIn("ET", output_df["smell"].tolist())
            self.assertTrue(output_df["percent"].map(lambda value: value == round(value, 2)).all())
            self.assertEqual(
                [
                    "strategy",
                    "tool",
                    "smell_detector",
                    "change",
                    "revision_group",
                    "methods",
                    "smell",
                    "percent",
                    "smell_total",
                    "smell_n",
                ],
                output_df.columns.tolist(),
            )

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

    def test_barchart_maps_smell_names_and_prints_nonzero_percent_labels(self):
        prevalence = pd.DataFrame(
            [
                {"revision_group": REVISION_GROUP_2, "smell": ALL_SMELLS, "percent": 50.0, "smell_n": 1},
                {"revision_group": REVISION_GROUP_2, "smell": "AR", "percent": 0.0, "smell_n": 0},
            ]
        )
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        try:
            plot_prevalence_axis(ax, prevalence, [REVISION_GROUP_2], {"AR": "Assertion Roulette"})
            labels = [text.get_text() for text in ax.texts]
            x_labels = [label.get_text() for label in ax.get_xticklabels()]
        finally:
            plt.close(fig)

        self.assertEqual("All", display_smell(ALL_SMELLS, {"AR": "Assertion Roulette"}))
        self.assertIn("Assertion Roulette", x_labels)
        self.assertIn("50.0%", labels)
        self.assertNotIn("0.0%", labels)

    def test_barchart_main_reads_prevalence_csv_and_writes_figure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            aggregate_dir = experiment_dir / "aggregate"
            aggregate_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_2, ALL_SMELLS, 50, 2, 1),
                    self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_2, "AR", 50, 2, 1),
                ]
            ).to_csv(aggregate_dir / "t2p-test-smell-prevalence.csv", index=False)

            barchart_main(
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
                    "ch_diff",
                    "--revision-groups",
                    "RT",
                    "--smell-detector",
                    "jnose",
                ]
            )

            self.assertTrue(
                (
                    experiment_dir
                    / "figure"
                    / "t2p-test-smell-barchart--historyFinder--nc--jnose--ch_diff.pdf"
                ).exists()
            )

    def test_plot_boxplot_axis_uses_smell_labels_once_and_group_legend(self):
        frame = pd.DataFrame(
            [
                {"smells": "AR", "from_ch_diff": 10, "rg_ch_diff": REVISION_GROUP_3},
                {"smells": "AR", "from_ch_diff": 5, "rg_ch_diff": REVISION_GROUP_2},
                {"smells": "VT", "from_ch_diff": 4, "rg_ch_diff": REVISION_GROUP_2},
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

    def test_boxplot_reads_generated_csv_and_filters_revision_groups(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.generated_row("demo", "test://A", "prod://A", 10, 1, "AR", REVISION_GROUP_3),
                    self.generated_row("demo", "test://B", "prod://B", 5, 1, "VT", REVISION_GROUP_2),
                    self.generated_row("demo", "test://C", "prod://C", 1, 5, "ET", REVISION_GROUP_1),
                ]
            ).to_csv(output_dir / "demo.csv", index=False)

            boxplot_main(
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
                    / "t2p-test-smell-boxplot--historyFinder--nc--jnose--ch_diff.pdf"
                ).exists()
            )

    def test_wilcoxon_requires_two_revision_groups_and_preserves_order(self):
        self.assertEqual([REVISION_GROUP_3, REVISION_GROUP_1], selected_two_revision_groups("RRT,RP"))
        with self.assertRaises(ValueError):
            selected_two_revision_groups("RT")

    def test_wilcoxon_pairs_by_smell_and_drops_missing_smells(self):
        prevalence = pd.DataFrame(
            [
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "AR", 75, 4, 3),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "ET", 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "VT", 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "AR", 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "ET", 0, 4, 0),
            ]
        )

        paired_df = paired_smell_values(prevalence, REVISION_GROUP_3, REVISION_GROUP_1)

        self.assertEqual(["AR", "ET"], paired_df["smell"].tolist())
        self.assertEqual([3, 1], paired_df["g1_smell_n"].tolist())
        self.assertEqual([1, 0], paired_df["g2_smell_n"].tolist())

    def test_wilcoxon_build_stat_row_excludes_all_and_uses_smell_n(self):
        prevalence = pd.DataFrame(
            [
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, ALL_SMELLS, 100, 4, 4),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "AR", 75, 4, 3),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "ET", 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, ALL_SMELLS, 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "AR", 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "ET", 0, 4, 0),
            ]
        )

        stat_row = build_stat_row(
            prevalence,
            group1=REVISION_GROUP_3,
            group2=REVISION_GROUP_1,
            strategy="nc",
            tool="historyFinder",
            smell_detector="jnose",
            change="ch_diff",
        )

        self.assertEqual("RRT,RP", stat_row["groups"])
        self.assertEqual(2, stat_row["size"])
        self.assertEqual(2, stat_row["g1_size"])
        self.assertEqual(2, stat_row["g2_size"])
        self.assertIn("w_stat", stat_row)
        self.assertIn("w_p", stat_row)

    def test_wilcoxon_all_zero_difference_fallback(self):
        prevalence = pd.DataFrame(
            [
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "AR", 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "ET", 0, 4, 0),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "AR", 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "ET", 0, 4, 0),
            ]
        )

        stat_row = build_stat_row(
            prevalence,
            group1=REVISION_GROUP_3,
            group2=REVISION_GROUP_1,
            strategy="nc",
            tool="historyFinder",
            smell_detector="jnose",
            change="ch_diff",
        )

        self.assertEqual(0.0, stat_row["w_stat"])
        self.assertEqual(1.0, stat_row["w_p"])
        self.assertEqual("=", stat_row["d_sign"])

    def test_wilcoxon_main_writes_ordered_groups_and_renamed_columns(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            aggregate_dir = experiment_dir / "aggregate"
            aggregate_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "AR", 75, 4, 3),
                    self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "ET", 25, 4, 1),
                    self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "AR", 25, 4, 1),
                    self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "ET", 0, 4, 0),
                    self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, ALL_SMELLS, 25, 4, 1),
                ]
            ).to_csv(aggregate_dir / "t2p-test-smell-prevalence.csv", index=False)

            wilcoxon_main(
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
                    "ch_diff",
                    "--revision-groups",
                    "RRT,RP",
                    "--smell-detector",
                    "jnose",
                ]
            )

            output_df = pd.read_csv(
                aggregate_dir / "t2p-test-smell-prevalence-wilcoxon-srt.csv",
                keep_default_na=False,
            )
            self.assertEqual(["RRT,RP"], output_df["groups"].tolist())
            self.assertEqual(
                [
                    "groups",
                    "strategy",
                    "tool",
                    "smell_detector",
                    "change",
                    "size",
                    "g1_size",
                    "g2_size",
                    "w_stat",
                    "w_p",
                    "d_value",
                    "d_sign",
                    "effect_size",
                    "N",
                    "S",
                    "M",
                    "L",
                ],
                output_df.columns.tolist(),
            )
            self.assertNotIn("mww_p", output_df.columns)

    def create_experiment(self, workspace_dir: str) -> Path:
        experiment_dir = Path(workspace_dir) / "experiment" / "demo-exp"
        (experiment_dir / "t2p-change" / "historyFinder" / "nc").mkdir(parents=True)
        return experiment_dir

    def write_t2p_change(self, experiment_dir: Path, project: str, rows: list[dict]) -> None:
        output_file = experiment_dir / "t2p-change" / "historyFinder" / "nc" / f"{project}.csv"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output_file, index=False)

    def write_smells(self, experiment_dir: Path, project: str, rows: list[dict]) -> None:
        output_file = experiment_dir / "test-smell" / "jnose" / "nc" / f"{project}.csv"
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

    def generated_row(
        self,
        project: str,
        from_url: str,
        to_url: str,
        from_ch_diff: int,
        to_ch_diff: int,
        smells: str,
        revision_group: str,
    ) -> dict:
        return {
            "project": project,
            "from_url": from_url,
            "to_url": to_url,
            "from_ch_diff": from_ch_diff,
            "to_ch_diff": to_ch_diff,
            "smells": smells,
            "rg_ch_diff": revision_group,
        }

    def prevalence_row(
        self,
        strategy: str,
        tool: str,
        smell_detector: str,
        change: str,
        revision_group: str,
        smell: str,
        percent: float,
        smell_total: int,
        smell_n: int,
    ) -> dict:
        return {
            "strategy": strategy,
            "tool": tool,
            "smell_detector": smell_detector,
            "change": change,
            "revision_group": revision_group,
            "smell": smell,
            "percent": percent,
            "smell_total": smell_total,
            "smell_n": smell_n,
        }


if __name__ == "__main__":
    unittest.main()
