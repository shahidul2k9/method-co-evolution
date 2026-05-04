from pathlib import Path
import json
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

from ptc.testlinker.execute import execute_project
from ptc.testlinker import main as testlinker_main
from ptc.testlinker.convert_author_results import convert_author_result_directory
from ptc.testlinker.model import _build_roberta_tokenizer_from_files
from ptc.testlinker.paths import (
    execute_csv_path,
    final_prediction_path,
    input_csv_path,
    mapped_input_json_directory,
    raw_detail_path,
    raw_input_json_directory,
)
from ptc.testlinker.postprocess import postprocess_project
from ptc.testlinker.preprocess import preprocess_project


@unittest.skipIf(pd is None, "pandas is required for TestLinker tests")
class TestTestLinkerPipeline(unittest.TestCase):
    def test_main_project_range_selects_repository_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            repository_dir = cache_dir / "data" / "repository"
            repository_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {"project": "commons-io"},
                    {"project": "commons-lang"},
                    {"project": "gson"},
                ]
            ).to_csv(repository_dir / "repository.csv", index=False)

            with mock.patch(
                "ptc.testlinker.main.preprocess_project",
                side_effect=lambda **_: pd.DataFrame([{}]),
            ) as preprocess:
                with mock.patch.object(
                    sys,
                    "argv",
                    [
                        "ptc-testlinker",
                        "testlinker",
                        "--stage",
                        "preprocess",
                        "--cache-directory",
                        str(cache_dir),
                        "--project-range",
                        "2:",
                    ],
                ):
                    self.assertEqual(0, testlinker_main.main())

            self.assertEqual(
                ["commons-lang", "gson"],
                [call.kwargs["project"] for call in preprocess.call_args_list],
            )

    def test_tokenizer_fallback_uses_installed_constructor_parameter_names(self):
        class NewTokenizer:
            def __init__(self, vocab=None, merges=None, **kwargs):
                self.vocab = vocab
                self.merges = merges
                self.kwargs = kwargs

        class OldTokenizer:
            def __init__(self, vocab_file=None, merges_file=None, **kwargs):
                self.vocab_file = vocab_file
                self.merges_file = merges_file
                self.kwargs = kwargs

        with mock.patch("transformers.RobertaTokenizer", NewTokenizer):
            tokenizer = _build_roberta_tokenizer_from_files("vocab.json", "merges.txt")
            self.assertEqual("vocab.json", tokenizer.vocab)
            self.assertEqual("merges.txt", tokenizer.merges)

        with mock.patch("transformers.RobertaTokenizer", OldTokenizer):
            tokenizer = _build_roberta_tokenizer_from_files("vocab.json", "merges.txt")
            self.assertEqual("vocab.json", tokenizer.vocab_file)
            self.assertEqual("merges.txt", tokenizer.merges_file)

    def test_preprocess_groups_candidates_by_test_url(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            data_dir = cache_dir / "data"
            (data_dir / "t2p-candidate").mkdir(parents=True)
            (data_dir / "method-code").mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_url": "test://A.testCopy",
                        "from_name": "testCopy",
                        "from_file": "src/test/A.java",
                        "from_fqn": "demo.ATest.testCopy",
                        "to_url": "prod://A.copy",
                        "to_name": "copy",
                        "to_tctracer_fqs": "demo.A.copy(String)",
                    },
                    {
                        "project": "demo",
                        "from_url": "test://A.testCopy",
                        "from_name": "testCopy",
                        "from_file": "src/test/A.java",
                        "from_fqn": "demo.ATest.testCopy",
                        "to_url": "prod://A.format",
                        "to_name": "format",
                        "to_tctracer_fqs": "demo.A.format(int)",
                    },
                ]
            ).to_csv(data_dir / "t2p-candidate" / "demo.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "name": "testCopy",
                        "url": "test://A.testCopy",
                        "artifact": "test",
                        "start_line": 1,
                        "end_line": 3,
                        "code": "void testCopy() { copy(\"x\"); }",
                    }
                ]
            ).to_csv(data_dir / "method-code" / "demo.csv", index=False)

            result_df = preprocess_project(cache_directory=cache_dir, project="demo")

            self.assertEqual(2, len(result_df))
            self.assertEqual(["000001", "000001"], result_df["test_id"].tolist())
            self.assertEqual('{ copy("x"); }', result_df.loc[0, "body"])
            self.assertEqual(["copy", "format"], result_df["invocation"].tolist())
            self.assertEqual(["demo.A.copy(String)", "demo.A.format(int)"], result_df["signature"].tolist())
            self.assertEqual([0, 0], result_df["label"].tolist())
            self.assertTrue(input_csv_path(cache_dir / "testlinker", "demo").exists())

    def test_convert_author_results_expands_invocations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "result"
            input_dir.mkdir()
            (input_dir / "demo_detail.json").write_text(
                json.dumps(
                    {
                        "id": "1",
                        "test_name": "testCopy",
                        "invocations": ["format", "copy"],
                        "sorted_invocations": ["copy", "format"],
                        "signatures": {"demo.A.unused()": {"detail_sigs": ["demo.A.unused()"]}},
                        "labels": ["demo.A.copy(String)"],
                        "recom_signatures": ["demo.A.copy(String)"],
                        "recom_by": "model",
                        "is_recom_all": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output_files = convert_author_result_directory(input_directory=input_dir)
            result_df = pd.read_csv(output_files[0])

            self.assertEqual(["format", "copy"], result_df["invocation"].tolist())
            self.assertEqual([2, 1], result_df["sorted_rank"].tolist())
            self.assertEqual([0, 1], result_df["label"].tolist())
            self.assertEqual([0, 1], result_df["pred_label"].tolist())
            self.assertNotIn("signature", result_df.columns)
            self.assertNotIn("params_json", result_df.columns)

    def test_convert_author_results_repeats_invocation_for_each_recommended_signature(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            input_dir = Path(tmpdir) / "result"
            input_dir.mkdir()
            (input_dir / "demo_detail.json").write_text(
                json.dumps(
                    {
                        "id": "1",
                        "test_name": "testGetName",
                        "invocations": ["getName"],
                        "sorted_invocations": ["getName"],
                        "signatures": {"demo.A.unused()": {"detail_sigs": ["demo.A.unused()"]}},
                        "labels": ["demo.A.getName(Class, String)", "demo.A.getName(Object, String)"],
                        "recom_signatures": ["demo.A.getName(Class, String)", "demo.A.getName(Object, String)"],
                        "recom_by": "model",
                        "is_recom_all": True,
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            output_files = convert_author_result_directory(input_directory=input_dir)
            result_df = pd.read_csv(output_files[0])

            self.assertEqual(
                ["demo.A.getName(Class, String)", "demo.A.getName(Object, String)"],
                result_df["recom_signature"].tolist(),
            )
            self.assertEqual(["getName", "getName"], result_df["invocation"].tolist())
            self.assertEqual([1, 1], result_df["label"].tolist())
            self.assertEqual([1, 1], result_df["pred_label"].tolist())
            self.assertNotIn("recom_signatures", result_df.columns)
            self.assertNotIn("recom_signatures_json", result_df.columns)

    def test_preprocess_can_use_author_invocation_order(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            data_dir = cache_dir / "data"
            author_result_dir = cache_dir / "testlinker"
            (data_dir / "t2p-candidate").mkdir(parents=True)
            (data_dir / "method-code").mkdir(parents=True)
            author_result_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_url": "test://A.testCopy",
                        "from_name": "testCopy",
                        "from_file": "src/test/A.java",
                        "from_fqn": "demo.ATest.testCopy",
                        "to_url": "prod://A.copy",
                        "to_name": "copy",
                        "to_tctracer_fqs": "demo.A.copy(String)",
                    },
                    {
                        "project": "demo",
                        "from_url": "test://A.testCopy",
                        "from_name": "testCopy",
                        "from_file": "src/test/A.java",
                        "from_fqn": "demo.ATest.testCopy",
                        "to_url": "prod://A.format",
                        "to_name": "format",
                        "to_tctracer_fqs": "demo.A.format(int)",
                    },
                ]
            ).to_csv(data_dir / "t2p-candidate" / "demo.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "name": "testCopy",
                        "url": "test://A.testCopy",
                        "artifact": "test",
                        "start_line": 1,
                        "end_line": 3,
                        "code": "void testCopy() { copy(\"x\"); }",
                    }
                ]
            ).to_csv(data_dir / "method-code" / "demo.csv", index=False)
            (author_result_dir / "demo_detail.json").write_text(
                json.dumps({"test_name": "testCopy", "invocations": ["format", "copy"]}) + "\n",
                encoding="utf-8",
            )

            result_df = preprocess_project(
                cache_directory=cache_dir,
                project="demo",
                order_production_method="testlinker",
                order_production_directory=author_result_dir,
            )

            self.assertEqual(["format", "copy"], result_df["invocation"].tolist())

    def test_preprocess_optionally_adds_ground_truth_labels(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            data_dir = cache_dir / "data"
            testlinker_dir = cache_dir / "testlinker"
            (data_dir / "t2p-candidate").mkdir(parents=True)
            (data_dir / "method-code").mkdir(parents=True)
            (data_dir / "t2p-ground-truth-updated").mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_url": "test://A.testCopy",
                        "from_name": "testCopy",
                        "from_file": "src/test/A.java",
                        "from_fqn": "demo.ATest.testCopy",
                        "from_tctracer_fqs": "demo.ATest.testCopy()",
                        "to_url": "prod://A.copy",
                        "to_name": "copy",
                        "to_tctracer_fqs": "demo.A.copy(String)",
                    },
                    {
                        "project": "demo",
                        "from_url": "test://A.testCopy",
                        "from_name": "testCopy",
                        "from_file": "src/test/A.java",
                        "from_fqn": "demo.ATest.testCopy",
                        "from_tctracer_fqs": "demo.ATest.testCopy()",
                        "to_url": "prod://A.format",
                        "to_name": "format",
                        "to_tctracer_fqs": "demo.A.format(int)",
                    },
                ]
            ).to_csv(data_dir / "t2p-candidate" / "demo.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "name": "testCopy",
                        "url": "test://A.testCopy",
                        "artifact": "test",
                        "start_line": 1,
                        "end_line": 3,
                        "code": "void testCopy() { copy(\"x\"); }",
                    }
                ]
            ).to_csv(data_dir / "method-code" / "demo.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_tctracer_fqs": "demo.ATest.testCopy()",
                        "to_tctracer_fqs": "demo.A.copy(String)",
                        "from_url": "test://A.testCopy",
                        "to_url": "prod://A.copy",
                    }
                ]
            ).to_csv(data_dir / "t2p-ground-truth-updated" / "demo.csv", index=False)

            result_df = preprocess_project(cache_directory=cache_dir, project="demo", include_labels=True)

            self.assertEqual([1, 0], result_df["label"].tolist())
            self.assertEqual(["demo.A.copy(String)"], json.loads(result_df.loc[0, "label_json"]))

    def test_execute_and_postprocess_use_csv_interface(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cache_dir = Path(tmpdir)
            data_dir = cache_dir / "data"
            (data_dir / "t2p-candidate").mkdir(parents=True)
            (data_dir / "method-code").mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_url": "test://A.testCopy",
                        "from_name": "testCopy",
                        "from_file": "src/test/A.java",
                        "from_fqn": "demo.ATest.testCopy",
                        "to_url": "prod://A.copy",
                        "to_name": "copy",
                        "to_tctracer_fqs": "demo.A.copy(String)",
                    },
                    {
                        "project": "demo",
                        "from_url": "test://A.testCopy",
                        "from_name": "testCopy",
                        "from_file": "src/test/A.java",
                        "from_fqn": "demo.ATest.testCopy",
                        "to_url": "prod://A.format",
                        "to_name": "format",
                        "to_tctracer_fqs": "demo.A.format(int)",
                    },
                ]
            ).to_csv(data_dir / "t2p-candidate" / "demo.csv", index=False)
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "name": "testCopy",
                        "url": "test://A.testCopy",
                        "artifact": "test",
                        "start_line": 1,
                        "end_line": 3,
                        "code": "void testCopy() { copy(\"x\"); }",
                    }
                ]
            ).to_csv(data_dir / "method-code" / "demo.csv", index=False)

            preprocess_project(cache_directory=cache_dir, project="demo")
            with self.assertWarnsRegex(RuntimeWarning, "TestLinker mapping files are missing"):
                execute_df = execute_project(
                    cache_directory=cache_dir,
                    project="demo",
                    top_k=1,
                    model_mode="heuristic",
                    only_model=True,
                )
            final_df = postprocess_project(cache_directory=cache_dir, project="demo")

            self.assertTrue(raw_detail_path(cache_dir / "testlinker", "demo").exists())
            self.assertTrue((raw_input_json_directory(cache_dir / "testlinker", "demo") / "000001.json").exists())
            self.assertTrue((mapped_input_json_directory(cache_dir / "testlinker", "demo") / "000001.json").exists())
            self.assertTrue(execute_csv_path(cache_dir / "testlinker", "demo").exists())
            self.assertTrue(final_prediction_path(cache_dir, "demo").exists())
            self.assertEqual([1, 0], execute_df["label_pred"].tolist())
            self.assertEqual([2.0, 1.0], execute_df["pred_score"].tolist())
            self.assertEqual([1, 0], final_df["label_pred"].tolist())
            self.assertEqual([2.0, 1.0], final_df["pred_score"].tolist())


if __name__ == "__main__":
    unittest.main()
