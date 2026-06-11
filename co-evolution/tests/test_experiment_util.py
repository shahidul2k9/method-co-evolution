from pathlib import Path
import sys
import unittest
from unittest import mock
import warnings

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
if str(MHC_SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(MHC_SRC_DIRECTORY))
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc import config
from mhc.command_util import (
    artifact_matches,
    build_experiment_parser,
    filter_artifact_dataframe,
    resolve_experiment_filters,
    select_named_items,
    select_revision_columns,
)
from ptc.util.helper import filter_concrete_methods


class TestExperimentParser(unittest.TestCase):
    def test_replace_option_defaults_to_false_when_included(self):
        parser = build_experiment_parser(
            "demo",
            include_replace=True,
        )

        args = parser.parse_args([])

        self.assertFalse(args.replace)

    def test_replace_option_parses_true(self):
        parser = build_experiment_parser(
            "demo",
            include_replace=True,
        )

        args = parser.parse_args(["--replace"])

        self.assertTrue(args.replace)

    def test_no_replace_option_parses_false(self):
        parser = build_experiment_parser(
            "demo",
            include_replace=True,
        )

        args = parser.parse_args(["--no-replace"])

        self.assertFalse(args.replace)

    def test_replace_option_is_absent_by_default(self):
        parser = build_experiment_parser("demo")

        args = parser.parse_args([])

        self.assertFalse(hasattr(args, "replace"))

    def test_project_directory_option_uses_shared_default_when_included(self):
        parser = build_experiment_parser(
            "demo",
            include_project_directory=True,
        )

        args = parser.parse_args([])

        self.assertEqual(config.PROJECT_DIRECTORY, args.project_directory)

    def test_output_directory_option_is_available_when_included(self):
        parser = build_experiment_parser(
            "demo",
            include_output_directory=True,
        )

        args = parser.parse_args(["--output-directory", "paper/figure"])

        self.assertEqual("paper/figure", args.output_directory)

    def test_replace_default_false_can_come_from_env(self):
        with mock.patch.dict("os.environ", {"ME_REPLACE": "false"}):
            parser = build_experiment_parser("demo", include_replace=True)

        args = parser.parse_args([])

        self.assertFalse(args.replace)

    def test_replace_default_true_can_come_from_env(self):
        with mock.patch.dict("os.environ", {"ME_REPLACE": "true"}):
            parser = build_experiment_parser("demo", include_replace=True)

        args = parser.parse_args([])

        self.assertTrue(args.replace)

    def test_filters_resolve_from_new_env_defaults(self):
        with mock.patch.dict(
            "os.environ",
            {
                "ME_TOOLS": "tool-a,tool-b",
                "ME_PROJECTS": ":",
                "ME_STRATEGIES": "strategy-a",
            },
        ):
            selected_tools, selected_projects, selected_strategies = resolve_experiment_filters()

        self.assertEqual(["tool-a", "tool-b"], selected_tools)
        self.assertIsNone(selected_projects)
        self.assertEqual(["strategy-a"], selected_strategies)

    def test_project_index_filters_original_project_order(self):
        with mock.patch.dict("os.environ", {"ME_PROJECT_INDEX": "1:4"}):
            projects = select_named_items(
                ["project-a", "project-b", "project-c", "project-d", "project-e"],
                item_label="project",
            )

        self.assertEqual(["project-b", "project-c", "project-d"], projects)

    def test_project_names_and_index_are_intersected(self):
        with mock.patch.dict("os.environ", {"ME_PROJECT_INDEX": "1:4"}):
            projects = select_named_items(
                ["project-a", "project-b", "project-c", "project-d", "project-e"],
                "project-a,project-c,project-e",
                item_label="project",
            )

        self.assertEqual(["project-c"], projects)

    def test_artifact_filter_matches_any_tag(self):
        self.assertTrue(artifact_matches("#test-code #test-case-method", "main-code,test-code"))
        self.assertFalse(artifact_matches("#test-resource", "main-code,test-code"))

    def test_artifact_dataframe_filter_uses_env_default(self):
        df = pd.DataFrame(
            [
                {"artifact": "#main-code", "url": "main"},
                {"artifact": "#test-resource", "url": "resource"},
            ]
        )

        with mock.patch.dict("os.environ", {"ME_ARTIFACTS": "main-code"}):
            filtered_df = filter_artifact_dataframe(df)

        self.assertEqual(["main"], filtered_df["url"].tolist())

    def test_revision_columns_use_configured_order(self):
        with mock.patch.dict("os.environ", {"ME_REVISION_TYPES": "ch_diff,ch_all"}):
            columns = select_revision_columns(
                ["ch_all", "ch_body", "ch_diff"],
                preferred_order=["ch_all", "ch_diff", "ch_body"],
            )

        self.assertEqual(["ch_all", "ch_diff"], columns)

    def test_concrete_method_filter_keeps_only_binary_zero_values(self):
        df = pd.DataFrame(
            [
                {"name": "integer-concrete", "abstract": 0},
                {"name": "string-concrete", "abstract": "0"},
                {"name": "integer-abstract", "abstract": 1},
                {"name": "string-abstract", "abstract": "1"},
            ]
        )

        filtered_df = filter_concrete_methods(df)

        self.assertEqual(
            ["integer-concrete", "string-concrete"],
            filtered_df["name"].tolist(),
        )

    def test_concrete_method_filter_warns_per_project_and_drops_invalid_values(self):
        df = pd.DataFrame(
            [
                {"project": "first", "name": "valid", "abstract": 0},
                {"project": "first", "name": "blank", "abstract": ""},
                {"project": "first", "name": "non-binary", "abstract": 2},
                {"project": "second", "name": "text", "abstract": "abstract"},
                {"project": "second", "name": "abstract", "abstract": 1},
            ]
        )

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            filtered_df = filter_concrete_methods(df)

        self.assertEqual(["valid"], filtered_df["name"].tolist())
        warning_messages = [str(warning.message) for warning in caught_warnings]
        self.assertIn("project=first: 2 invalid abstract values out of 3 methods.", warning_messages)
        self.assertIn("project=second: 1 invalid abstract values out of 2 methods.", warning_messages)

    def test_concrete_method_filter_warns_and_returns_empty_when_abstract_column_is_missing(self):
        df = pd.DataFrame(
            [
                {"project": "first", "name": "method1"},
                {"project": "first", "name": "method2"},
                {"project": "second", "name": "method3"},
            ]
        )

        with warnings.catch_warnings(record=True) as caught_warnings:
            warnings.simplefilter("always")
            filtered_df = filter_concrete_methods(df)

        self.assertTrue(filtered_df.empty)
        warning_messages = [str(warning.message) for warning in caught_warnings]
        self.assertIn("project=first: 2 invalid abstract values out of 2 methods.", warning_messages)
        self.assertIn("project=second: 1 invalid abstract values out of 1 methods.", warning_messages)


if __name__ == "__main__":
    unittest.main()
