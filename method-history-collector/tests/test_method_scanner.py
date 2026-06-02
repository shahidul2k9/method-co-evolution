import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
from git import GitCommandError

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

import mhc.method_scanner as ms
import mhc.util as util


class FakeJavaMethod:
    def __init__(self, repository_url: str, commit_hash: str, file_path: str):
        method_name = Path(file_path).stem
        self.name = f"{method_name}_method"
        self.url = util.format_to_git_url(repository_url, commit_hash, file_path, 1)
        self.artifact = "#main-code"
        self.start_line = 1
        self.end_line = 2
        self.expression = "method"
        self.file = file_path
        self.pkg = "demo.pkg"
        self.fqn = f"demo.pkg.{method_name}"
        self.fqs = f"{self.fqn}(java.lang.String)"
        self.tctracer_fqs = f"{self.fqn}(String)"
        self.testlinker_fqs = f"{self.fqn}(String)"
        self.testlinker_fqp = '["java.lang.String"]'
        self.abstract_method = 0
        self.hash = commit_hash
        self.resolver = "javaparser"

    def getName(self):
        return self.name

    def getUrl(self):
        return self.url

    def getArtifact(self):
        return self.artifact

    def getStartLine(self):
        return self.start_line

    def getEndLine(self):
        return self.end_line

    def getExpression(self):
        return self.expression

    def getFile(self):
        return self.file

    def getPkg(self):
        return self.pkg

    def getFqn(self):
        return self.fqn

    def getFqs(self):
        return self.fqs

    def getTcTracerFqs(self):
        return self.tctracer_fqs

    def getTestlinkerFqs(self):
        return self.testlinker_fqs

    def getTestlinkerFqp(self):
        return self.testlinker_fqp

    def getAbstractMethod(self):
        return self.abstract_method

    def getHash(self):
        return self.hash

    def getResolver(self):
        return self.resolver


class FakeMethodScannerImpl:
    init_calls = []
    scanned_files = []
    evict_calls = 0

    @staticmethod
    def getInstance():
        return FakeMethodScannerImpl()

    def init(self, repository_directory, repository_url, commit_hash, artifact_config_path, checkout_repository):
        FakeMethodScannerImpl.init_calls.append(
            (repository_directory, repository_url, commit_hash, artifact_config_path, checkout_repository)
        )

    def scanMethod(self, file_without_base):
        FakeMethodScannerImpl.scanned_files.append(file_without_base)
        _, repository_url, commit_hash, _, _ = FakeMethodScannerImpl.init_calls[-1]
        return [FakeJavaMethod(repository_url, commit_hash, file_without_base)]

    def evictCache(self):
        FakeMethodScannerImpl.evict_calls += 1


class MethodScannerCacheTestCase(unittest.TestCase):
    def test_error_markers_can_be_treated_as_completed_when_retry_disabled(self):
        cache_df = pd.DataFrame(
            [
                ms._build_scan_error_row(
                    "demo-project",
                    "src/Broken.java",
                    "abc123",
                    "parse failed",
                ),
                ms._build_scan_marker_row("demo-project", "src/Done.java", "abc123"),
            ],
            columns=ms.METHOD_SCAN_CACHE_COLUMNS,
        )

        self.assertEqual(
            {"src/Done.java"},
            ms._completed_method_scan_files(cache_df),
        )
        self.assertEqual(
            {"src/Broken.java", "src/Done.java"},
            ms._completed_method_scan_files(cache_df, retry_errors=False),
        )

    def test_should_flush_scan_cache_uses_threshold_or_time(self):
        now = 100.0
        with patch.object(ms.time, "monotonic", return_value=now):
            self.assertTrue(ms._should_flush_scan_cache(10, now, 10, 900))
            self.assertTrue(ms._should_flush_scan_cache(1, now - 901, 10, 900))
            self.assertFalse(ms._should_flush_scan_cache(1, now, 10, 900))
            self.assertFalse(ms._should_flush_scan_cache(10, now, 0, 0))
            self.assertFalse(ms._should_flush_scan_cache(10, now, -1, -1))

    def test_repository_start_logging_includes_diagnostic_context(self):
        with self.assertLogs(level="INFO") as logs:
            ms._log_scan_repository_start(
                "method-scan",
                "demo-project",
                "abc123",
                1,
                2,
                4,
                10000,
                900,
            )

        joined_logs = "\n".join(logs.output)
        self.assertIn("method-scan start project=demo-project", joined_logs)
        self.assertIn("shard=1/2", joined_logs)
        self.assertIn("max_workers=4", joined_logs)

    def test_progress_logging_reports_completed_files_and_pending_rows(self):
        with self.assertLogs(level="INFO") as logs:
            last_at, last_completed = ms._maybe_log_scan_progress(
                "method-scan",
                "demo-project",
                completed_files=100,
                total_files=250,
                pending_rows=1234,
                produced_rows=1500,
                error_count=2,
                started_at=10.0,
                last_progress_at=10.0,
                last_progress_completed=0,
            )

        self.assertEqual(100, last_completed)
        self.assertGreaterEqual(last_at, 10.0)
        joined_logs = "\n".join(logs.output)
        self.assertIn("completed_files=100/250", joined_logs)
        self.assertIn("pending_rows=1234", joined_logs)
        self.assertIn("errors=2", joined_logs)

    def test_flush_method_scan_buffers_logs_requested_and_appended_rows(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".method" / "demo-project.csv"
            lock_file = root / ".method" / "demo-project.lock"
            pending = [
                {
                    **ms._build_scan_marker_row("demo-project", "src/Alpha.java", "abc123"),
                    "name": None,
                }
            ]

            with self.assertLogs(level="INFO") as logs:
                ms._flush_method_scan_buffers(str(cache_file), str(lock_file), pending)

            self.assertEqual([], pending)
            joined_logs = "\n".join(logs.output)
            self.assertIn("method-scan flush rows_requested=1 rows_appended=1", joined_logs)
            self.assertIn(str(cache_file), joined_logs)

    def test_build_method_scanner_logs_worker_init_timing(self):
        FakeMethodScannerImpl.init_calls = []
        with self.assertLogs(level="INFO") as logs:
            ms._build_method_scanner(
                FakeMethodScannerImpl,
                "/tmp/demo-project",
                "https://github.com/example/demo-project",
                "abc123",
                None,
            )

        joined_logs = "\n".join(logs.output)
        self.assertIn("method-scan scanner-init start", joined_logs)
        self.assertIn("method-scan scanner-init finish", joined_logs)
        self.assertIn("elapsed_seconds=", joined_logs)

    def test_finalize_method_scan_outputs_removes_float_suffix_from_integer_columns(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".method" / "demo-project.csv"
            output_file = root / "method" / "demo-project.csv"
            error_file = root / ".method-error" / "demo-project.csv"
            cache_file.parent.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        **{col: None for col in ms.METHOD_SCAN_CACHE_COLUMNS},
                        "project": "demo-project",
                        "name": "run",
                        "url": "https://github.com/example/demo/blob/abc123/src/Alpha.java#L72",
                        "artifact": "#main-code",
                        "start_line": "72.0",
                        "end_line": 80.0,
                        "expression": "method",
                        "file": "src/Alpha.java",
                        "abstract": "0.0",
                        "hash": "abc123",
                    },
                    ms._build_scan_marker_row("demo-project", "src/Alpha.java", "abc123"),
                ],
                columns=ms.METHOD_SCAN_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = ms._finalize_method_scan_outputs(
                str(cache_file),
                str(output_file),
                str(error_file),
                {"src/Alpha.java"},
            )

            self.assertTrue(merged)
            output_text = output_file.read_text(encoding="utf-8")
            self.assertNotIn("72.0", output_text)
            self.assertNotIn("80.0", output_text)
            output_df = pd.read_csv(output_file, dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual("72", output_df.loc[0, "start_line"])
            self.assertEqual("80", output_df.loc[0, "end_line"])
            self.assertEqual("0", output_df.loc[0, "abstract"])

    def test_finalize_method_code_outputs_removes_float_suffix_from_integer_columns(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".method-code" / "demo-project.csv"
            output_file = root / "method-code" / "demo-project.csv"
            error_file = root / ".method-code-error" / "demo-project.csv"
            cache_file.parent.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "project": "demo-project",
                        "name": "run",
                        "url": "https://github.com/example/demo/blob/abc123/src/Alpha.java#L72",
                        "artifact": "#main-code",
                        "start_line": "72.0",
                        "end_line": 80.0,
                        "code": "void run() {}",
                        ms.METHOD_CODE_KEY_COLUMN: "key",
                        ms.METHOD_CODE_FLAG_COLUMN: None,
                        ms.METHOD_CODE_ERROR_COLUMN: None,
                    }
                ],
                columns=ms.METHOD_CODE_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = ms._finalize_method_code_outputs(
                str(cache_file),
                str(output_file),
                str(error_file),
                {"key"},
            )

            self.assertTrue(merged)
            output_text = output_file.read_text(encoding="utf-8")
            self.assertNotIn("72.0", output_text)
            output_df = pd.read_csv(output_file, dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual("72", output_df.loc[0, "start_line"])
            self.assertEqual("80", output_df.loc[0, "end_line"])

    def _repository_df(self) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "project": "demo-project",
                    "url": "https://github.com/example/demo-project",
                    "updated_hash": "abc123",
                }
            ]
        )

    def _create_java_file(self, file_path: Path) -> None:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text("class Demo { void run() {} }", encoding="utf-8")

    def test_clone_and_checkout_commit_retries_after_failed_clone(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            repository_directory = Path(temp_directory) / "demo-project"
            repo = MagicMock()
            repo.head.object.hexsha = "abc123"

            clone_calls: list[str] = []

            def clone_side_effect(_repo_url, target_directory, multi_options=None):
                clone_calls.append(target_directory)
                Path(target_directory).mkdir(parents=True, exist_ok=True)
                if len(clone_calls) == 1:
                    raise GitCommandError("clone", 128, stderr="early EOF")
                return repo

            with patch.object(ms.Repo, "clone_from", side_effect=clone_side_effect), patch.object(
                ms, "time"
            ) as mock_time:
                current_commit = ms.clone_and_checkout_commit(
                    "https://github.com/example/demo-project",
                    str(repository_directory),
                    "abc123",
                )

            self.assertEqual("abc123", current_commit)
            self.assertEqual(2, len(clone_calls))
            repo.git.fetch.assert_called_once_with("origin", "abc123", "--depth", "1")
            repo.git.checkout.assert_called_once_with("abc123")
            mock_time.sleep.assert_called_once()

    def test_scan_method_uses_method_cache_file_on_resume(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repositories"
            data_directory = root
            workspace_directory = root / "cache"
            project_directory = repository_directory / "demo-project"

            self._create_java_file(project_directory / "src" / "Alpha.java")
            self._create_java_file(project_directory / "src" / "Beta.java")

            repository_df = self._repository_df()
            output_method_file = Path(util.format_method_list_file(str(data_directory), "demo-project"))
            method_cache_file = workspace_directory / ".method" / "demo-project.csv"

            seed_rows = pd.DataFrame(
                [
                    {
                        "project": "demo-project",
                        "name": "Alpha_method",
                        "url": "https://github.com/example/demo-project/blob/abc123/src/Alpha.java#L1",
                        "artifact": "#main-code",
                        "start_line": 1,
                        "end_line": 2,
                        "expression": "method",
                        "file": "src/Alpha.java",
                        "pkg": "demo.pkg",
                        "fqn": "demo.pkg.Alpha",
                        "fqs": "demo.pkg.Alpha(java.lang.String)",
                        "tctracer_fqs": "demo.pkg.Alpha(String)",
                        "testlinker_fqs": "demo.pkg.Alpha(String)",
                        "testlinker_fqp": '["java.lang.String"]',
                        "abstract": 0,
                        "parser": "javaparser",
                        "resolver": "javaparser",
                        "hash": "abc123",
                    },
                    ms._build_scan_marker_row("demo-project", "src/Alpha.java", "abc123"),
                ]
            )
            method_cache_file.parent.mkdir(parents=True, exist_ok=True)
            seed_rows.to_csv(method_cache_file, index=False)

            FakeMethodScannerImpl.init_calls = []
            FakeMethodScannerImpl.scanned_files = []
            with patch("jpype.JClass", return_value=FakeMethodScannerImpl), patch.object(
                ms, "clone_and_checkout_commit"
            ):
                ms.scan_method(
                    repository_df,
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                )

            self.assertEqual(
                FakeMethodScannerImpl.init_calls,
                [
                    (
                        str(project_directory),
                        "https://github.com/example/demo-project",
                        "abc123",
                        None,
                        False,
                    )
                ],
            )
            self.assertEqual(FakeMethodScannerImpl.scanned_files, ["src/Beta.java"])
            self.assertFalse(method_cache_file.exists())
            self.assertTrue(output_method_file.exists())
            resumed_df = pd.read_csv(output_method_file)
            self.assertEqual(sorted(resumed_df["file"].tolist()), ["src/Alpha.java", "src/Beta.java"])
            self.assertNotIn(ms.METHOD_SCAN_FLAG_COLUMN, resumed_df.columns)

    def test_scan_method_appends_cache_before_completion(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repositories"
            data_directory = root
            workspace_directory = root / "cache"
            project_directory = repository_directory / "demo-project"

            self._create_java_file(project_directory / "src" / "Alpha.java")
            self._create_java_file(project_directory / "src" / "Beta.java")

            repository_df = self._repository_df()
            output_method_file = Path(util.format_method_list_file(str(data_directory), "demo-project"))
            FakeMethodScannerImpl.init_calls = []
            FakeMethodScannerImpl.scanned_files = []

            with patch("jpype.JClass", return_value=FakeMethodScannerImpl), patch.object(
                ms, "clone_and_checkout_commit"
            ), patch.object(
                ms, "_flush_method_scan_buffers", wraps=ms._flush_method_scan_buffers
            ) as flush_results:
                ms.scan_method(
                    repository_df,
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    merge_threshold=1,
                    merge_interval_seconds=0,
                )

            self.assertEqual(
                FakeMethodScannerImpl.init_calls,
                [
                    (
                        str(project_directory),
                        "https://github.com/example/demo-project",
                        "abc123",
                        None,
                        False,
                    )
                ],
            )
            self.assertGreaterEqual(flush_results.call_count, 3)
            self.assertTrue(output_method_file.exists())

    def test_scan_method_cache_eviction_disabled_by_default(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repositories"
            data_directory = root
            workspace_directory = root / "cache"
            project_directory = repository_directory / "demo-project"

            self._create_java_file(project_directory / "src" / "Alpha.java")
            self._create_java_file(project_directory / "src" / "Beta.java")

            FakeMethodScannerImpl.init_calls = []
            FakeMethodScannerImpl.scanned_files = []
            FakeMethodScannerImpl.evict_calls = 0
            with patch("jpype.JClass", return_value=FakeMethodScannerImpl), patch.object(
                ms, "clone_and_checkout_commit"
            ):
                ms.scan_method(
                    self._repository_df(),
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    merge_threshold=1,
                    merge_interval_seconds=0,
                )

            self.assertEqual(0, FakeMethodScannerImpl.evict_calls)

    def test_scan_method_evicts_cache_after_file_interval(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repositories"
            data_directory = root
            workspace_directory = root / "cache"
            project_directory = repository_directory / "demo-project"

            self._create_java_file(project_directory / "src" / "Alpha.java")
            self._create_java_file(project_directory / "src" / "Beta.java")

            FakeMethodScannerImpl.init_calls = []
            FakeMethodScannerImpl.scanned_files = []
            FakeMethodScannerImpl.evict_calls = 0
            with patch("jpype.JClass", return_value=FakeMethodScannerImpl), patch.object(
                ms, "clone_and_checkout_commit"
            ):
                ms.scan_method(
                    self._repository_df(),
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    cache_evict_interval_files=1,
                )

            self.assertEqual(2, FakeMethodScannerImpl.evict_calls)

    def test_scan_method_init_reset_interval_zero_reuses_scanner(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repositories"
            data_directory = root
            workspace_directory = root / "cache"
            project_directory = repository_directory / "demo-project"

            self._create_java_file(project_directory / "src" / "Alpha.java")
            self._create_java_file(project_directory / "src" / "Beta.java")

            FakeMethodScannerImpl.init_calls = []
            FakeMethodScannerImpl.scanned_files = []
            FakeMethodScannerImpl.evict_calls = 0
            with patch("jpype.JClass", return_value=FakeMethodScannerImpl), patch.object(
                ms, "clone_and_checkout_commit"
            ):
                ms.scan_method(
                    self._repository_df(),
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    init_reset_interval_files=0,
                )

            self.assertEqual(1, len(FakeMethodScannerImpl.init_calls))
            self.assertEqual(["src/Alpha.java", "src/Beta.java"], FakeMethodScannerImpl.scanned_files)

    def test_scan_method_init_reset_interval_rebuilds_scanner(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repositories"
            data_directory = root
            workspace_directory = root / "cache"
            project_directory = repository_directory / "demo-project"

            self._create_java_file(project_directory / "src" / "Alpha.java")
            self._create_java_file(project_directory / "src" / "Beta.java")

            FakeMethodScannerImpl.init_calls = []
            FakeMethodScannerImpl.scanned_files = []
            FakeMethodScannerImpl.evict_calls = 0
            with patch("jpype.JClass", return_value=FakeMethodScannerImpl), patch.object(
                ms, "clone_and_checkout_commit"
            ):
                ms.scan_method(
                    self._repository_df(),
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    init_reset_interval_files=1,
                )

            self.assertEqual(2, len(FakeMethodScannerImpl.init_calls))
            self.assertEqual(["src/Alpha.java", "src/Beta.java"], FakeMethodScannerImpl.scanned_files)

    def test_cache_evict_reason_uses_time_or_file_threshold(self):
        self.assertEqual(
            "files",
            ms._cache_evict_reason(10, 30, cache_evict_interval_files=10, cache_evict_interval_seconds=0),
        )
        self.assertEqual(
            "seconds",
            ms._cache_evict_reason(1, 300, cache_evict_interval_files=0, cache_evict_interval_seconds=300),
        )
        self.assertEqual(
            "files+seconds",
            ms._cache_evict_reason(10, 300, cache_evict_interval_files=10, cache_evict_interval_seconds=300),
        )
        self.assertIsNone(
            ms._cache_evict_reason(9, 299, cache_evict_interval_files=10, cache_evict_interval_seconds=300)
        )

    def test_evict_method_scanner_cache_swallows_errors(self):
        class BrokenScanner:
            def evictCache(self):
                raise RuntimeError("missing class")

        with self.assertLogs(level="INFO") as logs:
            success = ms._evict_method_scanner_cache(
                BrokenScanner(),
                "demo-project",
                "files",
                10,
                30.0,
            )

        self.assertFalse(success)
        self.assertIn("cache-evict finish project=demo-project success=False", "\n".join(logs.output))

    def test_scan_method_replace_ignores_existing_output(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repositories"
            data_directory = root
            workspace_directory = root / "cache"
            project_directory = repository_directory / "demo-project"

            self._create_java_file(project_directory / "src" / "Alpha.java")

            repository_df = self._repository_df()
            output_method_file = Path(util.format_method_list_file(str(data_directory), "demo-project"))
            output_method_file.parent.mkdir(parents=True, exist_ok=True)
            output_method_file.write_text("project,name,hash\nold,old,old\n", encoding="utf-8")

            FakeMethodScannerImpl.init_calls = []
            FakeMethodScannerImpl.scanned_files = []
            with patch("jpype.JClass", return_value=FakeMethodScannerImpl), patch.object(
                ms, "clone_and_checkout_commit"
            ):
                ms.scan_method(
                    repository_df,
                    str(repository_directory),
                    str(data_directory),
                    str(workspace_directory),
                    replace=True,
                )

            self.assertEqual(FakeMethodScannerImpl.scanned_files, ["src/Alpha.java"])
            regenerated_df = pd.read_csv(output_method_file)
            self.assertEqual(regenerated_df["project"].tolist(), ["demo-project"])

    def test_finalize_method_scan_writes_errors_and_deletes_cache_and_lock(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".method" / "demo-project.csv"
            lock_file = root / ".method" / "demo-project.lock"
            output_file = root / "method" / "demo-project.csv"
            error_file = root / ".method-error" / "demo-project.csv"
            cache_file.parent.mkdir(parents=True)
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [
                    {
                        **{col: None for col in ms.METHOD_SCAN_CACHE_COLUMNS},
                        "project": "demo-project",
                        "name": "Alpha_method",
                        "file": "src/Alpha.java",
                        "hash": "abc123",
                    },
                    ms._build_scan_error_row(
                        "demo-project",
                        "src/Broken.java",
                        "abc123",
                        "x" * 300,
                    ),
                ],
                columns=ms.METHOD_SCAN_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = ms._finalize_method_scan_outputs(
                str(cache_file),
                str(output_file),
                str(error_file),
                {"src/Alpha.java", "src/Broken.java"},
                str(lock_file),
            )

            self.assertTrue(merged)
            self.assertFalse(cache_file.exists())
            self.assertFalse(lock_file.exists())
            output_df = pd.read_csv(output_file)
            self.assertEqual(["src/Alpha.java"], output_df["file"].tolist())
            self.assertNotIn(ms.METHOD_SCAN_FLAG_COLUMN, output_df.columns)
            error_df = pd.read_csv(error_file)
            self.assertEqual(["src/Broken.java"], error_df["file"].tolist())
            self.assertEqual([ms.METHOD_SCAN_ERROR_MARKER], error_df[ms.METHOD_SCAN_FLAG_COLUMN].tolist())
            self.assertEqual(ms.METHOD_SCAN_ERROR_MAX_LENGTH, len(error_df[ms.METHOD_SCAN_ERROR_COLUMN].iloc[0]))

    def test_finalize_method_scan_waits_until_all_files_are_tried(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / ".method" / "demo-project.csv"
            lock_file = root / ".method" / "demo-project.lock"
            output_file = root / "method" / "demo-project.csv"
            error_file = root / ".method-error" / "demo-project.csv"
            cache_file.parent.mkdir(parents=True)
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [ms._build_scan_marker_row("demo-project", "src/Alpha.java", "abc123")],
                columns=ms.METHOD_SCAN_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = ms._finalize_method_scan_outputs(
                str(cache_file),
                str(output_file),
                str(error_file),
                {"src/Alpha.java", "src/Missing.java"},
                str(lock_file),
            )

            self.assertFalse(merged)
            self.assertTrue(cache_file.exists())
            self.assertTrue(lock_file.exists())
            self.assertFalse(output_file.exists())


if __name__ == "__main__":
    unittest.main()
