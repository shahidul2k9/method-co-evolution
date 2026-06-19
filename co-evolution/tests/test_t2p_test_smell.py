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
from ptc.generator.t2p_test_smell_loc_group import (
    loc_group,
    loc_group_rows,
    main as loc_group_main,
    unique_method_locs,
)
from ptc.generator.t2p_test_smell_prevalence import (
    ALL_LOC_GROUP,
    ALL_SMELLS,
    loc_group_frame,
    main as prevalence_main,
    prevalence_rows,
    unique_method_frame,
)
from ptc.generator.t2p_test_smell_association import (
    association_rows,
    benjamini_hochberg,
    main as association_main,
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
    effect_order,
    main as barchart_main,
    plot_effect_axis,
    plot_prevalence_axis,
)
from ptc.plot.t2p_test_smell_association_table import (
    main as association_table_main,
    render_latex_table,
)
from ptc.plot.t2p_test_smell_prevalence_wilcoxon_srt_table import (
    main as wilcoxon_table_main,
    render_latex_table as render_wilcoxon_table,
)
from ptc.plot.t2p_test_smell_boxplot import (
    ALL_GROUPS,
    boxplot_values,
    load_generated_frames,
    main as boxplot_main,
    plot_boxplot_axis,
    plot_revision_type,
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
            (prevalence["rg_group"] == REVISION_GROUP_2)
            & (prevalence["loc_group"] == ALL_LOC_GROUP)
            & (prevalence["smell"] == ALL_SMELLS)
        ].iloc[0]

        self.assertEqual(1, rt_all["smell_total"])
        self.assertEqual(1, rt_all["methods"])
        self.assertEqual(0, rt_all["smell_n"])
        self.assertEqual(0, rt_all["percent"])
        self.assertNotIn("AR", prevalence["smell"].tolist())
        self.assertEqual(
            [0] * len(prevalence[prevalence["rg_group"] == REVISION_GROUP_3]),
            prevalence[prevalence["rg_group"] == REVISION_GROUP_3]["methods"].tolist(),
        )

    def test_unique_method_frame_deduplicates_and_excludes_conflicting_groups(self):
        frame = pd.DataFrame(
            [
                {"project": "one", "from_url": "test://A", "smells": "AR", "rg_ch_diff": REVISION_GROUP_1},
                {"project": "one", "from_url": "test://A", "smells": "AR ET", "rg_ch_diff": REVISION_GROUP_1},
                {"project": "one", "from_url": "test://B", "smells": "VT", "rg_ch_diff": REVISION_GROUP_1},
                {"project": "one", "from_url": "test://B", "smells": "VT", "rg_ch_diff": REVISION_GROUP_3},
                {"project": "two", "from_url": "test://C", "smells": "", "rg_ch_diff": REVISION_GROUP_3},
            ]
        )

        unique = unique_method_frame(frame, "ch_diff", [REVISION_GROUP_1, REVISION_GROUP_3])

        self.assertEqual(["test://A", "test://C"], unique["from_url"].tolist())
        self.assertEqual(["AR ET", ""], unique["smells"].tolist())

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
            self.write_smells(
                experiment_dir,
                "large",
                [
                    {"url": "test://A", "smell": "AR", "loc": 10},
                    {"url": "test://B", "smell": "VT", "loc": 20},
                ],
            )

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
                    "rg_group",
                    "loc_group",
                    "methods",
                    "smell",
                    "percent",
                    "smell_total",
                    "smell_n",
                ],
                output_df.columns.tolist(),
            )
            self.assertIn(REVISION_GROUP_3, output_df["rg_group"].tolist())
            self.assertNotIn("loc", output_df["change"].tolist())
            self.assertIn(ALL_LOC_GROUP, output_df["loc_group"].tolist())
            self.assertIn("S", output_df["loc_group"].tolist())

    def test_loc_group_frame_assigns_groups_and_deduplicates_methods(self):
        smell_df = pd.DataFrame(
            [
                {"url": f"test://{index}", "smell": "AR", "loc": index}
                for index in range(1, 11)
            ]
            + [
                {"url": "test://1", "smell": "VT", "loc": 99},
                {"url": "test://bad", "smell": "ET", "loc": "bad"},
            ]
        )

        output = loc_group_frame([smell_df])

        self.assertEqual(10, len(output))
        self.assertEqual(["S", "M", "L", "XL"], sorted(output["loc_group"].unique(), key=["S", "M", "L", "XL"].index))
        self.assertEqual(["S"], output[output["from_url"] == "test://1"]["loc_group"].tolist())

    def test_loc_group_uses_unique_first_valid_method_loc(self):
        frame = pd.DataFrame(
            [
                {"url": "test://A", "loc": "bad"},
                {"url": "test://A", "loc": "10"},
                {"url": "test://A", "loc": "99"},
                {"url": "test://B", "loc": "0"},
                {"url": "test://C", "loc": "3"},
                {"url": "", "loc": "4"},
            ]
        )

        method_locs = unique_method_locs([frame])

        self.assertEqual(["test://A", "test://C"], method_locs["url"].tolist())
        self.assertEqual([10, 3], method_locs["loc"].tolist())

    def test_loc_group_rows_use_percentile_boundaries(self):
        method_locs = pd.DataFrame(
            [{"url": f"test://{index}", "loc": index} for index in range(1, 11)]
        )

        rows = loc_group_rows(method_locs, strategy="nc", smell_detector="jnose")
        output = pd.DataFrame(rows).set_index("loc_group")

        groups = ["S", "M", "L", "XL"]
        self.assertEqual("S", loc_group(7, (7, 8, 9)))
        self.assertEqual("M", loc_group(8, (7, 8, 9)))
        self.assertEqual("L", loc_group(9, (7, 8, 9)))
        self.assertEqual("XL", loc_group(10, (7, 8, 9)))
        self.assertEqual(["1", "8", "9", "10"], output.loc[groups, "loc_min"].tolist())
        self.assertEqual(["7", "8", "9", "10"], output.loc[groups, "loc_max"].tolist())
        self.assertEqual([7, 1, 1, 1], output.loc[groups, "methods"].tolist())
        self.assertEqual([70.0, 10.0, 10.0, 10.0], output.loc[groups, "percent"].tolist())

    def test_loc_group_main_writes_aggregate_and_applies_project_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            self.write_smells(
                experiment_dir,
                "demo",
                [
                    {"url": f"test://{index}", "smell": "AR", "loc": index}
                    for index in range(1, 11)
                ]
                + [
                    {"url": "test://1", "smell": "ET", "loc": 99},
                    {"url": "test://bad", "smell": "ET", "loc": "bad"},
                ],
            )
            self.write_smells(experiment_dir, "other", [{"url": "test://other", "smell": "AR", "loc": 100}])

            loc_group_main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo-exp",
                    "--strategies",
                    "nc",
                    "--projects",
                    "demo",
                    "--smell-detector",
                    "jnose",
                    "--replace",
                ]
            )

            output_df = pd.read_csv(
                experiment_dir / "aggregate" / "t2p-test-smell-loc-size.csv",
                keep_default_na=False,
                na_filter=False,
            )
            self.assertEqual(
                ["strategy", "smell_detector", "loc_group", "loc_min", "loc_max", "methods", "percent"],
                output_df.columns.tolist(),
            )
            self.assertEqual(["S", "M", "L", "XL"], output_df["loc_group"].tolist())
            self.assertEqual([1, 8, 9, 10], output_df["loc_min"].tolist())
            self.assertEqual([7, 8, 9, 10], output_df["loc_max"].tolist())
            self.assertNotIn(100, output_df["loc_max"].tolist())

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

    def test_effect_plot_main_reads_association_csv_and_writes_figure(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            aggregate_dir = experiment_dir / "aggregate"
            aggregate_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.association_row(ALL_SMELLS, 10, 20, 10, 20, ""),
                    self.association_row("AR", 10, 20, 30, 50, "x"),
                ]
            ).to_csv(aggregate_dir / "t2p-test-smell-association.csv", index=False)

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
                    / "t2p-test-smell-effectplot--historyFinder--nc--jnose--ch_diff.pdf"
                ).exists()
            )

    def test_effect_plot_writes_to_project_relative_output_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_directory = Path(tmpdir)
            experiment_dir = self.create_experiment(tmpdir)
            aggregate_dir = experiment_dir / "aggregate"
            aggregate_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.association_row(ALL_SMELLS, 10, 20, 10, 20, ""),
                    self.association_row("AR", 10, 20, 30, 50, "x"),
                ]
            ).to_csv(aggregate_dir / "t2p-test-smell-association.csv", index=False)

            barchart_main(
                [
                    "--project-directory",
                    str(project_directory),
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
                    "--output-directory",
                    "t2plinker-latex/figure",
                ]
            )

            self.assertTrue(
                (
                    project_directory
                    / "t2plinker-latex"
                    / "figure"
                    / "t2p-test-smell-effectplot--historyFinder--nc--jnose--ch_diff.pdf"
                ).exists()
            )

    def test_association_rows_report_pooled_and_project_adjusted_results(self):
        frame = pd.DataFrame(
            [
                self.generated_row("one", "test://r1", "prod://1", 20, 1, "AR", REVISION_GROUP_3),
                self.generated_row("one", "test://r2", "prod://2", 20, 1, "AR", REVISION_GROUP_3),
                self.generated_row("one", "test://p1", "prod://3", 1, 2, "", REVISION_GROUP_1),
                self.generated_row("one", "test://p2", "prod://4", 1, 2, "", REVISION_GROUP_1),
                self.generated_row("two", "test://r3", "prod://5", 20, 1, "VT", REVISION_GROUP_3),
                self.generated_row("two", "test://p3", "prod://6", 1, 2, "", REVISION_GROUP_1),
            ]
        )

        rows = association_rows(frame, strategy="nc", tool="historyFinder", smell_detector="jnose")
        association = pd.DataFrame(rows).set_index("smell")

        self.assertEqual(3, association.loc["AR", "focal_n"])
        self.assertEqual(3, association.loc["AR", "baseline_n"])
        self.assertGreater(association.loc["AR", "difference_pp"], 0)
        self.assertGreater(association.loc["AR", "odds_ratio"], 1)
        self.assertGreater(association.loc["AR", "mh_odds_ratio"], 1)
        self.assertLess(association.loc["AR", "difference_ci_low"], association.loc["AR", "difference_ci_high"])
        self.assertIn("fisher_p_adjusted", association.columns)
        self.assertEqual(ALL_LOC_GROUP, association.loc["AR", "loc_group"])
        self.assertEqual("RP", association.loc["AR", "baseline_group"])
        self.assertEqual("RRT", association.loc["AR", "focal_group"])

    def test_association_main_writes_unique_method_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.generated_row("demo", "test://r", "prod://1", 20, 1, "AR", REVISION_GROUP_3),
                    self.generated_row("demo", "test://r", "prod://2", 20, 1, "AR", REVISION_GROUP_3),
                    self.generated_row("demo", "test://p", "prod://3", 1, 2, "", REVISION_GROUP_1),
                ]
            ).to_csv(output_dir / "demo.csv", index=False)

            association_main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo-exp",
                    "--tools",
                    "historyFinder",
                    "--strategies",
                    "nc",
                    "--min-t2p-links",
                    "0",
                ]
            )

            output_df = pd.read_csv(experiment_dir / "aggregate" / "t2p-test-smell-association.csv")
            ar = output_df[output_df["smell"] == "AR"].iloc[0]
            self.assertEqual(1, ar["focal_n"])
            self.assertEqual(1, ar["baseline_n"])
            self.assertEqual("RP", ar["baseline_group"])
            self.assertEqual("RRT", ar["focal_group"])

    def test_benjamini_hochberg_preserves_order_and_monotonicity(self):
        adjusted = benjamini_hochberg([0.04, 0.001, 0.03])
        self.assertEqual([0.04, 0.003, 0.04], [round(value, 3) for value in adjusted])

    def test_effect_plot_orders_by_difference_and_marks_significance(self):
        frame = pd.DataFrame(
            [
                self.association_row("AR", 10, 20, 30, 50, "x"),
                self.association_row("VT", 10, 20, 12, 25, ""),
            ]
        )
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        try:
            plot_effect_axis(ax, frame, {"AR": "Assertion Roulette", "VT": "Verbose Test"})
            labels = [label.get_text() for label in ax.get_yticklabels()]
        finally:
            plt.close(fig)

        self.assertEqual(["VT", "AR"], effect_order(frame))
        self.assertEqual(["Verbose Test", "Assertion Roulette"], labels)

    def test_association_table_renders_and_main_writes_latex(self):
        frame = pd.DataFrame(
            [
                self.association_row(ALL_SMELLS, 50, 100, 75, 100, ""),
                self.association_row("AR", 10, 100, 30, 100, "x"),
            ]
        )
        latex = render_latex_table(frame, {"AR": "Assertion Roulette"})
        self.assertTrue(latex.startswith(r"\begin{tabular}{lrrrrrrr}"))
        self.assertNotIn(r"\begin{table}", latex)
        self.assertNotIn(r"\begin{table*}", latex)
        self.assertNotIn(r"\centering", latex)
        self.assertNotIn(r"\caption", latex)
        self.assertNotIn(r"\label", latex)
        self.assertIn(r"\textbf{Assertion Roulette}", latex)
        self.assertIn("Any test smell", latex)

        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            aggregate_dir = experiment_dir / "aggregate"
            aggregate_dir.mkdir(parents=True, exist_ok=True)
            frame.to_csv(aggregate_dir / "t2p-test-smell-association.csv", index=False)
            association_table_main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo-exp",
                    "--tools",
                    "historyFinder",
                    "--strategies",
                    "nc",
                ]
            )
            self.assertTrue(
                (
                    experiment_dir
                    / "figure"
                    / "t2p-test-smell-association-table--historyFinder--nc--jnose--ch_diff.tex"
                ).exists()
            )

    def test_association_table_renders_string_numeric_columns_and_blank_p_values(self):
        frame = pd.DataFrame(
            [
                self.association_row(ALL_SMELLS, 50, 100, 75, 100, ""),
                self.association_row("AR", 10, 100, 30, 100, "x"),
            ]
        ).astype(str)
        frame.loc[frame["smell"] == ALL_SMELLS, ["fisher_p_adjusted", "mh_p_adjusted"]] = ""

        latex = render_latex_table(frame, {"AR": "Assertion Roulette"})

        self.assertIn("30.0", latex)
        self.assertIn("2.00 [1.20, 3.00]", latex)
        self.assertIn("Any test smell was present in 50.0\\% of RP methods", latex)

    def test_association_table_writes_to_project_relative_output_directory(self):
        frame = pd.DataFrame(
            [
                self.association_row(ALL_SMELLS, 50, 100, 75, 100, ""),
                self.association_row("AR", 10, 100, 30, 100, "x"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            project_directory = Path(tmpdir)
            experiment_dir = self.create_experiment(tmpdir)
            aggregate_dir = experiment_dir / "aggregate"
            aggregate_dir.mkdir(parents=True, exist_ok=True)
            frame.to_csv(aggregate_dir / "t2p-test-smell-association.csv", index=False)

            association_table_main(
                [
                    "--project-directory",
                    str(project_directory),
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo-exp",
                    "--tools",
                    "historyFinder",
                    "--strategies",
                    "nc",
                    "--output-directory",
                    "t2plinker-latex/figure",
                ]
            )

            self.assertTrue(
                (
                    project_directory
                    / "t2plinker-latex"
                    / "figure"
                    / "t2p-test-smell-association-table--historyFinder--nc--jnose--ch_diff.tex"
                ).exists()
            )

    def test_wilcoxon_table_renders_all_and_loc_group_rows(self):
        frame = pd.DataFrame(
            [
                self.wilcoxon_row("ALL", 0, 0.0004, 0.83, "+", "large", "L"),
                self.wilcoxon_row("S", 1, 0.02, 0.20, "+", "small", "S"),
            ]
        ).astype(str)

        latex = render_wilcoxon_table(frame)

        self.assertIn("All", latex)
        self.assertIn("Small", latex)
        self.assertIn(r"$<.001$", latex)
        self.assertIn("+0.83", latex)
        self.assertIn("large", latex)
        self.assertTrue(latex.startswith(r"\begin{tabular}{lrrll}"))
        self.assertNotIn(r"\begin{table}", latex)
        self.assertNotIn(r"\begin{table*}", latex)
        self.assertNotIn(r"\centering", latex)
        self.assertNotIn(r"\caption", latex)
        self.assertNotIn(r"\label", latex)
        self.assertIn(r"\textbf{Group}", latex)
        self.assertNotIn(r"\textbf{LOC group}", latex)
        self.assertNotIn(r"\textbf{Groups}", latex)
        self.assertNotIn(r"\textbf{Smells}", latex)
        self.assertNotIn(r"\textbf{$W$}", latex)
        self.assertNotIn(r"\textbf{N}", latex)

    def test_wilcoxon_table_main_writes_latex(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            aggregate_dir = experiment_dir / "aggregate"
            aggregate_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.wilcoxon_row("ALL", 0, 0.0004, 0.83, "+", "large", "L"),
                    self.wilcoxon_row("S", 1, 0.02, 0.20, "+", "small", "S"),
                ]
            ).to_csv(aggregate_dir / "t2p-test-smell-prevalence-wilcoxon-srt.csv", index=False)

            wilcoxon_table_main(
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
                    "--smell-detector",
                    "jnose",
                ]
            )

            self.assertTrue(
                (
                    experiment_dir
                    / "figure"
                    / "t2p-test-smell-prevalence-wilcoxon-srt-table--historyFinder--nc--jnose--ch_diff.tex"
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
            legend_hatches = [handle.get_hatch() for handle in ax.get_legend().legend_handles]
        finally:
            plt.close(fig)

        self.assertEqual(["Assertion Roulette", "Verbose Test"], x_labels)
        self.assertEqual("", ax.get_title())
        self.assertEqual("# Test Method Revisions", ax.get_ylabel())
        self.assertNotIn(ALL_GROUPS, legend_labels)
        self.assertIn("Revision-Prone Test (RT)", legend_labels)
        self.assertIn("Recurrent Revision-Prone Test (RRT)", legend_labels)
        self.assertEqual(len(legend_hatches), len(set(legend_hatches)))
        self.assertTrue(all(hatch for hatch in legend_hatches))

    def test_boxplot_can_include_all_groups_when_requested(self):
        frame = pd.DataFrame(
            [
                {"smells": "AR", "from_ch_diff": 10, "rg_ch_diff": REVISION_GROUP_3},
                {"smells": "AR", "from_ch_diff": 5, "rg_ch_diff": REVISION_GROUP_2},
            ]
        )
        rows = boxplot_values(
            frame,
            "ch_diff",
            [REVISION_GROUP_2, REVISION_GROUP_3],
            {"AR": "Assertion Roulette"},
            include_all_groups=True,
        )

        self.assertIn(ALL_GROUPS, [row["group"] for row in rows])

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

    def test_boxplot_writes_to_project_relative_output_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            project_directory = Path(tmpdir)
            experiment_dir = self.create_experiment(tmpdir)
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.generated_row("demo", "test://A", "prod://A", 10, 1, "AR", REVISION_GROUP_3),
                    self.generated_row("demo", "test://B", "prod://B", 1, 5, "ET", REVISION_GROUP_1),
                ]
            ).to_csv(output_dir / "demo.csv", index=False)

            boxplot_main(
                [
                    "--project-directory",
                    str(project_directory),
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
                    "RP,RRT",
                    "--min-t2p-links",
                    "0",
                    "--smell-detector",
                    "jnose",
                    "--output-directory",
                    "t2plinker-latex/figure",
                ]
            )

            self.assertTrue(
                (
                    project_directory
                    / "t2plinker-latex"
                    / "figure"
                    / "t2p-test-smell-boxplot--historyFinder--nc--jnose--ch_diff.pdf"
                ).exists()
            )

    def test_boxplot_uses_unique_methods_and_excludes_conflicting_groups(self):
        frame = pd.DataFrame(
            [
                self.generated_row("demo", "test://dup", "prod://1", 10, 1, "AR", REVISION_GROUP_3),
                self.generated_row("demo", "test://dup", "prod://2", 10, 1, "VT", REVISION_GROUP_3),
                self.generated_row("demo", "test://conflict", "prod://3", 10, 1, "ET", REVISION_GROUP_3),
                self.generated_row("demo", "test://conflict", "prod://4", 1, 5, "ET", REVISION_GROUP_1),
                self.generated_row("demo", "test://rp", "prod://5", 1, 5, "AR", REVISION_GROUP_1),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "boxplot.pdf"
            captured_frames = []

            def capture_boxplot_values(plot_df, *args, **kwargs):
                captured_frames.append(plot_df.copy())
                return boxplot_values(plot_df, *args, **kwargs)

            with mock.patch("ptc.plot.t2p_test_smell_boxplot.boxplot_values", side_effect=capture_boxplot_values):
                plot_revision_type(
                    frame,
                    "ch_diff",
                    [REVISION_GROUP_1, REVISION_GROUP_3],
                    {"AR": "Assertion Roulette", "VT": "Verbose Test", "ET": "Exception Handling"},
                    output_file,
                )

            plotted_urls = captured_frames[0]["from_url"].tolist()
            self.assertEqual(["test://dup", "test://rp"], plotted_urls)
            self.assertEqual(["AR VT", "AR"], captured_frames[0]["smells"].tolist())

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
        self.assertEqual(ALL_LOC_GROUP, stat_row["loc_group"])
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
                    "--replace",
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
                    "loc_group",
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
            "rg_group": revision_group,
            "loc_group": ALL_LOC_GROUP,
            "smell": smell,
            "percent": percent,
            "smell_total": smell_total,
            "smell_n": smell_n,
        }

    def association_row(
        self,
        smell: str,
        baseline_smell_n: int,
        baseline_n: int,
        focal_smell_n: int,
        focal_n: int,
        significant: str,
    ) -> dict:
        baseline_percent = baseline_smell_n / baseline_n * 100
        focal_percent = focal_smell_n / focal_n * 100
        difference = focal_percent - baseline_percent
        return {
            "strategy": "nc",
            "tool": "historyFinder",
            "smell_detector": "jnose",
            "change": "ch_diff",
            "loc_group": ALL_LOC_GROUP,
            "baseline_group": REVISION_GROUP_1,
            "focal_group": REVISION_GROUP_3,
            "smell": smell,
            "baseline_n": baseline_n,
            "baseline_smell_n": baseline_smell_n,
            "baseline_percent": baseline_percent,
            "focal_n": focal_n,
            "focal_smell_n": focal_smell_n,
            "focal_percent": focal_percent,
            "difference_pp": difference,
            "difference_ci_low": difference - 5,
            "difference_ci_high": difference + 5,
            "odds_ratio": 2.0,
            "odds_ratio_ci_low": 1.2,
            "odds_ratio_ci_high": 3.0,
            "fisher_p": 0.01,
            "fisher_p_adjusted": 0.02,
            "significant": significant,
            "mh_odds_ratio": 1.8,
            "mh_p": 0.02,
            "mh_p_adjusted": 0.03,
            "mh_significant": significant,
            "sensitivity_agrees": significant,
        }

    def wilcoxon_row(
        self,
        loc_group: str,
        w_stat: float,
        w_p: float,
        d_value: float,
        d_sign: str,
        effect_size: str,
        marker_column: str,
    ) -> dict:
        markers = {column: "" for column in ["N", "S", "M", "L"]}
        markers[marker_column] = "x"
        return {
            "groups": "RP,RRT",
            "strategy": "nc",
            "tool": "historyFinder",
            "smell_detector": "jnose",
            "change": "ch_diff",
            "loc_group": loc_group,
            "size": 17,
            "g1_size": 17,
            "g2_size": 17,
            "w_stat": w_stat,
            "w_p": w_p,
            "d_value": d_value,
            "d_sign": d_sign,
            "effect_size": effect_size,
            **markers,
        }


if __name__ == "__main__":
    unittest.main()
