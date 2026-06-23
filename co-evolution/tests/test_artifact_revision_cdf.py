from pathlib import Path
import sys
import tempfile
import unittest
import warnings

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
for directory in (SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(directory) not in sys.path:
        sys.path.insert(0, str(directory))

from ptc.plot.artifact_revision_cdf import (
    DEFAULT_CHANGE_AXIS_WIDTH,
    DEFAULT_TICK_FONT_SIZE,
    METHOD_KIND_MARKERS,
    PAPER_AXIS_LABEL_FONT_SIZE,
    PAPER_CHANGE_AXIS_WIDTH,
    PAPER_LEGEND_ANCHOR,
    PAPER_MARK_EVERY,
    PAPER_MARKER_SIZE,
    PAPER_TICK_FONT_SIZE,
    build_project_stats,
    classify_method_kind,
    main,
    paper_marker_positions,
    plot_change_axis,
    revision_display_positions,
    revision_tick_values,
    subsequent_revision_series,
    y_values_at_marker_positions,
)
import ptc.generator.artifact_revision as artifact_revision_generator
from ptc.generator.filter_artifact import main as filter_artifact_main
from ptc.util.helper import (
    filter_revision_method_base_population,
    filter_revision_method_population,
    join_method_code,
    load_method_code_df,
)


class TestArtifactRevisionCdf(unittest.TestCase):
    def test_raw_artifact_revision_generator_does_not_load_method_code(self):
        self.assertFalse(hasattr(artifact_revision_generator, "load_method_code_df"))
        self.assertFalse(hasattr(artifact_revision_generator, "method_code_file"))

    def test_method_code_loader_does_not_import_artifact_column(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = Path(tmpdir) / "experiment" / "demo"
            code_file = experiment_dir / "method-code" / "projectA.csv"
            code_file.parent.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "project": "projectA",
                        "name": "getName",
                        "url": "https://example.test/projectA/Foo.java#L1",
                        "artifact": "#test-code #test-case-method",
                        "start_line": 1,
                        "end_line": 3,
                        "code": "public String getName() {\n  return name;\n}",
                    }
                ]
            ).to_csv(code_file, index=False)

            method_code_df = load_method_code_df(experiment_dir, "projectA")

            self.assertEqual(["url", "code"], method_code_df.columns.tolist())

    def test_join_method_code_drops_missing_code_after_base_population_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = Path(tmpdir) / "experiment" / "demo"
            df = pd.DataFrame(
                [
                    {
                        "project": "projectA",
                        "name": "abstractMain",
                        "url": "https://example.test/projectA/Foo.java#L1",
                        "artifact": "#main-code",
                        "abstract": 1,
                        "ch_diff": 99,
                    },
                    {
                        "project": "projectA",
                        "name": "missingMain",
                        "url": "https://example.test/projectA/Foo.java#L10",
                        "artifact": "#main-code",
                        "abstract": 0,
                        "ch_diff": 4,
                    },
                    {
                        "project": "projectA",
                        "name": "validTest",
                        "url": "https://example.test/projectA/FooTest.java#L1",
                        "artifact": "#test-code #test-case-method",
                        "abstract": 0,
                        "ch_diff": 3,
                    },
                ]
            )
            code_file = experiment_dir / "method-code" / "projectA.csv"
            code_file.parent.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "url": "https://example.test/projectA/Foo.java#L1",
                        "code": "",
                    },
                    {
                        "url": "https://example.test/projectA/Foo.java#L10",
                        "code": "",
                    },
                    {
                        "url": "https://example.test/projectA/FooTest.java#L1",
                        "code": "public void validTest() { assertTrue(true); }",
                    },
                ]
            ).to_csv(code_file, index=False)

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                base_df = filter_revision_method_base_population(df)
                joined_df = join_method_code(base_df, experiment_dir)

            self.assertEqual(["validTest"], joined_df["name"].tolist())
            self.assertEqual(
                ["Dropping 1 method-history rows with missing method code in project=projectA."],
                [str(warning.message) for warning in caught_warnings],
            )

    def test_abstract_methods_are_excluded_from_cdf_population_and_counts(self):
        df = pd.DataFrame(
            [
                {"name": "concrete-main", "artifact": "#main-code", "abstract": 0, "ch_diff": 2},
                {"name": "abstract-main", "artifact": "#main-code", "abstract": 1, "ch_diff": 99},
                {"name": "concrete-test", "artifact": "#test-code #test-case-method", "abstract": 0, "ch_diff": 3},
                {"name": "concrete-helper", "artifact": "#test-code #test-helper-method", "abstract": 0, "ch_diff": 4},
                {"name": "abstract-test", "artifact": "#test-code #test-case-method", "abstract": 1, "ch_diff": 98},
                {"name": "invalid-test", "artifact": "#test-code #test-case-method", "abstract": "", "ch_diff": 97},
            ]
        )

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            method_df = filter_revision_method_population(df)

        self.assertEqual(["concrete-main", "concrete-test"], method_df["name"].tolist())
        self.assertEqual({"total": 2, "test": 1, "production": 1}, build_project_stats(method_df))
        self.assertEqual([2, 3], method_df["ch_diff"].tolist())
        self.assertEqual(
            ["project=<unknown>: 1 invalid abstract values out of 6 methods."],
            [str(warning.message) for warning in caught_warnings],
        )

    def test_filter_artifact_writes_filtered_rows_without_code_then_cdf_plots(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = Path(tmpdir) / "experiment" / "demo"
            self.write_project_file(experiment_dir, ["projectA"])
            history_file = experiment_dir / "method-history" / "historyFinder" / "projectA.csv"
            history_file.parent.mkdir(parents=True)
            method_rows = [
                {
                    "project": "projectA",
                    "name": "mainMethod",
                    "url": "https://example.test/projectA/Foo.java#L1",
                    "artifact": "#main-code",
                    "abstract": 0,
                    "ch_diff": 2,
                },
                {
                    "project": "projectA",
                    "name": "testMethod",
                    "url": "https://example.test/projectA/FooTest.java#L1",
                    "artifact": "#test-code #test-case-method",
                    "abstract": 0,
                    "ch_diff": 3,
                },
                {
                    "project": "projectA",
                    "name": "helper",
                    "url": "https://example.test/projectA/FooTest.java#L8",
                    "artifact": "#test-code #test-helper-method",
                    "abstract": 0,
                    "ch_diff": 4,
                },
                {
                    "project": "projectA",
                    "name": "invalid",
                    "url": "https://example.test/projectA/Foo.java#L8",
                    "artifact": "#main-code",
                    "abstract": "",
                    "ch_diff": 99,
                },
            ]
            (experiment_dir / "method").mkdir(parents=True, exist_ok=True)
            pd.DataFrame(method_rows).to_csv(experiment_dir / "method" / "projectA.csv", index=False)
            pd.DataFrame(
                [
                    {**row, "ch_all": row["ch_diff"]}
                    for row in method_rows
                ]
            ).to_csv(history_file, index=False)
            self.write_method_code_for_rows(experiment_dir, "projectA", method_rows)

            with warnings.catch_warnings(record=True) as caught_warnings:
                warnings.simplefilter("always")
                filter_artifact_main(
                    [
                        "--workspace-directory",
                        tmpdir,
                        "--experiment-name",
                        "demo",
                    ]
                )
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

            filtered_file = experiment_dir / "method-artifact-filtered" / "projectA.csv"
            filtered_df = pd.read_csv(filtered_file, keep_default_na=False, na_filter=False)
            self.assertEqual(["mainMethod", "testMethod"], filtered_df["name"].tolist())
            self.assertIn("method_kind", filtered_df.columns)
            self.assertNotIn("code", filtered_df.columns)
            self.assertTrue(
                (experiment_dir / "figure" / "artifact-revision-cdf--historyFinder.pdf").exists()
            )
            self.assertIn(
                "project=projectA: 1 invalid abstract values out of 4 methods.",
                [str(warning.message) for warning in caught_warnings],
            )

    def test_all_projects_only_writes_paper_plot_to_output_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            experiment_dir = Path(tmpdir) / "experiment" / "demo"
            self.write_history_file(
                experiment_dir,
                "historyFinder",
                "projectA",
                [
                    {"artifact": "#main-code", "abstract": 0, "ch_all": 20, "ch_diff": 12},
                    {"artifact": "#test-code #test-case-method", "abstract": 0, "ch_all": 4, "ch_diff": 2},
                    {"artifact": "#test-code #test-helper-method", "abstract": 0, "ch_all": 30, "ch_diff": 30},
                ],
            )
            self.write_history_file(
                experiment_dir,
                "historyFinder",
                "projectB",
                [
                    {"artifact": "#main-code", "abstract": 0, "ch_all": 1, "ch_diff": 1},
                    {"artifact": "#test-code #test-case-method", "abstract": 0, "ch_all": 2, "ch_diff": 15},
                ],
            )
            output_directory = Path(tmpdir) / "paper-figure"

            main(
                [
                    "--workspace-directory",
                    tmpdir,
                    "--experiment-name",
                    "demo",
                    "--tools",
                    "historyFinder",
                    "--revision-types",
                    "ch_diff",
                    "--all-projects-only",
                    "--output-directory",
                    str(output_directory),
                ]
            )

            self.assertTrue((output_directory / "artifact-revision-cdf--historyFinder.pdf").exists())
            self.assertFalse((experiment_dir / "figure" / "artifact-revision-cdf--historyFinder.pdf").exists())

    def test_paper_plot_axis_labels_ticks_legend_and_title(self):
        df = pd.DataFrame(
            [
                {"method_kind": "main-code", "ch_diff": 0},
                {"method_kind": "main-code", "ch_diff": 1},
                {"method_kind": "main-code", "ch_diff": 101},
                {"method_kind": "test-case-method", "ch_diff": 1},
                {"method_kind": "test-case-method", "ch_diff": 2},
                {"method_kind": "test-case-method", "ch_diff": 16},
            ]
        )
        fig, ax = plt.subplots()
        try:
            plot_change_axis(ax, df, "ch_diff", 0, paper_mode=True)

            self.assertEqual("", ax.get_title())
            self.assertEqual("# Method Revisions", ax.get_xlabel())
            self.assertEqual("CDF", ax.get_ylabel())
            self.assertEqual("linear", ax.get_xscale())
            tick_labels = [tick.get_text() for tick in ax.get_xticklabels()]
            self.assertEqual(["0", "1", "2", "5", "10", "20", "50"], tick_labels)
            self.assertNotIn("10+", tick_labels)
            self.assertEqual("0", ax.get_xticklabels()[0].get_text())
            self.assertEqual(list(range(len(tick_labels))), ax.get_xticks().tolist())
            self.assertEqual(PAPER_AXIS_LABEL_FONT_SIZE, ax.xaxis.label.get_fontsize())
            self.assertEqual(PAPER_AXIS_LABEL_FONT_SIZE, ax.yaxis.label.get_fontsize())
            self.assertEqual([round(value, 1) for value in ax.get_yticks().tolist()], [round(value / 10, 1) for value in range(11)])
            self.assertTrue(
                all(tick.get_fontsize() == PAPER_TICK_FONT_SIZE for tick in ax.get_xticklabels())
            )
            self.assertTrue(
                all(tick.get_fontsize() == PAPER_TICK_FONT_SIZE for tick in ax.get_yticklabels())
            )
            legend = ax.get_legend()
            self.assertIsNotNone(legend)
            self.assertEqual(
                ["Test Method", "Production Method"],
                [text.get_text() for text in legend.get_texts()],
            )
            self.assertEqual([0, 1, 4.5], ax.lines[0].get_xdata().tolist())
            self.assertEqual([0, 6], ax.lines[2].get_xdata().tolist())
            self.assertEqual("None", ax.lines[0].get_marker())
            self.assertEqual("None", ax.lines[2].get_marker())
            self.assertEqual([0, 2, 4, 6], ax.lines[1].get_xdata().tolist())
            self.assertEqual([0.5, 2.5, 4.5], ax.lines[3].get_xdata().tolist())
            self.assertEqual(METHOD_KIND_MARKERS["test-case-method"], ax.lines[1].get_marker())
            self.assertEqual(METHOD_KIND_MARKERS["main-code"], ax.lines[3].get_marker())
            self.assertEqual(PAPER_MARKER_SIZE, ax.lines[1].get_markersize())
            self.assertEqual(PAPER_MARKER_SIZE, ax.lines[3].get_markersize())
            self.assertEqual((0.0, 6.0), ax.get_xlim())
            self.assertEqual(PAPER_LEGEND_ANCHOR, legend.get_bbox_to_anchor()._bbox.bounds[:2])
        finally:
            plt.close(fig)

    def test_default_plot_uses_sparse_ticks_without_clipping(self):
        df = pd.DataFrame(
            [
                {"method_kind": "main-code", "ch_diff": 1},
                {"method_kind": "main-code", "ch_diff": 52},
                {"method_kind": "test-case-method", "ch_diff": 2},
                {"method_kind": "test-case-method", "ch_diff": 101},
            ]
        )
        fig, ax = plt.subplots()
        try:
            plot_change_axis(ax, df, "ch_diff", 0, paper_mode=False)

            self.assertEqual("ch_diff", ax.get_title())
            self.assertEqual("linear", ax.get_xscale())
            tick_labels = [tick.get_text() for tick in ax.get_xticklabels()]
            self.assertEqual(["0", "1", "2", "5", "10", "20", "50", "100"], tick_labels)
            self.assertNotIn("10+", tick_labels)
            self.assertEqual("0", ax.get_xticklabels()[0].get_text())
            self.assertEqual(list(range(len(tick_labels))), ax.get_xticks().tolist())
            self.assertTrue(
                all(tick.get_fontsize() == DEFAULT_TICK_FONT_SIZE for tick in ax.get_xticklabels())
            )
            self.assertTrue(
                all(tick.get_fontsize() == DEFAULT_TICK_FONT_SIZE for tick in ax.get_yticklabels())
            )
            self.assertEqual((0.0, 7.0), ax.get_xlim())
            self.assertEqual([1, 7], ax.lines[0].get_xdata().tolist())
            self.assertEqual([0, 6.02], ax.lines[1].get_xdata().tolist())
            self.assertEqual("None", ax.lines[0].get_marker())
            self.assertEqual("None", ax.lines[1].get_marker())
        finally:
            plt.close(fig)

    def test_revision_tick_values_are_sparse(self):
        self.assertEqual([0], revision_tick_values(0))
        self.assertEqual([0, 1, 2, 5, 10], revision_tick_values(9))
        self.assertEqual([0, 1, 2, 5, 10], revision_tick_values(10))
        self.assertEqual([0, 1, 2, 5, 10, 20, 50, 100, 200], revision_tick_values(101))

    def test_revision_display_positions_are_equally_spaced_at_ticks(self):
        ticks = [0, 1, 2, 5, 10, 20, 50, 100]

        self.assertEqual(
            list(range(len(ticks))),
            revision_display_positions(ticks, ticks).tolist(),
        )
        self.assertEqual(
            [4.5, 6.02],
            revision_display_positions([15, 51], ticks).round(2).tolist(),
        )

    def test_paper_marker_positions_are_based_on_x_ticks(self):
        ticks = [0, 1, 2, 5, 10, 20, 50]

        self.assertEqual([0, 2, 4, 6], paper_marker_positions(ticks, "test-case-method"))
        self.assertEqual([0.5, 2.5, 4.5], paper_marker_positions(ticks, "main-code"))

    def test_y_values_at_marker_positions_use_cdf_value_at_or_before_marker(self):
        self.assertEqual(
            [0.2, 0.6, 1.0],
            y_values_at_marker_positions(
                [0.5, 2.5, 6],
                [0, 2, 4, 6],
                [0.2, 0.6, 0.8, 1.0],
            ).tolist(),
        )

    def test_artifact_revision_cdf_figure_widths_are_increased(self):
        self.assertEqual(4.6, PAPER_CHANGE_AXIS_WIDTH)
        self.assertEqual(5.5, DEFAULT_CHANGE_AXIS_WIDTH)

    def test_subsequent_revision_series_excludes_introduction(self):
        series = pd.Series([0, 1, 2, 11])

        self.assertEqual([0, 0, 1, 10], subsequent_revision_series(series).tolist())

    def test_rq3_population_uses_test_case_methods_and_filters_trivial_production_only(self):
        df = pd.DataFrame(
            [
                {
                    "name": "getName",
                    "artifact": "#main-code",
                    "abstract": 0,
                    "start_line": 1,
                    "end_line": 3,
                    "code": "public String getName() {\n  return name;\n}",
                },
                {
                    "name": "setName",
                    "artifact": "#main-code",
                    "abstract": 0,
                    "start_line": 4,
                    "end_line": 6,
                    "code": "public void setName(String name) {\n  this.name = name;\n}",
                },
                {
                    "name": "isReady",
                    "artifact": "#main-code",
                    "abstract": 0,
                    "start_line": 7,
                    "end_line": 7,
                    "code": "boolean isReady();",
                },
                {
                    "name": "calculate",
                    "artifact": "#main-code",
                    "abstract": 0,
                    "start_line": 8,
                    "end_line": 14,
                    "code": "public int calculate() {\n  int x = 1;\n  int y = 2;\n  int z = 3;\n  return x + y + z;\n}",
                },
                {
                    "name": "testGetName",
                    "artifact": "#test-code #test-case-method",
                    "abstract": 0,
                    "start_line": 15,
                    "end_line": 17,
                    "code": "public void testGetName() {\n  assertEquals(\"x\", name);\n}",
                },
                {
                    "name": "helper",
                    "artifact": "#test-code #test-helper-method",
                    "abstract": 0,
                    "start_line": 18,
                    "end_line": 20,
                    "code": "private String helper() {\n  return \"x\";\n}",
                },
            ]
        )

        method_df = filter_revision_method_population(df)

        self.assertEqual(["calculate", "testGetName"], method_df["name"].tolist())
        self.assertEqual(["main-code", "test-case-method"], method_df["method_kind"].tolist())

    def write_history_file(
        self,
        experiment_dir: Path,
        tool: str,
        project: str,
        rows: list[dict],
    ) -> None:
        history_file = experiment_dir / "method-history" / tool / f"{project}.csv"
        history_file.parent.mkdir(parents=True, exist_ok=True)
        history_rows = [
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
        pd.DataFrame(history_rows).to_csv(history_file, index=False)
        filtered_file = experiment_dir / "method-artifact-filtered" / f"{project}.csv"
        filtered_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(
            [
                {
                    "project": row["project"],
                    "name": row["name"],
                    "url": row["url"],
                    "artifact": row["artifact"],
                    "abstract": row["abstract"],
                    "method_kind": classify_method_kind(row["artifact"]),
                }
                for row in history_rows
                if classify_method_kind(row["artifact"]) in {"test-case-method", "main-code"}
            ]
        ).to_csv(filtered_file, index=False)

    def write_method_code_for_rows(self, experiment_dir: Path, project: str, rows: list[dict]) -> None:
        method_code_file = experiment_dir / "method-code" / f"{project}.csv"
        method_code_file.parent.mkdir(parents=True, exist_ok=True)
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
        ).to_csv(method_code_file, index=False)

    def write_project_file(self, experiment_dir: Path, projects: list[str]) -> None:
        project_file = experiment_dir / "project.csv"
        project_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"project": project} for project in projects]).to_csv(project_file, index=False)


if __name__ == "__main__":
    unittest.main()
