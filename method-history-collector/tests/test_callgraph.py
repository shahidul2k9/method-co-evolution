import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.callgraph import (
    CALLGRAPH_CACHE_COLUMNS,
    CALLGRAPH_COLUMNS,
    CALLGRAPH_ERROR_COLUMN,
    CALLGRAPH_ERROR_MAX_LENGTH,
    CALLGRAPH_ERROR_MARKER,
    CALLGRAPH_FLAG_COLUMN,
    _build_callgraph_error_marker,
    _build_callgraph_scan_marker,
    execute_callgraph_per_file,
    _finalize_callgraph,
    _fan_in_from_fan_out,
    _load_cached_callgraph_files,
)


class FakeCallGraphServiceImpl:
    init_calls = []
    scanned_files = []
    cache_stats_calls = 0

    @staticmethod
    def getInstance():
        return FakeCallGraphServiceImpl()

    def init(
        self,
        project_name,
        repository_url,
        repository_path,
        commit_hash,
        method_mapping_file,
        class_mapping_file,
        artifact_config_path,
        checkout_repository,
        max_cache_size,
    ):
        FakeCallGraphServiceImpl.init_calls.append(
            (
                project_name,
                repository_url,
                repository_path,
                commit_hash,
                method_mapping_file,
                class_mapping_file,
                artifact_config_path,
                checkout_repository,
                max_cache_size,
            )
        )

    def findCallgraph(self, file_without_base):
        FakeCallGraphServiceImpl.scanned_files.append(file_without_base)
        return []

    def logCacheStats(self):
        FakeCallGraphServiceImpl.cache_stats_calls += 1


class CallGraphRunnerTest(unittest.TestCase):
    def test_fan_in_from_fan_out_swaps_callee_and_caller(self):
        fan_out = pd.DataFrame(
            [
                {
                    "project": "demo",
                    "from_name": "caller",
                    "to_name": "callee",
                    "from_url": "caller-url",
                    "to_url": "callee-url",
                    "from_expression": "method",
                    "to_expression": "method_call",
                    "from_pkg": "demo",
                    "to_pkg": "demo.target",
                    "from_fqn": "demo.Caller.caller",
                    "to_fqn": "demo.Target.callee",
                    "from_fqs": "demo.Caller.caller()",
                    "from_tctracer_fqs": "caller()",
                    "from_testlinker_fqs": "caller()",
                    "from_testlinker_fqp": "[]",
                    "to_fqs": "demo.Target.callee()",
                    "to_tctracer_fqs": "callee()",
                    "to_testlinker_fqs": "callee()",
                    "to_testlinker_fqp": "[]",
                    "from_start": 10,
                    "from_end": 20,
                    "to_start": 30,
                    "to_end": 40,
                    "from_invocation": 15,
                    "to_invocation": None,
                    "from_lcba": 0,
                    "to_lcba": 1,
                    "from_file": "src/Caller.java",
                    "to_file": "src/Target.java",
                    "from_caller_url": None,
                    "to_caller_url": None,
                    "from_call_depth": None,
                    "to_call_depth": None,
                    "hash": "abc123",
                    "from_resolver": "javaparser",
                    "to_resolver": "mapping",
                }
            ],
            columns=CALLGRAPH_COLUMNS,
        )

        fan_in = _fan_in_from_fan_out(fan_out)

        self.assertEqual(["callee"], fan_in["from_name"].tolist())
        self.assertEqual(["caller"], fan_in["to_name"].tolist())
        self.assertEqual(["callee-url"], fan_in["from_url"].tolist())
        self.assertEqual(["caller-url"], fan_in["to_url"].tolist())
        self.assertTrue(fan_in["from_invocation"].isna().all())
        self.assertTrue(fan_in["to_invocation"].isna().all())
        self.assertEqual(CALLGRAPH_COLUMNS, fan_in.columns.tolist())

    def test_finalize_callgraph_writes_callgraph_and_fanin_outputs(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / "cache.csv"
            lock_file = root / "cache.lock"
            callgraph_file = root / "callgraph" / "demo.csv"
            fanin_file = root / "fanin" / "demo.csv"
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_file": "src/Caller.java",
                        "from_name": "caller",
                        "to_name": "callee",
                        "from_url": "caller-url",
                        "to_url": "callee-url",
                        "from_start": "72.0",
                        "from_end": 80.0,
                        "to_start": "96.0",
                        "to_end": 108.0,
                        "from_invocation": "75.0",
                        "from_lcba": "0.0",
                        "to_lcba": 1.0,
                        "hash": "abc123",
                    }
                ],
                columns=CALLGRAPH_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = _finalize_callgraph(
                str(cache_file),
                str(callgraph_file),
                str(fanin_file),
                str(root / ".callgraph-error" / "demo.csv"),
                {"src/Caller.java"},
                str(lock_file),
            )

            self.assertTrue(merged)
            self.assertFalse(cache_file.exists())
            self.assertFalse(lock_file.exists())
            callgraph_text = callgraph_file.read_text(encoding="utf-8")
            fanin_text = fanin_file.read_text(encoding="utf-8")
            self.assertNotIn("72.0", callgraph_text)
            self.assertNotIn("96.0", callgraph_text)
            self.assertNotIn("72.0", fanin_text)
            callgraph_df = pd.read_csv(callgraph_file, dtype=str, keep_default_na=False, na_filter=False)
            fanin_df = pd.read_csv(fanin_file, dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual(["caller"], callgraph_df["from_name"].tolist())
            self.assertEqual(["callee"], fanin_df["from_name"].tolist())
            self.assertEqual("72", callgraph_df.loc[0, "from_start"])
            self.assertEqual("96", callgraph_df.loc[0, "to_start"])
            self.assertEqual("75", callgraph_df.loc[0, "from_invocation"])
            self.assertEqual("0", callgraph_df.loc[0, "from_lcba"])
            self.assertEqual("96", fanin_df.loc[0, "from_start"])
            self.assertEqual("72", fanin_df.loc[0, "to_start"])

    def test_error_markers_are_retryable_for_shard_processing(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            cache_file = Path(temp_directory) / "cache.csv"
            pd.DataFrame(
                [
                    _build_callgraph_error_marker("src/Broken.java"),
                    _build_callgraph_scan_marker("src/Done.java"),
                    {
                        **{col: None for col in CALLGRAPH_CACHE_COLUMNS},
                        "from_file": "src/Caller.java",
                        "from_name": "caller",
                        "to_name": "callee",
                        "hash": "abc123",
                    },
                ],
                columns=CALLGRAPH_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            self.assertEqual(
                {"src/Done.java", "src/Caller.java"},
                _load_cached_callgraph_files(str(cache_file)),
            )
            self.assertEqual(
                {"src/Broken.java", "src/Done.java", "src/Caller.java"},
                _load_cached_callgraph_files(str(cache_file), retry_errors=False),
            )

    def test_finalize_waits_until_all_files_are_tried(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / "cache.csv"
            lock_file = root / "cache.lock"
            callgraph_file = root / "callgraph" / "demo.csv"
            fanin_file = root / "fanin" / "demo.csv"
            error_file = root / ".callgraph-error" / "demo.csv"
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [_build_callgraph_scan_marker("src/Done.java")],
                columns=CALLGRAPH_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = _finalize_callgraph(
                str(cache_file),
                str(callgraph_file),
                str(fanin_file),
                str(error_file),
                {"src/Done.java", "src/Missing.java"},
                str(lock_file),
            )

            self.assertFalse(merged)
            self.assertTrue(cache_file.exists())
            self.assertTrue(lock_file.exists())
            self.assertFalse(callgraph_file.exists())
            self.assertFalse(fanin_file.exists())

    def test_finalize_writes_failed_files_to_callgraph_error_folder(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / "cache.csv"
            callgraph_file = root / "callgraph" / "demo.csv"
            fanin_file = root / "fanin" / "demo.csv"
            error_file = root / ".callgraph-error" / "demo.csv"
            pd.DataFrame(
                [
                    {
                        **{col: None for col in CALLGRAPH_CACHE_COLUMNS},
                        "project": "demo",
                        "from_file": "src/Caller.java",
                        "from_name": "caller",
                        "to_name": "callee",
                        "hash": "abc123",
                    },
                    _build_callgraph_error_marker("src/Broken.java"),
                    _build_callgraph_scan_marker("src/Empty.java"),
                ],
                columns=CALLGRAPH_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = _finalize_callgraph(
                str(cache_file),
                str(callgraph_file),
                str(fanin_file),
                str(error_file),
                {"src/Caller.java", "src/Broken.java", "src/Empty.java"},
            )

            self.assertTrue(merged)
            self.assertFalse(cache_file.exists())
            self.assertEqual(["caller"], pd.read_csv(callgraph_file)["from_name"].tolist())
            error_df = pd.read_csv(error_file)
            self.assertEqual(["src/Broken.java"], error_df["from_file"].tolist())
            self.assertEqual([CALLGRAPH_ERROR_MARKER], error_df[CALLGRAPH_FLAG_COLUMN].tolist())
            self.assertIn(CALLGRAPH_ERROR_COLUMN, error_df.columns)

    def test_error_marker_stores_truncated_error_text_in_private_column(self):
        marker = _build_callgraph_error_marker("src/Broken.java", "x" * 300)

        self.assertEqual(CALLGRAPH_ERROR_MARKER, marker[CALLGRAPH_FLAG_COLUMN])
        self.assertEqual(CALLGRAPH_ERROR_MAX_LENGTH, len(marker[CALLGRAPH_ERROR_COLUMN]))

    def test_execute_configures_scanner_cache_before_init_and_logs_stats(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repository"
            data_directory = root / "data"
            workspace_directory = root / "workspace"
            repository_path = repository_directory / "apache-hadoop-copy"
            java_file = repository_path / "src" / "Caller.java"
            repository_df = pd.DataFrame(
                [
                    {
                        "project": "apache-hadoop-copy",
                        "url": "https://github.com/apache/hadoop",
                        "updated_hash": "abc123",
                    }
                ]
            )

            with patch("mhc.callgraph.git.clone_and_checkout_commit"), \
                    patch("mhc.callgraph._collect_java_files", return_value=[str(java_file)]), \
                    patch("mhc.callgraph.util.format_method_mapping_file", return_value=str(root / "method.csv")), \
                    patch("mhc.callgraph.util.format_class_mapping_file", return_value=str(root / "class.csv")), \
                    patch("jpype.JClass") as mock_jclass:
                scanner = mock_jclass.return_value.getInstance.return_value
                scanner.findCallgraph.return_value = []

                execute_callgraph_per_file(
                    repository_df,
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    max_cache_size=512,
                    merge_threshold=1,
                    merge_interval_seconds=0,
                )

                scanner.init.assert_called_once_with(
                    "apache-hadoop-copy",
                    "https://github.com/apache/hadoop",
                    str(repository_path),
                    "abc123",
                    str(root / "method.csv"),
                    str(root / "class.csv"),
                    None,
                    False,
                    512,
                )
                scanner.logCacheStats.assert_called_once_with()

    def test_execute_callgraph_init_reset_interval_zero_reuses_scanner(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repository"
            data_directory = root / "data"
            workspace_directory = root / "workspace"
            repository_path = repository_directory / "demo"
            java_files = [
                str(repository_path / "src" / "Alpha.java"),
                str(repository_path / "src" / "Beta.java"),
            ]
            repository_df = pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "url": "https://example.test/demo",
                        "updated_hash": "abc123",
                    }
                ]
            )

            FakeCallGraphServiceImpl.init_calls = []
            FakeCallGraphServiceImpl.scanned_files = []
            FakeCallGraphServiceImpl.cache_stats_calls = 0
            with patch("mhc.callgraph.git.clone_and_checkout_commit"), \
                    patch("mhc.callgraph._collect_java_files", return_value=java_files), \
                    patch("mhc.callgraph.util.format_method_mapping_file", return_value=str(root / "method.csv")), \
                    patch("mhc.callgraph.util.format_class_mapping_file", return_value=str(root / "class.csv")), \
                    patch("jpype.JClass", return_value=FakeCallGraphServiceImpl):
                execute_callgraph_per_file(
                    repository_df,
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    max_cache_size=512,
                    merge_threshold=1,
                    merge_interval_seconds=0,
                    init_reset_interval_files=0,
                )

            self.assertEqual(1, len(FakeCallGraphServiceImpl.init_calls))
            self.assertEqual(["src/Alpha.java", "src/Beta.java"], FakeCallGraphServiceImpl.scanned_files)

    def test_execute_callgraph_init_reset_interval_rebuilds_scanner(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repository"
            data_directory = root / "data"
            workspace_directory = root / "workspace"
            repository_path = repository_directory / "demo"
            method_mapping_file = root / "method.csv"
            class_mapping_file = root / "class.csv"
            java_files = [
                str(repository_path / "src" / "Alpha.java"),
                str(repository_path / "src" / "Beta.java"),
            ]
            repository_df = pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "url": "https://example.test/demo",
                        "updated_hash": "abc123",
                    }
                ]
            )

            FakeCallGraphServiceImpl.init_calls = []
            FakeCallGraphServiceImpl.scanned_files = []
            FakeCallGraphServiceImpl.cache_stats_calls = 0
            with patch("mhc.callgraph.git.clone_and_checkout_commit"), \
                    patch("mhc.callgraph._collect_java_files", return_value=java_files), \
                    patch("mhc.callgraph.util.format_method_mapping_file", return_value=str(method_mapping_file)), \
                    patch("mhc.callgraph.util.format_class_mapping_file", return_value=str(class_mapping_file)), \
                    patch("jpype.JClass", return_value=FakeCallGraphServiceImpl):
                execute_callgraph_per_file(
                    repository_df,
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    max_cache_size=512,
                    merge_threshold=1,
                    merge_interval_seconds=0,
                    init_reset_interval_files=1,
                )

            expected_init = (
                "demo",
                "https://example.test/demo",
                str(repository_path),
                "abc123",
                str(method_mapping_file),
                str(class_mapping_file),
                None,
                False,
                512,
            )
            self.assertEqual([expected_init, expected_init], FakeCallGraphServiceImpl.init_calls)
            self.assertEqual(["src/Alpha.java", "src/Beta.java"], FakeCallGraphServiceImpl.scanned_files)
            self.assertGreaterEqual(FakeCallGraphServiceImpl.cache_stats_calls, 2)

    def test_execute_merge_only_does_not_load_jpype_scanner(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repository"
            data_directory = root / "data"
            workspace_directory = root / "workspace"
            repository_path = repository_directory / "demo"
            cache_file = workspace_directory / ".callgraph" / "demo.csv"
            cache_file.parent.mkdir(parents=True)
            pd.DataFrame(
                [_build_callgraph_scan_marker("src/Caller.java")],
                columns=CALLGRAPH_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)
            repository_df = pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "url": "https://example.test/demo",
                        "updated_hash": "abc123",
                    }
                ]
            )

            with patch("mhc.callgraph.git.clone_and_checkout_commit"), \
                    patch("mhc.callgraph._collect_java_files", return_value=[str(repository_path / "src" / "Caller.java")]), \
                    patch.dict(sys.modules, {"jpype": None}):
                execute_callgraph_per_file(
                    repository_df,
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    merge_only=True,
                )

            self.assertTrue((data_directory / "callgraph" / "demo.csv").exists())
            self.assertTrue((data_directory / "fanin" / "demo.csv").exists())


if __name__ == "__main__":
    unittest.main()
