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

from mhc.util import parse_project_index
from ptc.sample import ground_truth_sample


@unittest.skipIf(pd is None, "pandas is required for ground truth sample tests")
class TestGroundTruthSample(unittest.TestCase):
    def test_project_index_selects_repository_rows(self):
        projects = ["commons-io", "commons-lang", "gson"]

        self.assertEqual(["commons-lang"], parse_project_index("1", projects))
        self.assertEqual(["commons-lang", "gson"], parse_project_index("1:", projects))
        self.assertEqual(["commons-io", "commons-lang"], parse_project_index(":2", projects))
        self.assertEqual(["gson"], parse_project_index("-1", projects))
        self.assertEqual([], parse_project_index(None, projects))

    def test_parse_update_columns_accepts_comma_separated_values(self):
        self.assertEqual(
            ["from_artifact", "to_artifact", "to_name", "to_fqs"],
            ground_truth_sample.parse_update_columns("from_artifact,to_artifact, to_name,to_fqs,to_name"),
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

            with self._patch_input_dirs(candidate_dir, method_dir):
                stats = ground_truth_sample.regenerate_project(
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
            self.assertEqual("1", str(preserved["label"]))
            self.assertEqual("needs-check", preserved["tags"])
            self.assertEqual("keep this", preserved["notes"])

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

            with self._patch_input_dirs(candidate_dir, method_dir):
                stats = ground_truth_sample.regenerate_project(
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

            with self._patch_input_dirs(candidate_dir, method_dir):
                stats = ground_truth_sample.regenerate_project(
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

            with self._patch_input_dirs(candidate_dir, method_dir):
                stats = ground_truth_sample.regenerate_project(
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

            with self._patch_input_dirs(candidate_dir, method_dir):
                ground_truth_sample.regenerate_project(
                    project="demo",
                    sample_count_per_project=1,
                    working_dir=working_dir,
                    output_dir=output_dir,
                    temp_dir=root / ".output",
                )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(ground_truth_sample.GROUND_TRUTH_COLUMNS, result.columns.tolist())
            self.assertEqual(["test://A"], result["from_url"].drop_duplicates().tolist())

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

            with self._patch_input_dirs(candidate_dir, method_dir):
                stats = ground_truth_sample.regenerate_project(
                    project="demo",
                    sample_count_per_project=1,
                    working_dir=working_dir,
                    output_dir=output_dir,
                    temp_dir=root / ".output",
                )

            result = pd.read_csv(output_dir / "demo.csv", keep_default_na=False, na_filter=False)
            manual = result[result["to_url"] == "prod://manual"].iloc[0]
            self.assertEqual(1, stats.manual_rows_preserved)
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

            with self._patch_input_dirs(candidate_dir, method_dir):
                stats = ground_truth_sample.regenerate_project(
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

            with self._patch_input_dirs(candidate_dir, method_dir):
                stats = ground_truth_sample.regenerate_project(
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

            with self._patch_input_dirs(candidate_dir, method_dir):
                stats = ground_truth_sample.regenerate_project(
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

            with self._patch_input_dirs(candidate_dir, method_dir):
                stats = ground_truth_sample.regenerate_project(
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
                            "--ground-truth-working-inprogress",
                            str(working_dir),
                            "--exclude-test-artifact-regex",
                            "[",
                        ]
                    )
            regenerate.assert_not_called()

    def _make_dirs(self, root: Path) -> tuple[Path, Path, Path, Path]:
        candidate_dir = root / "t2p-candidate-expanded"
        method_dir = root / "method"
        working_dir = root / "working"
        output_dir = root / "output"
        for directory in (candidate_dir, method_dir, working_dir, output_dir):
            directory.mkdir(parents=True)
        return candidate_dir, method_dir, working_dir, output_dir

    def _patch_input_dirs(self, candidate_dir: Path, method_dir: Path):
        return mock.patch.multiple(
            ground_truth_sample,
            T2P_CANDIDATE_DIR=candidate_dir,
            METHOD_DIR=method_dir,
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
