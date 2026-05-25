from pathlib import Path
import sys
import unittest
from unittest import mock

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
MHC_SRC_DIRECTORY = Path(__file__).resolve().parents[2] / "method-history-collector" / "src"
if str(MHC_SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(MHC_SRC_DIRECTORY))
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.command_util import (
    artifact_matches,
    build_experiment_parser,
    filter_artifact_dataframe,
    resolve_experiment_filters,
    select_named_items,
    select_revision_columns,
)


class TestExperimentParser(unittest.TestCase):
    def test_replace_option_defaults_to_true_when_included(self):
        parser = build_experiment_parser(
            "demo",
            include_replace=True,
        )

        args = parser.parse_args([])

        self.assertTrue(args.replace)

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

    def test_replace_default_can_come_from_env(self):
        with mock.patch.dict("os.environ", {"ME_REPLACE": "false"}):
            parser = build_experiment_parser("demo", include_replace=True)

        args = parser.parse_args([])

        self.assertFalse(args.replace)

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


if __name__ == "__main__":
    unittest.main()
