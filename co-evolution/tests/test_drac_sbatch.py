from pathlib import Path
import sys
import tempfile
import unittest

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.drac.main import (
    _parse_index_ranges,
    _expand_indices,
    _format_shell_command,
    _group_consecutive,
    _indices_to_task_ranges,
    _shift_task_groups,
    _output_exists,
    process,
    process_with_details,
)

SAMPLE_INPUT = """\
sbatch \\
  --job-name=method-callgraph-22-29-36-47 \\
  --time=1-00:00:00 \\
  --array=22,29,36,47 \\
  --mem=8GB \\
  --output=/home/shahidul/scratch/method-co-evolution/log/job/%x.%A_%a.out \\
  --error=/home/shahidul/scratch/method-co-evolution/log/job/%x.%A_%a.err \\
  scripts/job.sh \\
  --command call-graph \\
  --workspace-directory {workspace} \\
  --tool-name methodParser \\
  --java-options "-Xmx7g" \\
  --retry-errors false \\
  --merge-threshold 1000 \\
  --merge-interval-seconds 0 \\
  --shards 200"""


def _make_repo_df(projects: list[str]) -> pd.DataFrame:
    return pd.DataFrame({"project": projects})


class TestParseIndexRanges(unittest.TestCase):
    def test_single_index(self):
        self.assertEqual(_parse_index_ranges("22"), [(22, 22)])

    def test_multiple_indices(self):
        self.assertEqual(_parse_index_ranges("22,29,36,47"), [(22, 22), (29, 29), (36, 36), (47, 47)])

    def test_index_range(self):
        self.assertEqual(_parse_index_ranges("10-15"), [(10, 15)])

    def test_mixed(self):
        self.assertEqual(_parse_index_ranges("0,10-15,22"), [(0, 0), (10, 15), (22, 22)])


class TestExpandIndices(unittest.TestCase):
    def test_single(self):
        self.assertEqual(_expand_indices([(22, 22)]), [22])

    def test_range(self):
        self.assertEqual(_expand_indices([(10, 13)]), [10, 11, 12, 13])

    def test_mixed(self):
        self.assertEqual(_expand_indices([(0, 0), (10, 12), (22, 22)]), [0, 10, 11, 12, 22])


class TestGroupConsecutive(unittest.TestCase):
    def test_no_gaps(self):
        self.assertEqual(_group_consecutive([10, 11, 12, 13]), [(10, 13)])

    def test_all_separate(self):
        self.assertEqual(_group_consecutive([22, 29, 36, 47]), [(22, 22), (29, 29), (36, 36), (47, 47)])

    def test_mixed(self):
        self.assertEqual(_group_consecutive([0, 10, 11, 13, 14, 15, 22]), [(0, 0), (10, 11), (13, 15), (22, 22)])

    def test_empty(self):
        self.assertEqual(_group_consecutive([]), [])


class TestFormatShellCommand(unittest.TestCase):
    def test_formats_copyable_multiline_command(self):
        command = 'sbatch --java-options "-Xmx7g" scripts/job.sh --command call-graph'
        self.assertEqual(
            _format_shell_command(command),
            "sbatch \\\n"
            "  --java-options \\\n"
            "  -Xmx7g \\\n"
            "  scripts/job.sh \\\n"
            "  --command \\\n"
            "  call-graph",
        )


class TestIndicesToTaskRanges(unittest.TestCase):
    def test_single_indices(self):
        groups = [(22, 22), (29, 29), (36, 36), (47, 47)]
        self.assertEqual(
            _indices_to_task_ranges(groups, 200),
            ["4400-4599", "5800-5999", "7200-7399", "9400-9599"],
        )

    def test_index_range_collapsed(self):
        # indices 10-15 → task IDs 2000-3199
        self.assertEqual(_indices_to_task_ranges([(10, 15)], 200), ["2000-3199"])

    def test_mixed(self):
        # 0 → 0-199, 10-15 → 2000-3199, 22 → 4400-4599
        groups = [(0, 0), (10, 15), (22, 22)]
        self.assertEqual(
            _indices_to_task_ranges(groups, 200),
            ["0-199", "2000-3199", "4400-4599"],
        )


class TestShiftTaskGroups(unittest.TestCase):
    def test_no_shift_when_max_within_nibi_limit(self):
        task_groups, shift = _shift_task_groups([(4400, 4599), (9800, 9999)])
        self.assertEqual(task_groups, [(4400, 4599), (9800, 9999)])
        self.assertEqual(shift, 0)

    def test_shift_when_max_exceeds_nibi_limit(self):
        task_groups, shift = _shift_task_groups([(10000, 10199)])
        self.assertEqual(task_groups, [(0, 199)])
        self.assertEqual(shift, 10000)

    def test_raise_when_shifted_span_still_exceeds_nibi_limit(self):
        with self.assertRaises(ValueError):
            _shift_task_groups([(4400, 4599), (16000, 16199)])


class TestOutputExists(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def _make_file(self, *parts):
        path = Path(self.workspace, *parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def _make_dir(self, *parts):
        path = Path(self.workspace, *parts)
        path.mkdir(parents=True, exist_ok=True)

    def test_method_scan_exists(self):
        self._make_file("method", "checkstyle.csv")
        self.assertTrue(_output_exists("method-scan", self.workspace, "checkstyle", ""))

    def test_method_scan_alias(self):
        self._make_file("method", "checkstyle.csv")
        self.assertTrue(_output_exists("scan-method", self.workspace, "checkstyle", ""))

    def test_method_scan_missing(self):
        self.assertFalse(_output_exists("method-scan", self.workspace, "checkstyle", ""))

    def test_callgraph_exists(self):
        self._make_file("callgraph", "commons-io.csv")
        self.assertTrue(_output_exists("method-callgraph", self.workspace, "commons-io", ""))

    def test_callgraph_alias(self):
        self._make_file("callgraph", "commons-io.csv")
        self.assertTrue(_output_exists("call-graph", self.workspace, "commons-io", ""))

    def test_callgraph_missing(self):
        self.assertFalse(_output_exists("method-callgraph", self.workspace, "commons-io", ""))

    def test_history_exists(self):
        self._make_dir("history", "codeShovel", "checkstyle")
        self.assertTrue(_output_exists("method-history", self.workspace, "checkstyle", "codeShovel"))

    def test_history_missing(self):
        self.assertFalse(_output_exists("method-history", self.workspace, "checkstyle", "codeShovel"))

    def test_method_code_exists(self):
        self._make_file("method-code", "ant.csv")
        self.assertTrue(_output_exists("method-code", self.workspace, "ant", ""))

    def test_method_code_missing(self):
        self.assertFalse(_output_exists("method-code", self.workspace, "ant", ""))

    def test_test_smell_callgraph_exists_without_strategies(self):
        self._make_file("test-smell", "jnose", "callgraph", "checkstyle.csv")
        self.assertTrue(_output_exists("test-smell", self.workspace, "checkstyle", "jnose"))

    def test_test_smell_strategy_exists_with_strategies(self):
        self._make_file("test-smell", "jnose", "nc", "checkstyle.csv")
        self.assertTrue(_output_exists("test-smell", self.workspace, "checkstyle", "jnose", "nc"))

    def test_test_smell_multiple_strategies_require_all_outputs(self):
        self._make_file("test-smell", "jnose", "nc", "checkstyle.csv")
        self.assertFalse(_output_exists("test-smell", self.workspace, "checkstyle", "jnose", "nc,ncc"))
        self._make_file("test-smell", "jnose", "ncc", "checkstyle.csv")
        self.assertTrue(_output_exists("test-smell", self.workspace, "checkstyle", "jnose", "nc,ncc"))


class TestProcess(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.workspace = self.tmp.name
        self.runtime_workspace = Path(self.workspace, "experiment", "main")
        projects = [f"project-{i}" for i in range(50)]
        self.repo_df = _make_repo_df(projects)

    def tearDown(self):
        self.tmp.cleanup()

    def _input(self):
        return SAMPLE_INPUT.format(workspace=self.workspace)

    def test_indices_expanded_to_ranges(self):
        result = process(self._input(), self.repo_df, replace=True, workspace_override=self.workspace)
        self.assertIn("--array=4400-4599,5800-5999,7200-7399,9400-9599", result)
        self.assertNotIn("--job-index-shift", result)

    def test_array_above_nibi_limit_is_shifted_and_job_shift_is_passed(self):
        text = self._input().replace("--array=22,29,36,47", "--array=50")
        result = process(text, repo_df=None, replace=True, workspace_override=None)
        self.assertIn("--array=0-199", result)
        self.assertIn("--job-index-shift 10000", result)

    def test_existing_job_shift_is_replaced_when_recomputed(self):
        text = self._input().replace("--array=22,29,36,47", "--array=50")
        text = f"{text} --job-index-shift 1"
        result = process(text, repo_df=None, replace=True, workspace_override=None)
        self.assertIn("--array=0-199", result)
        self.assertIn("--job-index-shift 10000", result)
        self.assertEqual(result.count("--job-index-shift"), 1)

    def test_existing_job_shift_is_removed_when_not_needed(self):
        text = f"{self._input()} --job-index-shift 1"
        result = process(text, self.repo_df, replace=True, workspace_override=self.workspace)
        self.assertIn("--array=4400-4599,5800-5999,7200-7399,9400-9599", result)
        self.assertNotIn("--job-index-shift", result)

    def test_no_existing_files_keeps_all(self):
        result = process(self._input(), self.repo_df, replace=False, workspace_override=self.workspace)
        self.assertIn("--array=4400-4599,5800-5999,7200-7399,9400-9599", result)

    def test_existing_file_skips_index(self):
        path = self.runtime_workspace / "callgraph" / "project-29.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        result = process(self._input(), self.repo_df, replace=False, workspace_override=self.workspace)
        self.assertIn("--array=4400-4599,7200-7399,9400-9599", result)

    def test_strategy_test_smell_existing_output_skips_index(self):
        text = SAMPLE_INPUT.format(workspace=self.workspace).replace(
            "--command call-graph",
            "--command test-smell",
        ).replace(
            "--tool-name methodParser",
            "--tool-name jnose --strategies nc",
        )
        path = self.runtime_workspace / "test-smell" / "jnose" / "nc" / "project-29.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

        result = process(text, self.repo_df, replace=False, workspace_override=self.workspace)

        self.assertIn("--array=4400-4599,7200-7399,9400-9599", result)

    def test_strategy_test_smell_keeps_index_when_one_strategy_output_missing(self):
        text = SAMPLE_INPUT.format(workspace=self.workspace).replace(
            "--command call-graph",
            "--command test-smell",
        ).replace(
            "--tool-name methodParser",
            "--tool-name jnose --strategies nc,ncc",
        )
        path = self.runtime_workspace / "test-smell" / "jnose" / "nc" / "project-29.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

        result = process(text, self.repo_df, replace=False, workspace_override=self.workspace)

        self.assertIn("--array=4400-4599,5800-5999,7200-7399,9400-9599", result)

    def test_replace_overrides_existing_file(self):
        path = self.runtime_workspace / "callgraph" / "project-29.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        result = process(self._input(), self.repo_df, replace=True, workspace_override=self.workspace)
        self.assertIn("--array=4400-4599,5800-5999,7200-7399,9400-9599", result)

    def test_consecutive_indices_collapsed_after_filter(self):
        # Input: indices 22,23,24,29 — after filtering 23, should give 22,24 and 29 as separate ranges
        text = SAMPLE_INPUT.format(workspace=self.workspace).replace(
            "--array=22,29,36,47", "--array=22-24,29"
        )
        path = self.runtime_workspace / "callgraph" / "project-23.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        result = process(text, self.repo_df, replace=False, workspace_override=self.workspace)
        # 22 → 4400-4599, 24 → 4800-4999, 29 → 5800-5999
        self.assertIn("--array=4400-4599,4800-4999,5800-5999", result)

    def test_jobname_unchanged(self):
        result = process(self._input(), self.repo_df, replace=True, workspace_override=self.workspace)
        self.assertIn("--job-name=method-callgraph-22-29-36-47", result)

    def test_no_workspace_skips_existence_check(self):
        path = self.runtime_workspace / "callgraph" / "project-29.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        result = process(self._input(), repo_df=None, replace=False, workspace_override=None)
        self.assertIn("--array=4400-4599,5800-5999,7200-7399,9400-9599", result)

    def test_out_of_bounds_project_indices_are_truncated_before_filtering(self):
        text = self._input().replace("--array=22,29,36,47", "--array=45-60")
        result = process_with_details(text, self.repo_df, replace=False, workspace_override=self.workspace)
        self.assertIn("--array=9000-9999", result.command)
        self.assertTrue(result.repository_truncated)
        self.assertEqual(result.repository_valid_index_ranges, [(45, 49)])
        self.assertEqual(result.repository_excluded_index_ranges, [(50, 60)])

    def test_existing_outputs_are_reported_separately_from_limit_exclusions(self):
        text = self._input().replace("--array=22,29,36,47", "--array=0-60")
        for idx in [1, 2, 50]:
            path = self.runtime_workspace / "callgraph" / f"project-{idx}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        result = process_with_details(text, self.repo_df, replace=False, workspace_override=self.workspace)
        self.assertEqual(result.completed_excluded_index_ranges, [(1, 2)])
        self.assertEqual(result.repository_excluded_index_ranges, [(50, 60)])
        self.assertEqual(result.cluster_limit_excluded_index_ranges, [])

    def test_too_wide_task_range_is_truncated_to_nibi_limit(self):
        text = self._input().replace("--array=22,29,36,47", "--array=0-100")
        result = process_with_details(text, repo_df=None, replace=True, workspace_override=None)
        self.assertIn("--array=0-9999", result.command)
        self.assertTrue(result.task_truncated)
        self.assertEqual(result.final_logical_task_groups, [(0, 9999)])
        self.assertEqual(result.job_index_shift, 0)

    def test_shifted_too_wide_task_range_is_truncated_to_nibi_limit(self):
        text = self._input().replace("--array=22,29,36,47", "--array=50-100")
        result = process_with_details(text, repo_df=None, replace=True, workspace_override=None)
        self.assertIn("--array=0-9999", result.command)
        self.assertIn("--job-index-shift 10000", result.command)
        self.assertTrue(result.task_truncated)
        self.assertEqual(result.final_logical_task_groups, [(10000, 19999)])
        self.assertEqual(result.job_index_shift, 10000)

    def test_all_existing_raises(self):
        for idx in [22, 29, 36, 47]:
            path = self.runtime_workspace / "callgraph" / f"project-{idx}.csv"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
        with self.assertRaises(ValueError):
            process(self._input(), self.repo_df, replace=False, workspace_override=self.workspace)


if __name__ == "__main__":
    unittest.main()
