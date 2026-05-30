import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.test_smell import (
    SMELL_ACRONYMS,
    _ensure_repository_checkout,
    _execute_command,
    _postprocess_error_file,
    _resolve_test_smell_jar,
    _select_candidate,
    postprocess_project,
    preprocess_project,
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
            "callgraph",
        )

        self.assertEqual(1, len(result))
        row = result.iloc[0]
        self.assertEqual(
            str(self.repo / self.project / "src/test/java/acme/Foo.java"),
            row["pathToProductionFile"],
        )
        self.assertEqual(
            "https://github.com/acme/sample/blob/abc123/src/test/java/acme/FooTest.java#L1",
            row["from_url"],
        )
        self.assertEqual(
            "https://github.com/acme/sample/blob/abc123/src/test/java/acme/Foo.java#L1",
            row["to_url"],
        )
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

    def test_postprocess_splits_jnose_methods_and_maps_exact_method_urls(self):
        self._write_method_csv()
        raw_dir = self.data / ".test-smell" / "jnose" / "output"
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
