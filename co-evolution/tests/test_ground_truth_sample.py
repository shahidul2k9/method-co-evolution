from pathlib import Path
import re
import sys
import tempfile
import unittest
from unittest import mock

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

from mhc.command_util import select_project_items
from ptc.sample import sample_t2p_ground_truth as ground_truth_sample


@unittest.skipIf(pd is None, "pandas is required for ground truth sample tests")
class TestGroundTruthSample(unittest.TestCase):
    def test_project_index_selects_repository_rows(self):
        projects = ["commons-io", "commons-lang", "gson"]

        self.assertEqual(["commons-lang"], select_project_items(projects, project_index="1"))
        self.assertEqual(["commons-lang", "gson"], select_project_items(projects, project_index="1:"))
        self.assertEqual(["commons-io", "commons-lang"], select_project_items(projects, project_index=":2"))
        self.assertEqual(["gson"], select_project_items(projects, project_index="-1"))
        self.assertEqual(projects, select_project_items(projects, project_index=None))

    def test_project_index_accepts_comma_separated_indexes(self):
        projects = ["commons-io", "commons-lang", "gson", "junit4"]

        self.assertEqual(
            ["commons-io", "gson", "junit4"],
            select_project_items(projects, project_index="0,2,-1"),
        )

    def test_parse_update_columns_accepts_comma_separated_values(self):
        self.assertEqual(
            ["from_artifact", "to_artifact", "to_name", "to_fqs", "candidate"],
            ground_truth_sample.parse_update_columns("from_artifact,to_artifact, to_name,to_fqs,to_name,candidate"),
        )

    def test_parse_update_columns_rejects_unknown_and_protected_columns(self):
        with self.assertRaisesRegex(ValueError, "unknown update column"):
            ground_truth_sample.parse_update_columns("to_artifact,missing_column")
        with self.assertRaisesRegex(ValueError, "protected update column"):
            ground_truth_sample.parse_update_columns("to_artifact,label")

    def test_regenerate_preserves_labels_and_fills_sample_from_fresh_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=3)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_name": "testA",
                        "to_name": "prod1",
                        "from_url": "test://A",
                        "to_url": "prod://1",
                        "label": "1",
                        "tags": "needs-check",
                        "notes": "keep this",
                    }
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=2,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                random_state=42,
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertIsNotNone(stats)
            self.assertEqual(1, stats.reused_test_methods)
            self.assertEqual(1, stats.added_test_methods)
            self.assertEqual(2, result["from_url"].nunique())
            preserved = result[(result["from_url"] == "test://A") & (result["to_url"] == "prod://1")].iloc[0]
            self.assertEqual("#test-code #test-case-method", preserved["from_artifact"])
            self.assertEqual("1", str(preserved["candidate"]))
            self.assertEqual("1", str(preserved["label"]))
            self.assertEqual("needs-check", preserved["tags"])
            self.assertEqual("keep this", preserved["notes"])

    def test_add_only_preserves_existing_rows_and_fills_remaining_test_methods(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=3)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_name": "staleTestA",
                        "to_name": "staleProd",
                        "from_url": "test://A",
                        "to_url": "prod://1",
                        "from_fqs": "stale.from()",
                        "from_tctracer_fqs": "stale.from()",
                        "from_testlinker_fqs": "stale.from.linker()",
                        "to_fqs": "stale.to()",
                        "to_tctracer_fqs": "stale.to()",
                        "to_testlinker_fqs": "stale.to.linker()",
                        "from_artifact": "stale-from-artifact",
                        "to_artifact": "stale-to-artifact",
                        "to_call_depth": "99",
                        "candidate": "0",
                        "label": "1",
                        "tags": "reviewed",
                        "notes": "preserve all values",
                    }
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=2,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                random_state=42,
                add_only=True,
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            preserved = result.iloc[0]
            self.assertEqual(1, stats.reused_test_methods)
            self.assertEqual(1, stats.added_test_methods)
            self.assertEqual(2, result["from_url"].nunique())
            self.assertEqual("staleTestA", preserved["from_name"])
            self.assertEqual("stale.from.linker()", preserved["from_testlinker_fqs"])
            self.assertEqual("stale.to.linker()", preserved["to_testlinker_fqs"])
            self.assertEqual("stale-from-artifact", preserved["from_artifact"])
            self.assertEqual("stale-to-artifact", preserved["to_artifact"])
            self.assertEqual("99", str(preserved["to_call_depth"]))
            self.assertEqual("0", str(preserved["candidate"]))
            self.assertEqual("1", str(preserved["label"]))
            appended = result[result["from_url"] != "test://A"]
            self.assertFalse(appended.empty)
            self.assertEqual({"1"}, set(appended["candidate"].astype(str)))

    def test_add_only_with_enough_existing_methods_appends_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=3)
            working_rows = [
                {
                    "project": "demo",
                    "from_name": f"existing{index}",
                    "to_name": "prod1",
                    "from_url": f"test://{chr(ord('A') + index)}",
                    "to_url": "prod://1",
                    "from_testlinker_fqs": f"stale.from.{index}()",
                    "to_testlinker_fqs": f"stale.to.{index}()",
                    "candidate": "0",
                    "label": str(index % 2),
                }
                for index in range(3)
            ]
            pd.DataFrame(working_rows).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=2,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                add_only=True,
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(3, stats.reused_test_methods)
            self.assertEqual(0, stats.added_test_methods)
            self.assertEqual(3, len(result))
            self.assertEqual(["existing0", "existing1", "existing2"], result["from_name"].tolist())
            self.assertEqual(["stale.from.0()", "stale.from.1()", "stale.from.2()"], result["from_testlinker_fqs"].tolist())
            self.assertEqual(["0", "0", "0"], result["candidate"].astype(str).tolist())

    def test_update_columns_keeps_fresh_values_for_callgraph_backed_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=1)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_name": "testA",
                        "to_name": "staleProd",
                        "from_url": "test://A",
                        "to_url": "prod://1",
                        "from_artifact": "stale-from-artifact",
                        "to_artifact": "stale-artifact",
                        "label": "1",
                        "tags": "reviewed",
                        "notes": "keep these",
                    }
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=1,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                update_columns=["from_artifact", "to_artifact", "to_name"],
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            prod = result[(result["from_url"] == "test://A") & (result["to_url"] == "prod://1")].iloc[0]
            self.assertEqual(1, stats.rows_refreshed)
            self.assertEqual(0, stats.rows_not_refreshed)
            self.assertEqual("#test-code #test-case-method", prod["from_artifact"])
            self.assertEqual("#main-code", prod["to_artifact"])
            self.assertEqual("prod1", prod["to_name"])
            self.assertEqual("1", str(prod["label"]))
            self.assertEqual("reviewed", prod["tags"])
            self.assertEqual("keep these", prod["notes"])

    def test_regenerate_without_working_csv_samples_requested_count(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=3)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=2,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                random_state=42,
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(0, stats.reused_test_methods)
            self.assertEqual(2, stats.added_test_methods)
            self.assertEqual(2, result["from_url"].nunique())

    def test_regenerate_keeps_over_sample_existing_methods(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=3)
            pd.DataFrame(
                [
                    {"project": "demo", "from_url": "test://A", "to_url": "prod://1", "label": "1"},
                    {"project": "demo", "from_url": "test://B", "to_url": "prod://1", "label": "0"},
                    {"project": "demo", "from_url": "test://C", "to_url": "prod://1", "label": "1"},
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=2,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(3, stats.reused_test_methods)
            self.assertEqual(0, stats.added_test_methods)
            self.assertEqual(3, result["from_url"].nunique())

    def test_regenerate_overwrites_existing_output_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=1)
            (output_dir / "demo.csv").write_text("old,column\nstale,value\n", encoding="utf-8")

            self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=1,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(ground_truth_sample.GROUND_TRUTH_COLUMNS, result.columns.tolist())
            self.assertEqual(
                ground_truth_sample.GROUND_TRUTH_COLUMNS.index("to_call_depth") + 1,
                ground_truth_sample.GROUND_TRUTH_COLUMNS.index("candidate"),
            )
            self.assertEqual(["test://A"], result["from_url"].drop_duplicates().tolist())

    def test_zero_sample_count_preserves_existing_rows_and_updates_candidate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=2)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_url": "test://A",
                        "to_url": "prod://1",
                        "label": "1",
                    },
                    {
                        "project": "demo",
                        "from_url": "test://B",
                        "to_url": "prod://manual",
                        "label": "0",
                    },
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=0,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(2, stats.reused_test_methods)
            self.assertEqual(0, stats.added_test_methods)
            self.assertEqual(2, stats.generated_rows)
            self.assertEqual(ground_truth_sample.GROUND_TRUTH_COLUMNS, result.columns.tolist())
            candidate_values = dict(zip(result["to_url"], result["candidate"].astype(str)))
            self.assertEqual("1", candidate_values["prod://1"])
            self.assertEqual("0", candidate_values["prod://manual"])

    def test_update_columns_refreshes_to_call_depth_from_candidate_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=1)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_url": "test://A",
                        "to_url": "prod://1",
                        "to_call_depth": "",
                        "label": "1",
                    }
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=0,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                update_columns=["to_call_depth"],
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(1, stats.rows_refreshed)
            self.assertEqual("1", str(result.iloc[0]["to_call_depth"]))

    def test_zero_sample_count_without_option_does_not_add_missing_candidates(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=1)
            pd.DataFrame(
                [{"project": "demo", "from_url": "test://A", "to_url": "prod://1", "label": "1"}]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=0,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(1, len(result))
            self.assertEqual(0, stats.missing_candidate_rows_added)
            self.assertEqual({"prod://1"}, set(result["to_url"]))

    def test_add_missing_candidates_for_existing_working_from_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=2)
            pd.DataFrame(
                [{"project": "demo", "from_url": "test://A", "to_url": "prod://1", "label": "1"}]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=0,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                add_missing_candidates=True,
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(1, stats.missing_candidate_rows_added)
            self.assertEqual({"prod://1", "test-helper://1"}, set(result["to_url"]))
            added = result[result["to_url"] == "test-helper://1"].iloc[0]
            self.assertEqual("#test-code #test-case-method", added["from_artifact"])
            self.assertEqual("#test-code #test-helper-method", added["to_artifact"])
            self.assertEqual("1", str(added["candidate"]))
            self.assertEqual("", added["label"])
            self.assertNotIn("test://B", set(result["from_url"]))

    def test_add_missing_candidates_are_inserted_at_bottom_of_each_from_url_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=2)
            pd.DataFrame(
                [
                    {"project": "demo", "from_url": "test://A", "to_url": "prod://1", "label": "1"},
                    {"project": "demo", "from_url": "test://B", "to_url": "prod://1", "label": "1"},
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=0,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                add_missing_candidates=True,
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(2, stats.missing_candidate_rows_added)
            self.assertEqual(
                [
                    ("test://A", "prod://1"),
                    ("test://A", "test-helper://1"),
                    ("test://B", "prod://1"),
                    ("test://B", "test-helper://1"),
                ],
                list(zip(result["from_url"], result["to_url"])),
            )

    def test_add_missing_candidates_does_not_duplicate_existing_pair(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=1)
            pd.DataFrame(
                [
                    {"project": "demo", "from_url": "test://A", "to_url": "prod://1", "label": "1"},
                    {"project": "demo", "from_url": "test://A", "to_url": "test-helper://1", "label": "0"},
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=0,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                add_missing_candidates=True,
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(0, stats.missing_candidate_rows_added)
            self.assertEqual(2, len(result))
            self.assertEqual(2, result[["from_url", "to_url"]].drop_duplicates().shape[0])

    def test_zero_sample_count_preserves_working_row_with_blank_to_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=1)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_name": "testA",
                        "to_name": "values",
                        "from_url": "test://A",
                        "to_url": "",
                        "from_fqs": "DemoTest.testA()",
                        "to_fqs": "Demo.values()",
                        "from_artifact": "#test-code #test-case-method",
                        "label": "0",
                    }
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=0,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(1, stats.manual_rows_preserved)
            self.assertEqual(1, len(result))
            self.assertEqual("", result.iloc[0]["to_url"])
            self.assertEqual("0", str(result.iloc[0]["candidate"]))

    def test_zero_sample_count_preserves_working_rows_with_missing_urls(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=1)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_name": "missingFrom",
                        "to_name": "prod1",
                        "from_url": "",
                        "to_url": "prod://1",
                        "label": "1",
                    },
                    {
                        "project": "demo",
                        "from_name": "missingBoth",
                        "to_name": "unknown",
                        "from_url": "",
                        "to_url": "",
                        "label": "0",
                    },
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=0,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(2, stats.manual_rows_preserved)
            self.assertEqual(2, len(result))
            self.assertEqual({"missingFrom", "missingBoth"}, set(result["from_name"]))
            self.assertEqual({"0"}, set(result["candidate"].astype(str)))

    def test_working_row_with_unselected_from_url_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=2)
            pd.DataFrame(
                [
                    {"project": "demo", "from_url": "test://A", "to_url": "prod://1", "label": "1"},
                    {"project": "demo", "from_url": "manual://outside", "to_url": "prod://manual", "label": "0"},
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=1,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                random_state=42,
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(1, stats.manual_rows_preserved)
            self.assertIn("manual://outside", set(result["from_url"]))
            manual = result[result["from_url"] == "manual://outside"].iloc[0]
            self.assertEqual("0", str(manual["candidate"]))

    def test_zero_sample_count_skips_project_without_working_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=0,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
            )

            self.assertIsNone(stats)
            self.assertFalse((output_dir / "demo.csv").exists())

    def test_same_working_and_output_directory_preserves_manual_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            output_dir = working_dir
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=1)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_name": "testA",
                        "to_name": "manualToString",
                        "from_url": "test://A",
                        "to_url": "prod://manual",
                        "to_fqs": "Demo.manualToString()",
                        "to_artifact": "#main-code",
                        "label": "1",
                        "tags": "manual",
                        "notes": "added from UI",
                    }
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=1,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            manual = result[result["to_url"] == "prod://manual"].iloc[0]
            self.assertEqual(1, stats.manual_rows_preserved)
            self.assertEqual("0", str(manual["candidate"]))
            self.assertEqual("1", str(manual["label"]))
            self.assertEqual("manual", manual["tags"])
            self.assertEqual("added from UI", manual["notes"])

    def test_update_columns_refreshes_manual_row_from_method_csv(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(
                candidate_dir,
                method_dir,
                project="demo",
                test_count=1,
                extra_methods=[
                    {
                        "url": "prod://manual",
                        "name": "freshToString",
                        "artifact": "#main-code",
                        "fqs": "Demo.freshToString()",
                        "tctracer_fqs": "Demo.freshToString()",
                        "testlinker_fqs": "Demo.freshToString()",
                    }
                ],
            )
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_name": "testA",
                        "to_name": "staleToString",
                        "from_url": "test://A",
                        "to_url": "prod://manual",
                        "from_artifact": "stale-from-artifact",
                        "to_fqs": "Demo.staleToString()",
                        "to_tctracer_fqs": "Demo.staleToString()",
                        "to_testlinker_fqs": "Demo.staleToString()",
                        "to_artifact": "stale-artifact",
                        "label": "1",
                        "tags": "manual",
                        "notes": "keep label metadata",
                    }
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=1,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                update_columns=[
                    "from_artifact",
                    "to_artifact",
                    "to_name",
                    "to_fqs",
                    "to_tctracer_fqs",
                    "to_testlinker_fqs",
                ],
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            manual = result[result["to_url"] == "prod://manual"].iloc[0]
            self.assertEqual(1, stats.rows_refreshed)
            self.assertEqual(0, stats.rows_not_refreshed)
            self.assertEqual("#test-code #test-case-method", manual["from_artifact"])
            self.assertEqual("freshToString", manual["to_name"])
            self.assertEqual("Demo.freshToString()", manual["to_fqs"])
            self.assertEqual("Demo.freshToString()", manual["to_tctracer_fqs"])
            self.assertEqual("Demo.freshToString()", manual["to_testlinker_fqs"])
            self.assertEqual("#main-code", manual["to_artifact"])
            self.assertEqual("1", str(manual["label"]))
            self.assertEqual("manual", manual["tags"])
            self.assertEqual("keep label metadata", manual["notes"])

    def test_update_columns_keeps_manual_row_when_method_lookup_missing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(candidate_dir, method_dir, project="demo", test_count=1)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_name": "testA",
                        "to_name": "manualOnly",
                        "from_url": "test://A",
                        "to_url": "prod://missing",
                        "to_artifact": "manual-artifact",
                        "label": "1",
                    }
                ]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=1,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                update_columns=["to_artifact", "to_name"],
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            manual = result[result["to_url"] == "prod://missing"].iloc[0]
            self.assertEqual(0, stats.rows_refreshed)
            self.assertEqual(1, stats.rows_not_refreshed)
            self.assertEqual("manualOnly", manual["to_name"])
            self.assertEqual("manual-artifact", manual["to_artifact"])

    def test_exclude_test_artifact_regex_filters_random_additions_only(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(
                candidate_dir,
                method_dir,
                project="demo",
                test_count=3,
                test_artifacts={
                    "test://B": "#test-module #test-code #test-case-method",
                },
            )
            pd.DataFrame(
                [{"project": "demo", "from_url": "test://A", "to_url": "prod://1", "label": "1"}]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=2,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                exclude_test_artifact_pattern=re.compile("#test-module"),
                random_state=42,
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(1, stats.excluded_test_methods)
            self.assertEqual({"test://A", "test://C"}, set(result["from_url"]))
            self.assertNotIn("test://B", set(result["from_url"]))

    def test_excluded_existing_working_method_is_preserved(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            candidate_dir, method_dir, working_dir, output_dir = self._make_dirs(root)
            self._write_project_inputs(
                candidate_dir,
                method_dir,
                project="demo",
                test_count=2,
                test_artifacts={"test://B": "#test-module #test-code #test-case-method"},
            )
            pd.DataFrame(
                [{"project": "demo", "from_url": "test://B", "to_url": "prod://1", "label": "1"}]
            ).to_csv(working_dir / "demo.csv", index=False)

            stats = self._regenerate_project(
                candidate_dir,
                method_dir,
                project="demo",
                sample_count_per_project=1,
                working_dir=working_dir,
                output_dir=output_dir,
                temp_dir=root / ".output",
                exclude_test_artifact_pattern=re.compile("#test-module"),
            )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(1, stats.reused_test_methods)
            self.assertEqual({"test://B"}, set(result["from_url"]))

    def test_default_sampling_does_not_pass_fixed_random_state(self):
        with mock.patch.object(pd.Series, "sample", autospec=True, return_value=pd.Series(["test://B"])) as sample:
            selected, reused_count, added_count = ground_truth_sample._select_test_methods(
                available_urls=["test://A", "test://B", "test://C"],
                working_urls=["test://A"],
                sample_count_per_project=2,
            )

        self.assertEqual({"test://A", "test://B"}, selected)
        self.assertEqual(1, reused_count)
        self.assertEqual(1, added_count)
        self.assertIsNone(sample.call_args.kwargs["random_state"])

    def test_invalid_exclude_regex_errors_before_regeneration(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            working_dir = Path(tmpdir) / "working"
            working_dir.mkdir()
            with mock.patch.object(ground_truth_sample, "regenerate_project") as regenerate:
                with self.assertRaises(SystemExit):
                    ground_truth_sample.main(
                        [
                            "--project-index",
                            "0",
                            "--sample-count-per-project",
                            "1",
                            "--t2p-ground-truth-dir",
                            str(working_dir),
                            "--exclude-test-artifact-regex",
                            "[",
                        ]
                    )
            regenerate.assert_not_called()

    def test_main_rejects_add_only_with_update_columns(self):
        with mock.patch.object(ground_truth_sample, "regenerate_project") as regenerate:
            with self.assertRaises(SystemExit):
                ground_truth_sample.main(
                    [
                        "--project-index",
                        "0",
                        "--sample-count-per-project",
                        "20",
                        "--t2p-ground-truth-dir",
                        "unused",
                        "--add-only",
                        "--update-columns",
                        "to_testlinker_fqs",
                    ]
                )
        regenerate.assert_not_called()

    def test_main_rejects_add_only_with_add_missing_candidates(self):
        with mock.patch.object(ground_truth_sample, "regenerate_project") as regenerate:
            with self.assertRaises(SystemExit):
                ground_truth_sample.main(
                    [
                        "--project-index",
                        "0",
                        "--sample-count-per-project",
                        "20",
                        "--t2p-ground-truth-dir",
                        "unused",
                        "--add-only",
                        "--add-missing-candidates",
                    ]
                )
        regenerate.assert_not_called()

    def test_main_accepts_t2p_ground_truth_dir_and_project_index(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            workspace_dir = root / "workspace"
            experiment_dir = workspace_dir / "experiment" / "demo-exp"
            working_dir = root / "working"
            experiment_dir.mkdir(parents=True)
            working_dir.mkdir()
            pd.DataFrame([{"project": "alpha"}, {"project": "beta"}]).to_csv(
                experiment_dir / "project.csv",
                index=False,
            )
            stats = ground_truth_sample.GroundTruthProjectStats(
                project="beta",
                working_test_methods=0,
                reused_test_methods=0,
                added_test_methods=0,
                excluded_test_methods=0,
                selected_test_methods=0,
                generated_rows=0,
                manual_rows_preserved=0,
                rows_refreshed=0,
                rows_not_refreshed=0,
                missing_candidate_rows_added=0,
                carried_label_rows=0,
                new_or_unlabelled_rows=0,
                output_file=experiment_dir / "t2p-ground-truth" / "beta.csv",
            )

            with mock.patch.object(ground_truth_sample, "regenerate_project", return_value=stats) as regenerate:
                exit_code = ground_truth_sample.main(
                    [
                        "--workspace-directory",
                        str(workspace_dir),
                        "--experiment-name",
                        "demo-exp",
                        "--project-index",
                        "1",
                        "--sample-count-per-project",
                        "0",
                        "--t2p-ground-truth-dir",
                        str(working_dir),
                    ]
                )

            self.assertEqual(0, exit_code)
            regenerate.assert_called_once()
            self.assertEqual("beta", regenerate.call_args.kwargs["project"])
            self.assertEqual(experiment_dir / "t2p-candidate-expanded", regenerate.call_args.kwargs["candidate_dir"])
            self.assertEqual(experiment_dir / "method", regenerate.call_args.kwargs["method_dir"])
            self.assertEqual(experiment_dir / "t2p-ground-truth", regenerate.call_args.kwargs["output_dir"])
            self.assertEqual(experiment_dir / ".t2p-ground-truth", regenerate.call_args.kwargs["temp_dir"])

    def _make_dirs(self, root: Path) -> tuple[Path, Path, Path, Path]:
        candidate_dir = root / "t2p-candidate-expanded"
        method_dir = root / "method"
        working_dir = root / "working"
        output_dir = root / "output"
        for directory in (candidate_dir, method_dir, working_dir, output_dir):
            directory.mkdir(parents=True)
        return candidate_dir, method_dir, working_dir, output_dir

    def _regenerate_project(self, candidate_dir: Path, method_dir: Path, **kwargs):
        return ground_truth_sample.regenerate_project(
            candidate_dir=candidate_dir,
            method_dir=method_dir,
            **kwargs,
        )

    def _write_project_inputs(
        self,
        candidate_dir: Path,
        method_dir: Path,
        *,
        project: str,
        test_count: int,
        test_artifacts: dict[str, str] | None = None,
        extra_methods: list[dict[str, str]] | None = None,
    ) -> None:
        test_artifacts = test_artifacts or {}
        extra_methods = extra_methods or []
        test_urls = [f"test://{chr(ord('A') + index)}" for index in range(test_count)]
        candidate_rows = []
        method_rows = [
            {
                "url": "prod://1",
                "name": "prod1",
                "artifact": "#main-code",
                "fqs": "Demo.prod1()",
                "tctracer_fqs": "Demo.prod1()",
                "testlinker_fqs": "Demo.prod1()",
            },
            {
                "url": "test-helper://1",
                "name": "helper",
                "artifact": "#test-code #test-helper-method",
                "fqs": "DemoTest.helper()",
                "tctracer_fqs": "DemoTest.helper()",
                "testlinker_fqs": "DemoTest.helper()",
            },
        ]
        for index, test_url in enumerate(test_urls):
            method_rows.append(
                {
                    "url": test_url,
                    "name": f"test{chr(ord('A') + index)}",
                    "artifact": test_artifacts.get(test_url, "#test-code #test-case-method"),
                    "fqs": f"DemoTest.test{index}()",
                    "tctracer_fqs": f"DemoTest.test{index}()",
                    "testlinker_fqs": f"DemoTest.test{index}()",
                }
            )
            candidate_rows.extend(
                [
                    {
                        "project": project,
                        "from_name": f"test{chr(ord('A') + index)}",
                        "to_name": "prod1",
                        "from_url": test_url,
                        "to_url": "prod://1",
                        "from_fqs": f"DemoTest.test{index}()",
                        "from_tctracer_fqs": f"DemoTest.test{index}()",
                        "from_testlinker_fqs": f"DemoTest.test{index}()",
                        "to_fqs": "Demo.prod1()",
                        "to_tctracer_fqs": "Demo.prod1()",
                        "to_testlinker_fqs": "Demo.prod1()",
                        "to_call_depth": 1,
                    },
                    {
                        "project": project,
                        "from_name": f"test{chr(ord('A') + index)}",
                        "to_name": "helper",
                        "from_url": test_url,
                        "to_url": "test-helper://1",
                        "from_fqs": f"DemoTest.test{index}()",
                        "from_tctracer_fqs": f"DemoTest.test{index}()",
                        "from_testlinker_fqs": f"DemoTest.test{index}()",
                        "to_fqs": "DemoTest.helper()",
                        "to_tctracer_fqs": "DemoTest.helper()",
                        "to_testlinker_fqs": "DemoTest.helper()",
                        "to_call_depth": 1,
                    },
                ]
            )

        method_rows.extend(extra_methods)
        pd.DataFrame(candidate_rows).to_csv(candidate_dir / f"{project}.csv", index=False)
        pd.DataFrame(method_rows).to_csv(method_dir / f"{project}.csv", index=False)


if __name__ == "__main__":
    unittest.main()
