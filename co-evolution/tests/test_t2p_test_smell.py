import io
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
from ptc.generator.t2p_test_smell_count_mww import (
    COUNT_MWW_COLUMNS,
    count_mww_rows,
    main as count_mww_main,
    method_count_frame,
    selected_revision_group_pairs,
)
from ptc.generator.t2p_test_smell_size_control_association import (
    COMBINED_TOP_SMELLS,
    CONTROL_SIZE_GROUPS,
    association_top_smells,
    controlled_association_rows,
    fixed_control_group,
    fixed_control_group_frame,
    main as size_control_association_main,
    top_smells_from_association,
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
    selected_revision_group_pairs as selected_association_revision_group_pairs,
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
    EFFECT_COMPARISON_STYLES,
    EFFECT_LEGEND_FONTSIZE,
    EFFECT_MATCHED_CI_LINEWIDTH,
    EFFECT_MATCHED_XTICK_FONTSIZE,
    EFFECT_X_AXIS_LABEL,
    EFFECT_X_AXIS_MAX,
    EFFECT_X_AXIS_MIN,
    EFFECT_XTICK_FONTSIZE,
    EFFECT_Y_AXIS_LABEL,
    EFFECT_YTICK_FONTSIZE,
    NONSIGNIFICANT_MARKER,
    SIGNIFICANT_MARKER,
    comparison_pairs,
    display_smell,
    effect_order,
    format_any_smell_summary,
    main as barchart_main,
    plot_effect,
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
    count_annotation,
    extreme_point_count,
    load_generated_frames,
    main as boxplot_main,
    plot_boxplot_axis,
    plot_revision_type,
    selected_revision_groups,
    unique_smell_count,
)
from ptc.plot.t2p_test_smell_size_control_effectplot import (
    SIZE_CONTROL_CI_LINEWIDTH,
    SIZE_CONTROL_XTICK_FONTSIZE,
    METHOD_SIZE_LABEL,
    control_group_order as size_control_group_order,
    main as size_control_effectplot_main,
    plot_size_control_effect,
    series_label,
    series_order,
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
        self.assertEqual(REVISION_GROUP_2, assign_revision_group(14, 10))
        self.assertEqual(REVISION_GROUP_3, assign_revision_group(15, 10))
        self.assertEqual(REVISION_GROUP_1, assign_revision_group(2, 3, min_t2p_revision=5))
        self.assertEqual(REVISION_GROUP_1, assign_revision_group(10, 10, min_t2p_revision=5))
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
        self.assertEqual([REVISION_GROUP_2, REVISION_GROUP_3], selected_revision_groups("MTR,HTR"))
        with self.assertRaises(ValueError):
            selected_revision_groups("MTR,unknown")
        with self.assertRaises(ValueError):
            selected_revision_groups("RP,RRT")

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
                        "nc,omc--nc",
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

            with mock.patch("sys.stdout", new_callable=io.StringIO) as stdout:
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
                        "MTR",
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
            self.assertIn("Any test smell: NTR 50.0% vs HTR 50.0% (+0.0 pp)", stdout.getvalue())

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
        self.assertEqual("NTR", association.loc["AR", "baseline_group"])
        self.assertEqual("HTR", association.loc["AR", "focal_group"])

    def test_association_revision_group_pair_defaults_and_custom_order(self):
        self.assertEqual(
            [(REVISION_GROUP_3, REVISION_GROUP_1)],
            selected_association_revision_group_pairs(None),
        )
        self.assertEqual(
            [(REVISION_GROUP_3, REVISION_GROUP_1), (REVISION_GROUP_2, REVISION_GROUP_1)],
            selected_association_revision_group_pairs("HTR,NTR;MTR,NTR"),
        )
        with self.assertRaises(ValueError):
            selected_association_revision_group_pairs("HTR")

    def test_association_main_writes_unique_method_results(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.generated_row("demo", "test://r", "prod://1", 20, 1, "AR", REVISION_GROUP_3),
                    self.generated_row("demo", "test://r", "prod://2", 20, 1, "AR", REVISION_GROUP_3),
                    self.generated_row("demo", "test://m", "prod://4", 8, 1, "VT", REVISION_GROUP_2),
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
                    "--revision-group-pairs",
                    "HTR,NTR;MTR,NTR",
                ]
            )

            output_df = pd.read_csv(experiment_dir / "aggregate" / "t2p-test-smell-association.csv")
            self.assertEqual(
                {("HTR", "NTR"), ("MTR", "NTR")},
                set(zip(output_df["focal_group"], output_df["baseline_group"])),
            )
            ar = output_df[(output_df["smell"] == "AR") & (output_df["focal_group"] == "HTR")].iloc[0]
            self.assertEqual(1, ar["focal_n"])
            self.assertEqual(1, ar["baseline_n"])
            self.assertEqual("NTR", ar["baseline_group"])
            self.assertEqual("HTR", ar["focal_group"])

    def test_benjamini_hochberg_preserves_order_and_monotonicity(self):
        adjusted = benjamini_hochberg([0.04, 0.001, 0.03])
        self.assertEqual([0.04, 0.003, 0.04], [round(value, 3) for value in adjusted])

    def test_effect_plot_orders_by_difference_and_marks_significance(self):
        frame = pd.DataFrame(
            [
                self.association_row("AR", 10, 20, 30, 50, "x"),
                self.association_row("VT", 10, 20, 12, 25, ""),
                self.association_row("AR", 10, 20, 20, 50, "", focal_group=REVISION_GROUP_2),
                self.association_row("VT", 10, 20, 15, 50, "x", focal_group=REVISION_GROUP_2),
            ]
        )
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        try:
            plot_effect_axis(ax, frame, {"AR": "Assertion Roulette", "VT": "Verbose Test"})
            labels = [label.get_text() for label in ax.get_yticklabels()]
            legend = ax.get_legend()
            legend_markers = [handle.get_marker() for handle in legend.legend_handles]
            legend_labels = [text.get_text() for text in legend.get_texts()]
            facecolors = [
                collection.get_facecolors()[0].tolist()
                for collection in ax.collections
                if len(collection.get_facecolors()) > 0
            ]
            minor_ticks = ax.get_xticks(minor=True).astype(int).tolist()
            ci_linewidth = ax.collections[0].get_linewidths()[0]
        finally:
            plt.close(fig)

        self.assertEqual(["VT", "AR"], effect_order(frame))
        self.assertEqual(["Verbose Test", "Assertion Roulette"], labels)
        self.assertEqual(EFFECT_X_AXIS_LABEL, ax.get_xlabel())
        self.assertEqual(EFFECT_Y_AXIS_LABEL, ax.get_ylabel())
        self.assertEqual(["D", "s"], legend_markers)
        self.assertEqual(["HTR - NTR", "MTR - NTR"], legend_labels)
        self.assertNotIn("BH-adjusted p < .05", legend_labels)
        self.assertNotIn("Not significant", legend_labels)
        self.assertIn([1.0, 1.0, 1.0, 1.0], facecolors)
        self.assertTrue(any(facecolor != [1.0, 1.0, 1.0, 1.0] for facecolor in facecolors))
        self.assertEqual((EFFECT_X_AXIS_MIN, EFFECT_X_AXIS_MAX), tuple(int(value) for value in ax.get_xlim()))
        self.assertEqual(list(range(EFFECT_X_AXIS_MIN, EFFECT_X_AXIS_MAX + 1, 2)), ax.get_xticks().astype(int).tolist())
        self.assertIn(-1, minor_ticks)
        self.assertIn(1, minor_ticks)
        self.assertIn(17, minor_ticks)
        self.assertEqual(SIZE_CONTROL_XTICK_FONTSIZE, EFFECT_MATCHED_XTICK_FONTSIZE)
        self.assertEqual(SIZE_CONTROL_CI_LINEWIDTH, EFFECT_MATCHED_CI_LINEWIDTH)
        self.assertEqual(EFFECT_MATCHED_XTICK_FONTSIZE, ax.xaxis.get_ticklabels()[0].get_fontsize())
        self.assertEqual(EFFECT_MATCHED_CI_LINEWIDTH, ci_linewidth)
        self.assertGreaterEqual(ax.yaxis.get_ticklabels()[0].get_fontsize(), EFFECT_YTICK_FONTSIZE)
        self.assertEqual(EFFECT_LEGEND_FONTSIZE, legend.get_texts()[0].get_fontsize())
        self.assertEqual(
            [(REVISION_GROUP_3, REVISION_GROUP_1), (REVISION_GROUP_2, REVISION_GROUP_1)],
            comparison_pairs(frame),
        )
        self.assertEqual("D", EFFECT_COMPARISON_STYLES[(REVISION_GROUP_3, REVISION_GROUP_1)]["marker"])
        self.assertEqual("s", EFFECT_COMPARISON_STYLES[(REVISION_GROUP_2, REVISION_GROUP_1)]["marker"])

    def test_effect_plot_formats_any_smell_summary(self):
        frame = pd.DataFrame(
            [
                self.association_row(ALL_SMELLS, 379, 1000, 675, 1000, ""),
                self.association_row("AR", 10, 20, 30, 50, "x"),
            ]
        )

        self.assertEqual(
            "Any test smell: NTR 37.9% vs HTR 67.5% (+29.6 pp)",
            format_any_smell_summary(frame),
        )

    def test_effect_plot_formats_multiple_any_smell_summaries(self):
        frame = pd.DataFrame(
            [
                self.association_row(ALL_SMELLS, 379, 1000, 675, 1000, ""),
                self.association_row(ALL_SMELLS, 379, 1000, 500, 1000, "", focal_group=REVISION_GROUP_2),
            ]
        )

        self.assertEqual(
            "Any test smell: NTR 37.9% vs HTR 67.5% (+29.6 pp)\n"
            "Any test smell: NTR 37.9% vs MTR 50.0% (+12.1 pp)",
            format_any_smell_summary(frame),
        )

    def test_effect_plot_has_no_generated_title(self):
        frame = pd.DataFrame(
            [
                self.association_row(ALL_SMELLS, 50, 100, 75, 100, ""),
                self.association_row("AR", 10, 20, 30, 50, "x"),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            with mock.patch("matplotlib.figure.Figure.suptitle") as suptitle:
                plot_effect(
                    frame,
                    strategy="nc",
                    tool="historyFinder",
                    smell_detector="jnose",
                    change="ch_diff",
                    smell_names={"AR": "Assertion Roulette"},
                    output_file=Path(tmpdir) / "effect.pdf",
                )

        suptitle.assert_not_called()

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
        self.assertNotIn(r"\footnotesize", latex)
        self.assertNotIn(r"\textbf{Assertion Roulette}", latex)
        self.assertIn("Assertion Roulette", latex)
        self.assertIn("0.020", latex)
        self.assertTrue(latex.rstrip().endswith(r"\end{tabular}"))

        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            aggregate_dir = experiment_dir / "aggregate"
            aggregate_dir.mkdir(parents=True, exist_ok=True)
            table_input = pd.concat(
                [
                    frame,
                    pd.DataFrame(
                        [
                            self.association_row("VT", 5, 100, 12, 100, "", focal_group=REVISION_GROUP_2),
                        ]
                    ),
                ],
                ignore_index=True,
            )
            table_input.to_csv(aggregate_dir / "t2p-test-smell-association.csv", index=False)
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
            latex_file = (
                experiment_dir
                / "figure"
                / "t2p-test-smell-association-table--historyFinder--nc--jnose--ch_diff.tex"
            )
            rendered = latex_file.read_text(encoding="utf-8")
            self.assertIn("Assertion Roulette", rendered)
            self.assertNotIn("Verbose Test", rendered)

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
        self.assertNotIn("Any test smell was present", latex)
        self.assertNotIn(r"\footnotesize", latex)

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

    def test_plot_boxplot_axis_uses_independent_revision_and_loc_labels(self):
        frame = pd.DataFrame(
            [
                {"from_url": "test://A", "smells": "AR", "rg_ch_diff": REVISION_GROUP_3},
                {"from_url": "test://B", "smells": "AR VT", "rg_ch_diff": REVISION_GROUP_2},
                {"from_url": "test://C", "smells": "", "rg_ch_diff": REVISION_GROUP_2},
            ]
        )
        smell_frames = [
            pd.DataFrame(
                [
                    {"url": f"test://{index}", "smell": "AR", "loc": index}
                    for index in range(1, 11)
                ]
            )
        ]
        rows = boxplot_values(
            frame,
            "ch_diff",
            [REVISION_GROUP_2, REVISION_GROUP_3],
            smell_frames=smell_frames,
        )
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots()
        try:
            plot_boxplot_axis(ax, rows, [REVISION_GROUP_2, REVISION_GROUP_3])
            x_labels = [label.get_text() for label in ax.get_xticklabels()]
        finally:
            plt.close(fig)

        self.assertEqual(["MTR", "HTR", "S", "M", "L", "XL"], x_labels)
        self.assertEqual("", ax.get_title())
        self.assertEqual("# Unique Test Smells", ax.get_ylabel())
        self.assertEqual("", ax.get_xlabel())
        self.assertIsNone(ax.get_legend())
        self.assertEqual(list(range(0, 11)), [int(tick) for tick in ax.get_yticks()])
        self.assertEqual((-0.1, 10.0), ax.get_ylim())
        annotation_labels = [text.get_text() for text in ax.texts]
        self.assertTrue(any(label.startswith("n=") and "\next=" in label for label in annotation_labels))
        self.assertTrue(all(text.get_fontsize() >= 8 for text in ax.texts))
        self.assertTrue(all(text.get_position()[1] < ax.get_ylim()[1] for text in ax.texts))

    def test_boxplot_extreme_point_count_uses_iqr_whisker_rule(self):
        self.assertEqual(0, extreme_point_count([]))
        self.assertEqual(1, extreme_point_count([0, 0, 0, 0, 5]))
        self.assertEqual("n=68,896\next=4,676", count_annotation(68896, 4676))

    def test_boxplot_values_counts_revision_and_loc_groups_independently(self):
        frame = pd.DataFrame(
            [
                {"from_url": "test://A", "smells": "AR AR VT", "rg_ch_diff": REVISION_GROUP_3},
                {"from_url": "test://B", "smells": "", "rg_ch_diff": REVISION_GROUP_2},
                {"from_url": "test://C", "smells": "ET", "rg_ch_diff": REVISION_GROUP_2},
            ]
        )
        smell_rows = [{"url": f"test://{index}", "smell": "AR", "loc": index} for index in range(1, 10)]
        smell_rows.extend(
            [
                {"url": "test://outside", "smell": "AR", "loc": 10},
                {"url": "test://outside", "smell": "VT", "loc": 10},
            ]
        )
        rows = boxplot_values(
            frame,
            "ch_diff",
            [REVISION_GROUP_2, REVISION_GROUP_3],
            smell_frames=[pd.DataFrame(smell_rows)],
        )

        htr = next(row for row in rows if row["category"] == REVISION_GROUP_3)
        mtr = next(row for row in rows if row["category"] == REVISION_GROUP_2)
        xl = next(row for row in rows if row["category"] == "XL")
        self.assertEqual([2], htr["values"])
        self.assertEqual([0, 1], mtr["values"])
        self.assertEqual([2], xl["values"])
        self.assertEqual(2, unique_smell_count("AR AR VT"))
        self.assertEqual(0, unique_smell_count(""))

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
            self.write_smells(
                experiment_dir,
                "demo",
                [
                    {"url": "test://A", "smell": "AR", "loc": 10},
                    {"url": "test://B", "smell": "VT", "loc": 20},
                    {"url": "test://C", "smell": "ET", "loc": 30},
                ],
            )

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
                    "MTR,HTR",
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
            self.write_smells(
                experiment_dir,
                "demo",
                [
                    {"url": "test://A", "smell": "AR", "loc": 10},
                    {"url": "test://B", "smell": "ET", "loc": 20},
                ],
            )

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
                    "NTR,HTR",
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
                    output_file,
                    smell_frames=[
                        pd.DataFrame(
                            [
                                {"url": "test://dup", "smell": "AR", "loc": 1},
                                {"url": "test://rp", "smell": "AR", "loc": 2},
                            ]
                        )
                    ],
                )

            plotted_urls = captured_frames[0]["from_url"].tolist()
            self.assertEqual(["test://dup", "test://rp"], plotted_urls)
            self.assertEqual(["AR VT", "AR"], captured_frames[0]["smells"].tolist())

    def test_wilcoxon_requires_two_revision_groups_and_preserves_order(self):
        self.assertEqual([REVISION_GROUP_3, REVISION_GROUP_1], selected_two_revision_groups(None))
        self.assertEqual([REVISION_GROUP_3, REVISION_GROUP_1], selected_two_revision_groups("HTR,NTR"))
        with self.assertRaises(ValueError):
            selected_two_revision_groups("MTR")
        with self.assertRaises(ValueError):
            selected_two_revision_groups("RRT,RP")

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
        self.assertEqual([75, 25], paired_df["g1_percent"].tolist())
        self.assertEqual([25, 0], paired_df["g2_percent"].tolist())
        self.assertEqual([3, 1], paired_df["g1_smell_n"].tolist())
        self.assertEqual([1, 0], paired_df["g2_smell_n"].tolist())

    def test_wilcoxon_build_stat_row_excludes_all_and_uses_percent(self):
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

        self.assertEqual("HTR,NTR", stat_row["groups"])
        self.assertEqual(ALL_LOC_GROUP, stat_row["loc_group"])
        self.assertEqual(2, stat_row["size"])
        self.assertEqual(2, stat_row["g1_size"])
        self.assertEqual(2, stat_row["g2_size"])
        self.assertIn("w_stat", stat_row)
        self.assertIn("w_p", stat_row)

    def test_wilcoxon_build_stat_row_uses_percent_not_raw_smell_counts(self):
        prevalence = pd.DataFrame(
            [
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "AR", 50, 2, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_3, "ET", 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "AR", 25, 4, 1),
                self.prevalence_row("nc", "historyFinder", "jnose", "ch_diff", REVISION_GROUP_1, "ET", 10, 10, 1),
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

        self.assertEqual("+", stat_row["d_sign"])
        self.assertGreater(stat_row["d_value"], 0)

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
                    "HTR,NTR",
                    "--smell-detector",
                    "jnose",
                    "--replace",
                ]
            )

            output_df = pd.read_csv(
                aggregate_dir / "t2p-test-smell-prevalence-wilcoxon-srt.csv",
                keep_default_na=False,
            )
            self.assertEqual(["HTR,NTR"], output_df["groups"].tolist())
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

    def test_count_mww_revision_group_pair_defaults_and_custom_order(self):
        self.assertEqual(
            [(REVISION_GROUP_3, REVISION_GROUP_1), (REVISION_GROUP_3, REVISION_GROUP_2)],
            selected_revision_group_pairs(None),
        )
        self.assertEqual(
            [(REVISION_GROUP_3, REVISION_GROUP_1), (REVISION_GROUP_3, REVISION_GROUP_2)],
            selected_revision_group_pairs("HTR,NTR;HTR,MTR"),
        )
        with self.assertRaises(ValueError):
            selected_revision_group_pairs("HTR")

    def test_count_mww_method_frame_counts_unique_smells_and_excludes_conflicts(self):
        frame = pd.DataFrame(
            [
                self.generated_row("demo", "test://dup", "prod://1", 10, 1, "AR", REVISION_GROUP_3),
                self.generated_row("demo", "test://dup", "prod://2", 10, 1, "AR VT", REVISION_GROUP_3),
                self.generated_row("demo", "test://conflict", "prod://3", 10, 1, "ET", REVISION_GROUP_3),
                self.generated_row("demo", "test://conflict", "prod://4", 1, 5, "ET", REVISION_GROUP_1),
                self.generated_row("demo", "test://empty", "prod://5", 1, 5, "", REVISION_GROUP_1),
            ]
        )

        output = method_count_frame(frame, "ch_diff", [REVISION_GROUP_3, REVISION_GROUP_1])

        self.assertEqual(["test://dup", "test://empty"], output["from_url"].tolist())
        self.assertEqual([2, 0], output["unique_smell_count"].tolist())

    def test_count_mww_rows_include_all_and_loc_strata(self):
        frame = pd.DataFrame(
            [
                self.generated_row("demo", "test://h1", "prod://1", 10, 1, "AR VT", REVISION_GROUP_3),
                self.generated_row("demo", "test://h2", "prod://2", 11, 1, "AR VT ET", REVISION_GROUP_3),
                self.generated_row("demo", "test://n1", "prod://3", 1, 5, "", REVISION_GROUP_1),
                self.generated_row("demo", "test://n2", "prod://4", 1, 5, "AR", REVISION_GROUP_1),
                self.generated_row("demo", "test://m1", "prod://5", 4, 1, "AR", REVISION_GROUP_2),
                self.generated_row("demo", "test://m2", "prod://6", 5, 1, "AR VT", REVISION_GROUP_2),
            ]
        )
        loc_groups = pd.DataFrame(
            [
                {"from_url": "test://h1", "loc_group": "S"},
                {"from_url": "test://n1", "loc_group": "S"},
                {"from_url": "test://h2", "loc_group": "M"},
                {"from_url": "test://n2", "loc_group": "M"},
                {"from_url": "test://m1", "loc_group": "S"},
                {"from_url": "test://m2", "loc_group": "M"},
            ]
        )

        rows = count_mww_rows(
            frame,
            strategy="nc",
            tool="historyFinder",
            smell_detector="jnose",
            revision_type="ch_diff",
            revision_group_pairs=[(REVISION_GROUP_3, REVISION_GROUP_1), (REVISION_GROUP_3, REVISION_GROUP_2)],
            loc_groups=loc_groups,
        )

        comparisons = {(row["comparison"], row["loc_group"]) for row in rows}
        self.assertIn(("HTR,NTR", ALL_LOC_GROUP), comparisons)
        self.assertIn(("HTR,NTR", "S"), comparisons)
        self.assertIn(("HTR,NTR", "M"), comparisons)
        self.assertIn(("HTR,MTR", ALL_LOC_GROUP), comparisons)
        all_row = next(row for row in rows if row["comparison"] == "HTR,NTR" and row["loc_group"] == ALL_LOC_GROUP)
        self.assertEqual(4, all_row["size"])
        self.assertEqual(2, all_row["g1_size"])
        self.assertEqual(2, all_row["g2_size"])
        self.assertGreater(all_row["d_value"], 0)
        self.assertEqual("+", all_row["d_sign"])
        self.assertIn("mww_p", all_row)

    def test_count_mww_main_writes_expected_schema(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.generated_row("demo", "test://h1", "prod://1", 10, 1, "AR VT", REVISION_GROUP_3),
                    self.generated_row("demo", "test://h2", "prod://2", 11, 1, "AR VT ET", REVISION_GROUP_3),
                    self.generated_row("demo", "test://n1", "prod://3", 1, 5, "", REVISION_GROUP_1),
                    self.generated_row("demo", "test://n2", "prod://4", 1, 5, "AR", REVISION_GROUP_1),
                    self.generated_row("demo", "test://m1", "prod://5", 4, 1, "AR", REVISION_GROUP_2),
                    self.generated_row("demo", "test://m2", "prod://6", 5, 1, "AR VT", REVISION_GROUP_2),
                ]
            ).to_csv(output_dir / "demo.csv", index=False)
            self.write_smells(
                experiment_dir,
                "demo",
                [
                    {"url": "test://h1", "smell": "AR", "loc": 1},
                    {"url": "test://h2", "smell": "AR", "loc": 2},
                    {"url": "test://n1", "smell": "", "loc": 3},
                    {"url": "test://n2", "smell": "AR", "loc": 4},
                    {"url": "test://m1", "smell": "AR", "loc": 5},
                    {"url": "test://m2", "smell": "AR", "loc": 6},
                ],
            )

            count_mww_main(
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
                    "--min-t2p-links",
                    "0",
                    "--replace",
                ]
            )

            output_df = pd.read_csv(
                experiment_dir / "aggregate" / "t2p-test-smell-count-mww.csv",
                keep_default_na=False,
            )
            self.assertEqual(COUNT_MWW_COLUMNS, output_df.columns.tolist())
            self.assertEqual(["HTR,MTR", "HTR,NTR"], sorted(output_df["comparison"].unique().tolist()))
            self.assertIn(ALL_LOC_GROUP, output_df["loc_group"].tolist())

    def test_size_control_groups_use_fixed_paper_loc_ranges(self):
        self.assertEqual("Small", fixed_control_group(1))
        self.assertEqual("Small", fixed_control_group(29))
        self.assertEqual("Medium", fixed_control_group(30))
        self.assertEqual("Medium", fixed_control_group(60))
        self.assertEqual("Large", fixed_control_group(61))

        frame = fixed_control_group_frame(
            [
                pd.DataFrame(
                    [
                        {"url": "test://s", "loc": 29},
                        {"url": "test://m", "loc": 30},
                        {"url": "test://l", "loc": 61},
                        {"url": "test://bad", "loc": 0},
                    ]
                )
            ]
        ).set_index("from_url")

        self.assertEqual("Small", frame.loc["test://s", "control_group"])
        self.assertEqual("Medium", frame.loc["test://m", "control_group"])
        self.assertEqual("Large", frame.loc["test://l", "control_group"])
        self.assertNotIn("test://bad", frame.index)

    def test_size_control_rows_use_association_top_smells_and_combined_row(self):
        frame = pd.DataFrame(
            [
                self.generated_row("demo", "test://h-small", "prod://1", 10, 1, "AR VT AR", REVISION_GROUP_3),
                self.generated_row("demo", "test://h-medium", "prod://2", 10, 1, "AR EH", REVISION_GROUP_3),
                self.generated_row("demo", "test://h-large", "prod://3", 10, 1, "AR DA", REVISION_GROUP_3),
                self.generated_row("demo", "test://m-small", "prod://4", 5, 1, "VT", REVISION_GROUP_2),
                self.generated_row("demo", "test://m-medium", "prod://5", 5, 1, "AR", REVISION_GROUP_2),
                self.generated_row("demo", "test://m-large", "prod://6", 5, 1, "MN", REVISION_GROUP_2),
                self.generated_row("demo", "test://n-small", "prod://7", 1, 5, "", REVISION_GROUP_1),
                self.generated_row("demo", "test://n-medium", "prod://8", 1, 5, "VT", REVISION_GROUP_1),
                self.generated_row("demo", "test://n-large", "prod://9", 1, 5, "", REVISION_GROUP_1),
                self.generated_row("demo", "test://h-large-2", "prod://10", 10, 1, "CTL", REVISION_GROUP_3),
                self.generated_row("demo", "test://m-large-2", "prod://11", 5, 1, "LT", REVISION_GROUP_2),
                self.generated_row("demo", "test://n-large-2", "prod://12", 1, 5, "", REVISION_GROUP_1),
            ]
        )
        control_groups = pd.DataFrame(
            [
                {"from_url": "test://h-small", "control_group": "Small"},
                {"from_url": "test://m-small", "control_group": "Small"},
                {"from_url": "test://n-small", "control_group": "Small"},
                {"from_url": "test://h-medium", "control_group": "Medium"},
                {"from_url": "test://m-medium", "control_group": "Medium"},
                {"from_url": "test://n-medium", "control_group": "Medium"},
                {"from_url": "test://h-large", "control_group": "Large"},
                {"from_url": "test://m-large", "control_group": "Large"},
                {"from_url": "test://n-large", "control_group": "Large"},
                {"from_url": "test://h-large-2", "control_group": "Large"},
                {"from_url": "test://m-large-2", "control_group": "Large"},
                {"from_url": "test://n-large-2", "control_group": "Large"},
            ]
        )
        association_frame = pd.DataFrame(
            [
                self.association_output_row("AR", 16.5, REVISION_GROUP_3, REVISION_GROUP_1),
                self.association_output_row("VT", 11.9, REVISION_GROUP_3, REVISION_GROUP_1),
                self.association_output_row("MNT", 8.4, REVISION_GROUP_3, REVISION_GROUP_1),
                self.association_output_row("CTL", 5.5, REVISION_GROUP_3, REVISION_GROUP_1),
                self.association_output_row("EH", 5.4, REVISION_GROUP_3, REVISION_GROUP_1),
                self.association_output_row("DA", 4.8, REVISION_GROUP_3, REVISION_GROUP_1),
                self.association_output_row(ALL_SMELLS, 20.0, REVISION_GROUP_3, REVISION_GROUP_1),
                self.association_output_row("ET", 1.6, REVISION_GROUP_2, REVISION_GROUP_1),
            ]
        )
        self.assertEqual(
            [("AR", 16.5), ("VT", 11.9), ("MNT", 8.4), ("CTL", 5.5), ("EH", 5.4)],
            association_top_smells(
                association_frame,
                strategy="nc",
                tool="historyFinder",
                smell_detector="jnose",
                revision_type="ch_diff",
                focal_group=REVISION_GROUP_3,
                baseline_group=REVISION_GROUP_1,
                top_n=5,
            ),
        )
        selected_smells = top_smells_from_association(
            association_frame,
            strategy="nc",
            tool="historyFinder",
            smell_detector="jnose",
            revision_type="ch_diff",
            top_n=5,
        )
        self.assertEqual(["AR", "VT", "MNT", "CTL", "EH"], selected_smells)

        rows = controlled_association_rows(
            frame,
            strategy="nc",
            tool="historyFinder",
            smell_detector="jnose",
            revision_type="ch_diff",
            control_groups=control_groups,
            top_smells=selected_smells,
        )
        output = pd.DataFrame(rows)

        self.assertEqual(set(CONTROL_SIZE_GROUPS), set(output["control_group"].unique()))
        self.assertEqual({REVISION_GROUP_2, REVISION_GROUP_3}, set(output["focal_group"].unique()))
        self.assertEqual({REVISION_GROUP_1}, set(output["baseline_group"].unique()))
        self.assertEqual({"AR", "VT", "MNT", "CTL", "EH", COMBINED_TOP_SMELLS}, set(output["smell"].unique()))
        self.assertEqual(36, len(output))
        htr_small_ar = output[
            (output["control_group"] == "Small")
            & (output["focal_group"] == REVISION_GROUP_3)
            & (output["smell"] == "AR")
        ].iloc[0]
        self.assertEqual(1, htr_small_ar["focal_n"])
        self.assertEqual(1, htr_small_ar["baseline_n"])
        htr_small_combined = output[
            (output["control_group"] == "Small")
            & (output["focal_group"] == REVISION_GROUP_3)
            & (output["smell"] == COMBINED_TOP_SMELLS)
        ].iloc[0]
        self.assertEqual(1, htr_small_combined["focal_smell_n"])
        self.assertEqual(0, htr_small_combined["baseline_smell_n"])
        self.assertTrue(pd.isna(htr_small_combined["fisher_p_adjusted"]))
        self.assertEqual("", htr_small_combined["significant"])
        self.assertIn("difference_ci_low", output.columns)
        self.assertIn("fisher_p_adjusted", output.columns)

    def test_size_control_effectplot_writes_pdf(self):
        frame = pd.DataFrame(
            [
                self.size_control_row("Small", "AR", REVISION_GROUP_3, 0, 10, 5, 10, ""),
                self.size_control_row("Small", "AR", REVISION_GROUP_2, 0, 10, 2, 10, "x"),
                self.size_control_row("Medium", "AR", REVISION_GROUP_3, 1, 10, 4, 10, "x"),
                self.size_control_row("Medium", "AR", REVISION_GROUP_2, 1, 10, 3, 10, ""),
                self.size_control_row("Large", "AR", REVISION_GROUP_3, 0, 10, 6, 10, "x"),
                self.size_control_row("Large", "AR", REVISION_GROUP_2, 0, 10, 2, 10, ""),
                self.size_control_row("Small", "VT", REVISION_GROUP_3, 1, 10, 3, 10, ""),
                self.size_control_row("Small", "VT", REVISION_GROUP_2, 1, 10, 2, 10, ""),
                self.size_control_row("Medium", "VT", REVISION_GROUP_3, 1, 10, 4, 10, "x"),
                self.size_control_row("Medium", "VT", REVISION_GROUP_2, 1, 10, 2, 10, ""),
                self.size_control_row("Large", "VT", REVISION_GROUP_3, 1, 10, 5, 10, "x"),
                self.size_control_row("Large", "VT", REVISION_GROUP_2, 1, 10, 2, 10, ""),
                self.size_control_row("Small", COMBINED_TOP_SMELLS, REVISION_GROUP_3, 1, 10, 6, 10, ""),
                self.size_control_row("Small", COMBINED_TOP_SMELLS, REVISION_GROUP_2, 1, 10, 3, 10, ""),
                self.size_control_row("Medium", COMBINED_TOP_SMELLS, REVISION_GROUP_3, 2, 10, 6, 10, ""),
                self.size_control_row("Medium", COMBINED_TOP_SMELLS, REVISION_GROUP_2, 2, 10, 4, 10, ""),
                self.size_control_row("Large", COMBINED_TOP_SMELLS, REVISION_GROUP_3, 1, 10, 7, 10, ""),
                self.size_control_row("Large", COMBINED_TOP_SMELLS, REVISION_GROUP_2, 1, 10, 3, 10, ""),
            ]
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "size-control.pdf"
            import matplotlib.pyplot as plt

            real_close = plt.close
            with mock.patch("matplotlib.pyplot.close") as close:
                plot_size_control_effect(
                    frame,
                    strategy="nc",
                    tool="historyFinder",
                    smell_detector="jnose",
                    change="ch_diff",
                    smell_names={"AR": "Assertion Roulette", "VT": "Verbose Test"},
                    output_file=output_file,
                )
                figure = plt.gcf()
                axes_count = len(figure.axes)
                legend_labels = [text.get_text() for text in figure.legends[0].get_texts()]
                ytick_labels = [text.get_text() for text in figure.axes[0].get_yticklabels()]
                ylabel = figure.axes[0].get_ylabel()
                ylabel_size = figure.axes[0].yaxis.label.get_fontsize()
                xlabel_size = figure._supxlabel.get_fontsize()
                ci_linewidth = figure.axes[0].collections[0].get_linewidths()[0]
                close.assert_called_once()
                real_close(figure)

            self.assertTrue(output_file.exists())
            top5_frame = frame[frame["smell"] == COMBINED_TOP_SMELLS]
            self.assertEqual(["Small", "Medium", "Large"], size_control_group_order(top5_frame))
            self.assertEqual(["Small", "Medium", "Large"], ytick_labels)
            self.assertEqual(METHOD_SIZE_LABEL, ylabel)
            self.assertEqual(xlabel_size, ylabel_size)
            self.assertEqual(SIZE_CONTROL_CI_LINEWIDTH, ci_linewidth)
            self.assertEqual(1, axes_count)
            self.assertNotIn("Assertion Roulette", ytick_labels)
            self.assertNotIn("Verbose Test", ytick_labels)
            self.assertEqual(["HTR - NTR", "MTR - NTR"], legend_labels)
            self.assertEqual(
                [
                    (REVISION_GROUP_3, REVISION_GROUP_1),
                    (REVISION_GROUP_2, REVISION_GROUP_1),
                ],
                series_order(top5_frame),
            )
            self.assertEqual("HTR - NTR", series_label((REVISION_GROUP_3, REVISION_GROUP_1)))

    def test_size_control_main_writes_aggregate_and_plot(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = self.create_experiment(tmpdir)
            output_dir = output_directory(experiment_dir, "nc", "historyFinder", "jnose")
            output_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.generated_row("demo", "test://h-small", "prod://1", 10, 1, "AR VT", REVISION_GROUP_3),
                    self.generated_row("demo", "test://h-medium", "prod://2", 10, 1, "AR EH", REVISION_GROUP_3),
                    self.generated_row("demo", "test://h-large", "prod://3", 10, 1, "AR DA", REVISION_GROUP_3),
                    self.generated_row("demo", "test://m-small", "prod://4", 5, 1, "VT", REVISION_GROUP_2),
                    self.generated_row("demo", "test://m-medium", "prod://5", 5, 1, "AR", REVISION_GROUP_2),
                    self.generated_row("demo", "test://m-large", "prod://6", 5, 1, "MN", REVISION_GROUP_2),
                    self.generated_row("demo", "test://n-small", "prod://7", 1, 5, "", REVISION_GROUP_1),
                    self.generated_row("demo", "test://n-medium", "prod://8", 1, 5, "VT", REVISION_GROUP_1),
                    self.generated_row("demo", "test://n-large", "prod://9", 1, 5, "", REVISION_GROUP_1),
                ]
            ).to_csv(output_dir / "demo.csv", index=False)
            self.write_smells(
                experiment_dir,
                "demo",
                [
                    {"url": "test://h-small", "smell": "AR", "loc": 29},
                    {"url": "test://m-small", "smell": "VT", "loc": 20},
                    {"url": "test://n-small", "smell": "", "loc": 10},
                    {"url": "test://h-medium", "smell": "AR", "loc": 30},
                    {"url": "test://m-medium", "smell": "AR", "loc": 45},
                    {"url": "test://n-medium", "smell": "VT", "loc": 60},
                    {"url": "test://h-large", "smell": "AR", "loc": 61},
                    {"url": "test://m-large", "smell": "MN", "loc": 80},
                    {"url": "test://n-large", "smell": "", "loc": 100},
                ],
            )
            (experiment_dir / "aggregate").mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    self.association_output_row("AR", 16.5, REVISION_GROUP_3, REVISION_GROUP_1),
                    self.association_output_row("VT", 11.9, REVISION_GROUP_3, REVISION_GROUP_1),
                    self.association_output_row("MNT", 8.4, REVISION_GROUP_3, REVISION_GROUP_1),
                    self.association_output_row("CTL", 5.5, REVISION_GROUP_3, REVISION_GROUP_1),
                    self.association_output_row("EH", 5.4, REVISION_GROUP_3, REVISION_GROUP_1),
                    self.association_output_row("DA", 4.8, REVISION_GROUP_3, REVISION_GROUP_1),
                ]
            ).to_csv(experiment_dir / "aggregate" / "t2p-test-smell-association.csv", index=False)

            plot_args = [
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
            generator_args = [*plot_args, "--projects", "demo"]
            size_control_association_main([*generator_args, "--min-t2p-links", "0", "--replace"])
            size_control_effectplot_main(plot_args)

            self.assertTrue((experiment_dir / "aggregate" / "t2p-test-smell-size-control-association.csv").exists())
            output_df = pd.read_csv(experiment_dir / "aggregate" / "t2p-test-smell-size-control-association.csv")
            self.assertEqual(36, len(output_df))
            self.assertEqual({"AR", "VT", "MNT", "CTL", "EH", COMBINED_TOP_SMELLS}, set(output_df["smell"]))
            self.assertTrue(
                (
                    experiment_dir
                    / "figure"
                    / "t2p-test-smell-size-control-effectplot--historyFinder--nc--jnose--ch_diff.pdf"
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
        *,
        focal_group: str = REVISION_GROUP_3,
        baseline_group: str = REVISION_GROUP_1,
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
            "baseline_group": baseline_group,
            "focal_group": focal_group,
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

    def association_output_row(
        self,
        smell: str,
        difference_pp: float,
        focal_group: str,
        baseline_group: str,
    ) -> dict:
        row = self.association_row(smell, 1, 10, 1, 10, "", focal_group=focal_group, baseline_group=baseline_group)
        row["difference_pp"] = difference_pp
        return row

    def size_control_row(
        self,
        control_group: str,
        smell: str,
        focal_group: str,
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
            "control_group": control_group,
            "control_group_label": f"{control_group} LOC",
            "baseline_group": REVISION_GROUP_1,
            "focal_group": focal_group,
            "smell": smell,
            "smell_rank": {"AR": 1, "VT": 2}.get(smell, 3),
            "baseline_n": baseline_n,
            "baseline_smell_n": baseline_smell_n,
            "baseline_percent": baseline_percent,
            "focal_n": focal_n,
            "focal_smell_n": focal_smell_n,
            "focal_percent": focal_percent,
            "difference_pp": difference,
            "difference_ci_low": difference - 5,
            "difference_ci_high": difference + 5,
            "fisher_p": 0.01,
            "fisher_p_adjusted": 0.02,
            "significant": significant,
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
            "groups": "HTR,NTR",
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
