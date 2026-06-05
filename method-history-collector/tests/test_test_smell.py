import io
import json
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.test_smell import (
    SMELL_ACRONYMS,
    _bridge_file,
    _ensure_repository_checkout,
    _execute_command,
    _adapter_input_file_path,
    _download_adapter_input_file,
    _input_file,
    _postprocess_file,
    _postprocess_error_file,
    _resolve_test_smell_jar,
    _select_candidate,
    postprocess_project,
    postprocess_strategy_project,
    preprocess_project,
    preprocess_strategy_project,
    run_test_smell,
)


class TestSmellWorkflowTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.data = self.root / "experiment"
        self.repo = self.root / "repository"
        self.project = "sample"
        (self.data / "method").mkdir(parents=True)
        (self.data / "callgraph").mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _repository(self):
        return pd.Series(
            {
                "project": self.project,
                "url": "https://github.com/acme/sample",
                "updated_hash": "abc123",
            }
        )

    def _write_method_csv(self):
        pd.DataFrame(
            [
                {
                    "project": self.project,
                    "name": "testFoo",
                    "url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "artifact": "#test-code #test-case-method",
                    "start_line": "10",
                    "end_line": "20",
                    "expression": "method",
                    "pkg": "acme",
                    "fqn": "acme.FooTest.testFoo",
                    "fqs": "acme.FooTest.testFoo()",
                    "fqs_alt": "acme.FooTest.testFoo()",
                    "file": "src/test/java/acme/FooTest.java",
                    "hash": "abc123",
                    "parser": "javaparser",
                },
                {
                    "project": self.project,
                    "name": "barHelper",
                    "url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/BarHelper.java#L7",
                    "artifact": "#test-code #test-helper-method",
                    "start_line": "7",
                    "end_line": "8",
                    "expression": "method",
                    "pkg": "acme",
                    "fqn": "acme.BarHelper.barHelper",
                    "fqs": "acme.BarHelper.barHelper()",
                    "fqs_alt": "acme.BarHelper.barHelper()",
                    "file": "src/test/java/acme/BarHelper.java",
                    "hash": "abc123",
                    "parser": "javaparser",
                },
                {
                    "project": self.project,
                    "name": "foo",
                    "url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/Foo.java#L7",
                    "artifact": "#test-code #test-helper-method",
                    "start_line": "7",
                    "end_line": "8",
                    "expression": "method",
                    "pkg": "acme",
                    "fqn": "acme.Foo.foo",
                    "fqs": "acme.Foo.foo()",
                    "fqs_alt": "acme.Foo.foo()",
                    "file": "src/test/java/acme/Foo.java",
                    "hash": "abc123",
                    "parser": "javaparser",
                },
                {
                    "project": self.project,
                    "name": "helper",
                    "url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/TestHelper.java#L7",
                    "artifact": "#test-code #test-helper-method",
                    "start_line": "7",
                    "end_line": "8",
                    "expression": "method",
                    "pkg": "acme",
                    "fqn": "acme.TestHelper.helper",
                    "fqs": "acme.TestHelper.helper()",
                    "fqs_alt": "acme.TestHelper.helper()",
                    "file": "src/test/java/acme/TestHelper.java",
                    "hash": "abc123",
                    "parser": "javaparser",
                },
            ]
        ).to_csv(self.data / "method" / f"{self.project}.csv", index=False)

    def _write_callgraph_csv(self, project: str | None = None):
        project = project or self.project
        pd.DataFrame(
            [
                {
                    "project": project,
                    "from_url": f"https://github.com/acme/{project}/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": f"https://github.com/acme/{project}/blob/abc123/src/test/java/acme/Foo.java#L7",
                    "from_file": "src/test/java/acme/FooTest.java",
                    "to_file": "src/test/java/acme/Foo.java",
                    "from_fqs": "acme.FooTest.testFoo()",
                    "to_fqs": "acme.Foo.foo()",
                },
            ]
        ).to_csv(self.data / "callgraph" / f"{project}.csv", index=False)

    def _write_minimal_method_csv(self, project: str):
        pd.DataFrame(
            [
                {
                    "project": project,
                    "name": "testFoo",
                    "url": f"https://github.com/acme/{project}/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "artifact": "#test-code #test-case-method",
                    "fqs": "acme.FooTest.testFoo()",
                    "file": "src/test/java/acme/FooTest.java",
                },
                {
                    "project": project,
                    "name": "foo",
                    "url": f"https://github.com/acme/{project}/blob/abc123/src/test/java/acme/Foo.java#L7",
                    "artifact": "#test-code #test-helper-method",
                    "fqs": "acme.Foo.foo()",
                    "file": "src/test/java/acme/Foo.java",
                },
            ]
        ).to_csv(self.data / "method" / f"{project}.csv", index=False)

    def _write_history_archive(self, histories: list[dict], project: str | None = None):
        project = project or self.project
        archive = self.data / "method-history-gz" / "historyFinder" / f"{project}.tar.gz"
        archive.parent.mkdir(parents=True)
        with tarfile.open(archive, "w:gz") as tar:
            for index, history in enumerate(histories):
                payload = json.dumps(history).encode("utf-8")
                info = tarfile.TarInfo(f"history-{index}.json")
                info.size = len(payload)
                tar.addfile(info, io.BytesIO(payload))

    def _history(self, file_path: str, method_name: str, details: dict[str, dict]) -> dict:
        return {
            "sourceFilePath": file_path,
            "functionName": method_name,
            "changeHistory": list(details),
            "changeHistoryDetails": details,
        }

    def _detail(self, commit: str, file_path: str, method_name: str, change_type: str = "Yintroduced") -> dict:
        return {
            "commitName": commit,
            "type": change_type,
            "newFileUrl": f"https://github.com/acme/sample/blob/{commit}/{file_path}#L10",
            "extendedDetails": {"newMethodName": method_name, "newPath": file_path},
            "path": file_path,
        }

    def test_preprocess_filters_tags_and_prefers_exact_name_match(self):
        self._write_method_csv()
        pd.DataFrame(
            [
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/BarHelper.java#L7",
                    "from_file": "src/test/java/acme/FooTest.java",
                    "to_file": "src/test/java/acme/BarHelper.java",
                    "from_fqs": "acme.FooTest.testFoo()",
                    "to_fqs": "acme.BarHelper.barHelper()",
                },
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/Foo.java#L7",
                    "from_file": "src/test/java/acme/FooTest.java",
                    "to_file": "src/test/java/acme/Foo.java",
                    "from_fqs": "acme.FooTest.testFoo()",
                    "to_fqs": "acme.Foo.foo()",
                },
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/TestHelper.java#L7",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/Foo.java#L7",
                    "from_file": "src/test/java/acme/TestHelper.java",
                    "to_file": "src/test/java/acme/Foo.java",
                    "from_fqs": "acme.TestHelper.helper()",
                    "to_fqs": "acme.Foo.foo()",
                },
            ]
        ).to_csv(self.data / "callgraph" / f"{self.project}.csv", index=False)

        result = preprocess_project(
            self._repository(),
            str(self.repo),
            str(self.data),
        )

        self.assertEqual(1, len(result))
        row = result.iloc[0]
        self.assertEqual("", row["pathToProductionFile"])
        self.assertEqual(
            "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L1",
            row["from_url"],
        )
        self.assertEqual("", row["to_url"])
        self.assertEqual(2, int(row["candidateCount"]))
        self.assertEqual(1.0, float(row["confidence"]))

    def test_select_candidate_ranks_by_fqs_similarity_when_no_exact_name_match(self):
        rows = pd.DataFrame(
            [
                {
                    "to_file": "src/main/java/acme/Remote.java",
                    "from_fqs": "acme.FooTest.testFoo()",
                    "to_fqs": "acme.Remote.call()",
                },
                {
                    "to_file": "src/main/java/acme/FooService.java",
                    "from_fqs": "acme.FooTest.testFoo()",
                    "to_fqs": "acme.FooService.testFoo()",
                },
            ]
        )

        selected = _select_candidate("src/test/java/acme/FooTest.java", rows)

        self.assertEqual("src/main/java/acme/FooService.java", selected["to_file"])
        self.assertEqual(2, selected["candidate_count"])
        self.assertGreater(selected["confidence"], 0)

    def test_preprocess_skips_missing_method_csv(self):
        with self.assertLogs(level="WARNING") as logs:
            result = preprocess_project(
                self._repository(),
                str(self.repo),
                str(self.data),
            )

        self.assertIsNone(result)
        self.assertIn("method CSV not found", "\n".join(logs.output))

    def test_preprocess_skips_missing_callgraph_csv(self):
        self._write_method_csv()

        with self.assertLogs(level="WARNING") as logs:
            result = preprocess_project(
                self._repository(),
                str(self.repo),
                str(self.data),
            )

        self.assertIsNone(result)
        self.assertIn("callgraph CSV not found", "\n".join(logs.output))

    def test_run_skips_precomputed_output_without_replace(self):
        output_file = _postprocess_file(str(self.data), self.project)
        output_file.parent.mkdir(parents=True)
        output_file.write_text("project,name,smell,smell_detector,url,smell_begin,smell_end\n")
        repository_df = pd.DataFrame([self._repository()])

        with (
            self.assertLogs(level="INFO") as logs,
            patch("mhc.test_smell.preprocess_project") as mock_preprocess,
            patch("mhc.test_smell.execute_project") as mock_execute,
            patch("mhc.test_smell.postprocess_project") as mock_postprocess,
        ):
            run_test_smell(
                repository_df,
                str(self.repo),
                str(self.data),
                {"jnose": "/tmp/jnose.jar"},
                [self.project],
                "jnose",
            )

        self.assertIn("precomputed output already exists", "\n".join(logs.output))
        mock_preprocess.assert_not_called()
        mock_execute.assert_not_called()
        mock_postprocess.assert_not_called()

    def test_run_does_not_skip_precomputed_output_with_replace(self):
        output_file = _postprocess_file(str(self.data), self.project)
        output_file.parent.mkdir(parents=True)
        output_file.write_text("project,name,smell,smell_detector,url,smell_begin,smell_end\n")
        repository_df = pd.DataFrame([self._repository()])

        with (
            patch("mhc.test_smell.preprocess_project", return_value=pd.DataFrame()) as mock_preprocess,
            patch("mhc.test_smell._ensure_repository_checkout") as mock_checkout,
            patch("mhc.test_smell.execute_project") as mock_execute,
            patch("mhc.test_smell.postprocess_project") as mock_postprocess,
        ):
            run_test_smell(
                repository_df,
                str(self.repo),
                str(self.data),
                {"jnose": "/tmp/jnose.jar"},
                [self.project],
                "jnose",
                replace=True,
            )

        mock_preprocess.assert_called_once()
        mock_checkout.assert_called_once()
        mock_execute.assert_called_once()
        mock_postprocess.assert_called_once()

    def test_run_continues_when_one_project_dependency_is_missing(self):
        valid_project = "valid"
        self._write_minimal_method_csv(valid_project)
        self._write_callgraph_csv(valid_project)
        repository_df = pd.DataFrame(
            [
                self._repository().to_dict(),
                {
                    "project": valid_project,
                    "url": f"https://github.com/acme/{valid_project}",
                    "updated_hash": "abc123",
                },
            ]
        )

        run_test_smell(
            repository_df,
            str(self.repo),
            str(self.data),
            {"jnose": "/tmp/jnose.jar"},
            [self.project, valid_project],
            "jnose",
            stage="preprocess",
        )

        self.assertFalse(_input_file(str(self.data), self.project).exists())
        self.assertTrue(_input_file(str(self.data), valid_project).exists())

    def test_postprocess_splits_jnose_methods_and_maps_exact_method_urls(self):
        self._write_method_csv()
        raw_dir = self.data / ".test-smell" / "jnose" / "callgraph" / "jnose-adapter-output"
        raw_dir.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "projectName": self.project,
                    "name": "FooTest",
                    "pathFile": str(self.repo / self.project / "src/test/java/acme/FooTest.java"),
                    "productionFile": str(self.repo / self.project / "src/test/java/acme/Foo.java"),
                    "junitVersion": "JUnit4",
                    "loc": "20",
                    "qtdMethods": "1",
                    "testSmellName": "Lazy Test",
                    "testSmellMethod": "testFoo, missingMethod",
                    "testSmellLineBegin": "10, 12",
                    "testSmellLineEnd": "10, 12",
                }
            ]
        ).to_csv(raw_dir / f"{self.project}.csv", sep=";", index=False)

        result = postprocess_project(self._repository(), str(self.data))

        self.assertEqual(["LT"], result["smell"].tolist())
        self.assertEqual(["jnose"], result["smell_detector"].tolist())
        self.assertEqual(["testFoo"], result["name"].tolist())
        self.assertTrue(result["url"].str.endswith("#L10").all())
        self.assertEqual(["10, 12"], result["smell_begin"].tolist())
        self.assertEqual(["10, 12"], result["smell_end"].tolist())

        errors = pd.read_csv(_postprocess_error_file(str(self.data), self.project), dtype=str)
        self.assertEqual(["missingMethod"], errors["testSmellMethod"].tolist())
        self.assertIn("No exact method match", errors["reason"].iloc[0])

    def test_strategy_preprocess_builds_bridge_and_adapter_input(self):
        strategy = "nc"
        (self.data / "t2p-link" / strategy).mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/main/java/acme/Foo.java#L20",
                    "from_name": "testFoo",
                    "to_name": "foo",
                },
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/main/java/acme/Foo.java#L20",
                    "from_name": "testFoo",
                    "to_name": "foo",
                },
            ]
        ).to_csv(self.data / "t2p-link" / strategy / f"{self.project}.csv", index=False)
        intro_commit = "intro123"
        self._write_history_archive(
            [
                self._history(
                    "src/test/java/acme/FooTest.java",
                    "testFoo",
                    {
                        "later456": self._detail("later456", "src/test/java/acme/FooTest.java", "testFoo", "Ybodychange"),
                        intro_commit: self._detail(intro_commit, "src/test/java/acme/FooTest.java", "testFooOld"),
                    },
                ),
                self._history(
                    "src/main/java/acme/Foo.java",
                    "foo",
                    {intro_commit: self._detail(intro_commit, "src/main/java/acme/Foo.java", "fooOld")},
                ),
            ]
        )

        with patch("mhc.test_smell.urlopen") as mock_urlopen:
            response = MagicMock()
            response.read.return_value = b"class Source {}"
            mock_urlopen.return_value.__enter__.return_value = response
            result = preprocess_strategy_project(self._repository(), str(self.data), strategy)

        self.assertEqual(1, len(result))
        row = result.iloc[0]
        self.assertIn(f"adapter-input-file/{self.project}/{intro_commit}/src/test/java/acme/FooTest.java", row["pathToTestFile"])
        self.assertIn(f"adapter-input-file/{self.project}/{intro_commit}/src/main/java/acme/Foo.java", row["pathToProductionFile"])

        bridge = pd.read_csv(_bridge_file(str(self.data), self.project, strategy), dtype=str)
        self.assertEqual(1, len(bridge))
        self.assertEqual(["testFooOld"], bridge["from_old_name"].tolist())
        self.assertEqual(["fooOld"], bridge["to_old_name"].tolist())

    def test_strategy_preprocess_falls_back_to_last_entry_and_clears_ambiguous_production_file(self):
        strategy = "nc"
        (self.data / "t2p-link" / strategy).mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/main/java/acme/Foo.java#L20",
                    "from_name": "testFoo",
                    "to_name": "foo",
                },
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/main/java/acme/Bar.java#L30",
                    "from_name": "testFoo",
                    "to_name": "bar",
                },
            ]
        ).to_csv(self.data / "t2p-link" / strategy / f"{self.project}.csv", index=False)
        fallback_commit = "fallback123"
        self._write_history_archive(
            [
                self._history(
                    "src/test/java/acme/FooTest.java",
                    "testFoo",
                    {
                        "first456": self._detail("first456", "src/test/java/acme/FooTest.java", "testFooOld", "Ybodychange"),
                        fallback_commit: self._detail(fallback_commit, "src/test/java/acme/FooTest.java", "testFooOld", "Yrename"),
                    },
                ),
                self._history(
                    "src/main/java/acme/Foo.java",
                    "foo",
                    {fallback_commit: self._detail(fallback_commit, "src/main/java/acme/Foo.java", "fooOld")},
                ),
                self._history(
                    "src/main/java/acme/Bar.java",
                    "bar",
                    {fallback_commit: self._detail(fallback_commit, "src/main/java/acme/Bar.java", "barOld")},
                ),
            ]
        )

        with patch("mhc.test_smell.urlopen") as mock_urlopen:
            response = MagicMock()
            response.read.return_value = b"class Source {}"
            mock_urlopen.return_value.__enter__.return_value = response
            result = preprocess_strategy_project(self._repository(), str(self.data), strategy)

        self.assertEqual(1, len(result))
        self.assertEqual("", result.iloc[0]["pathToProductionFile"])
        self.assertIn(fallback_commit, result.iloc[0]["pathToTestFile"])

    def test_strategy_postprocess_maps_old_method_to_current_method_and_warns_on_multiple_matches(self):
        strategy = "nc"
        old_path = _adapter_input_file_path(
            str(self.data),
            strategy,
            self.project,
            "https://github.com/acme/sample/blob/intro/src/test/java/acme/FooTest.java#L10",
        )
        raw_dir = self.data / ".test-smell" / "jnose" / strategy / "jnose-adapter-output"
        raw_dir.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "projectName": self.project,
                    "name": "FooTest",
                    "pathFile": str(old_path),
                    "productionFile": "",
                    "junitVersion": "JUnit4",
                    "loc": "20",
                    "qtdMethods": "1",
                    "testSmellName": "Lazy Test",
                    "testSmellMethod": "testFooOld, missingOld",
                    "testSmellLineBegin": "10",
                    "testSmellLineEnd": "10",
                }
            ]
        ).to_csv(raw_dir / f"{self.project}.csv", sep=";", index=False)
        bridge_file = _bridge_file(str(self.data), self.project, strategy)
        bridge_file.parent.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/main/java/acme/Foo.java#L20",
                    "from_old_url": "https://github.com/acme/sample/blob/intro/src/test/java/acme/FooTest.java#L10",
                    "to_old_url": "",
                    "from_name": "testFoo",
                    "to_name": "foo",
                    "from_old_name": "testFooOld",
                    "to_old_name": "",
                },
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/main/java/acme/Bar.java#L30",
                    "from_old_url": "https://github.com/acme/sample/blob/intro/src/test/java/acme/FooTest.java#L10",
                    "to_old_url": "",
                    "from_name": "testFoo",
                    "to_name": "bar",
                    "from_old_name": "testFooOld",
                    "to_old_name": "",
                },
            ],
            columns=[
                "project",
                "from_url",
                "to_url",
                "from_old_url",
                "to_old_url",
                "from_name",
                "to_name",
                "from_old_name",
                "to_old_name",
            ],
        ).to_csv(bridge_file, index=False)

        with self.assertLogs(level="WARNING") as logs:
            result = postprocess_strategy_project(self._repository(), str(self.data), strategy)

        self.assertIn("Multiple t2p-link bridge rows matched", "\n".join(logs.output))
        self.assertEqual(["LT", "LT"], result["smell"].tolist())
        self.assertEqual(["testFoo", "testFoo"], result["name"].tolist())
        errors = pd.read_csv(_postprocess_error_file(str(self.data), self.project, strategy), dtype=str)
        self.assertEqual(["missingOld"], errors["testSmellMethod"].tolist())
        self.assertIn("in ", errors["reason"].iloc[0])

    def test_strategy_postprocess_matches_old_file_before_method_name(self):
        strategy = "nc"
        bar_old_url = "https://github.com/acme/sample/blob/barintro/src/test/java/acme/BarTest.java#L15"
        raw_dir = self.data / ".test-smell" / "jnose" / strategy / "jnose-adapter-output"
        raw_dir.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "projectName": self.project,
                    "name": "BarTest",
                    "pathFile": str(_adapter_input_file_path(str(self.data), strategy, self.project, bar_old_url)),
                    "productionFile": "",
                    "junitVersion": "JUnit4",
                    "loc": "20",
                    "qtdMethods": "1",
                    "testSmellName": "Lazy Test",
                    "testSmellMethod": "testSameOld",
                    "testSmellLineBegin": "15",
                    "testSmellLineEnd": "15",
                }
            ]
        ).to_csv(raw_dir / f"{self.project}.csv", sep=";", index=False)
        bridge_file = _bridge_file(str(self.data), self.project, strategy)
        bridge_file.parent.mkdir(parents=True)
        pd.DataFrame(
            [
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L10",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/main/java/acme/Foo.java#L20",
                    "from_old_url": "https://github.com/acme/sample/blob/foointro/src/test/java/acme/FooTest.java#L10",
                    "to_old_url": "",
                    "from_name": "testFoo",
                    "to_name": "foo",
                    "from_old_name": "testSameOld",
                    "to_old_name": "",
                },
                {
                    "project": self.project,
                    "from_url": "https://github.com/acme/sample/blob/abc123/src/test/java/acme/BarTest.java#L15",
                    "to_url": "https://github.com/acme/sample/blob/abc123/src/main/java/acme/Bar.java#L30",
                    "from_old_url": bar_old_url,
                    "to_old_url": "",
                    "from_name": "testBar",
                    "to_name": "bar",
                    "from_old_name": "testSameOld",
                    "to_old_name": "",
                },
            ],
            columns=[
                "project",
                "from_url",
                "to_url",
                "from_old_url",
                "to_old_url",
                "from_name",
                "to_name",
                "from_old_name",
                "to_old_name",
            ],
        ).to_csv(bridge_file, index=False)

        result = postprocess_strategy_project(self._repository(), str(self.data), strategy)

        self.assertEqual(["testBar"], result["name"].tolist())
        self.assertEqual(
            ["https://github.com/acme/sample/blob/abc123/src/test/java/acme/BarTest.java#L15"],
            result["url"].tolist(),
        )
        errors = pd.read_csv(_postprocess_error_file(str(self.data), self.project, strategy), dtype=str)
        self.assertTrue(errors.empty)


class TestSmellHelpersTest(unittest.TestCase):
    def test_smell_mapping_includes_tsdetector_aliases(self):
        self.assertEqual("EH", SMELL_ACRONYMS["Exception Catching Throwing"])
        self.assertEqual("EH", SMELL_ACRONYMS["Exception Handling"])
        self.assertEqual("RP", SMELL_ACRONYMS["Print Statement"])
        self.assertEqual("RP", SMELL_ACRONYMS["Redundant Print"])

    def test_resolve_jar_accepts_jnose_tool_keys(self):
        self.assertEqual("/tmp/jnose.jar", _resolve_test_smell_jar({"jnose": "/tmp/jnose.jar"}))
        self.assertEqual(
            "/tmp/JNose.jar",
            _resolve_test_smell_jar({"JNose": "/tmp/JNose.jar"}),
        )

    def test_ensure_repository_checkout_skips_existing_checkout(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo_dir = Path(tmp)
            (repo_dir / "sample").mkdir()
            _ensure_repository_checkout(
                pd.Series({"project": "sample", "url": "", "updated_hash": ""}),
                str(repo_dir),
            )

    def test_execute_command_shape(self):
        self.assertEqual(
            [
                "java",
                "-jar",
                "/jar/test.jar",
                "--file",
                "/input.csv",
                "--output",
                "/output.csv",
            ],
            _execute_command(
                "/jar/test.jar",
                Path("/input.csv"),
                Path("/output.csv"),
            ),
        )


if __name__ == "__main__":
    unittest.main()
    _execute_command,
