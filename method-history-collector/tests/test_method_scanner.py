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
        self.artifact = "production"
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

    @staticmethod
    def getInstance():
        return FakeMethodScannerImpl()

    def init(self, repository_directory, repository_url, commit_hash):
        FakeMethodScannerImpl.init_calls.append(
            (repository_directory, repository_url, commit_hash)
        )

    def scanMethod(self, file_without_base):
        FakeMethodScannerImpl.scanned_files.append(file_without_base)
        _, repository_url, commit_hash = FakeMethodScannerImpl.init_calls[-1]
        return [FakeJavaMethod(repository_url, commit_hash, file_without_base)]


class MethodScannerCacheTestCase(unittest.TestCase):
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
            data_directory = root / "data"
            workspace_directory = root / "cache"
            project_directory = repository_directory / "demo-project"

            self._create_java_file(project_directory / "src" / "Alpha.java")
            self._create_java_file(project_directory / "src" / "Beta.java")

            repository_df = self._repository_df()
            output_method_file = Path(util.format_method_list_file(str(data_directory), "demo-project"))
            method_cache_file = workspace_directory / "data" / ".method" / "demo-project.csv"

            seed_rows = pd.DataFrame(
                [
                    {
                        "project": "demo-project",
                        "name": "Alpha_method",
                        "url": "https://github.com/example/demo-project/blob/abc123/src/Alpha.java#L1",
                        "artifact": "production",
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
            data_directory = root / "data"
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
                ms, "SCAN_METHOD_FLUSH_INTERVAL_SECONDS", 0
            ), patch.object(
                ms, "_flush_method_scan_buffers", wraps=ms._flush_method_scan_buffers
            ) as flush_results:
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
                    )
                ],
            )
            self.assertGreaterEqual(flush_results.call_count, 3)
            self.assertTrue(output_method_file.exists())

    def test_scan_method_replace_ignores_existing_output(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            repository_directory = root / "repositories"
            data_directory = root / "data"
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
            output_file = root / "data" / "method" / "demo-project.csv"
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
            output_file = root / "data" / "method" / "demo-project.csv"
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
