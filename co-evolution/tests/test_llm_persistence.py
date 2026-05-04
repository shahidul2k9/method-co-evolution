import csv
import json
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.llm.models import PromptContentText, PromptInput, PromptMessage
from ptc.llm.persistence import CsvRunStore
from ptc.llm.runner import DataFrameMethodLinker, ModelProvider
from ptc.llm.prompting import JsonPredictionParser, MethodLinkingPromptFactory
from ptc.llm.models import GenerationConfig, ProviderGeneration


class TestCsvRunStore(unittest.TestCase):
    def test_completed_ids_and_csv_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "callgraph", "openai/gpt-oss-20b", "commons-io.csv")

            with store.runs_file.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "project",
                        "name",
                        "url",
                        "prompt_text",
                        "messages_json",
                        "metadata_json",
                        "output_raw",
                        "output_json",
                        "error",
                        "created_at",
                        "updated_at",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "project": "commons-io",
                        "name": "testSaveItem",
                        "url": "https://example/source#L1",
                        "prompt_text": "SYSTEM:\nhello",
                        "messages_json": "[]",
                        "metadata_json": "{}",
                        "output_raw": '{"methods":[{"name":"saveItem","confidence":0.9,"rationale":"Direct call"}],"overall_rationale":"One clear match."}',
                        "output_json": '{"methods":[{"name":"saveItem","confidence":0.9,"rationale":"Direct call"}],"overall_rationale":"One clear match."}',
                        "error": "null",
                        "created_at": "2026-03-23T10:00:00+00:00",
                        "updated_at": "2026-03-23T10:00:00+00:00",
                    }
                )

            self.assertEqual({"https://example/source#L1"}, store.load_completed_example_ids())
            self.assertEqual(set(), store.load_error_example_ids())
            csv_text = store.runs_file.read_text(encoding="utf-8")
            self.assertIn("output_json", csv_text)
            self.assertIn("saveItem", csv_text)
            self.assertEqual("t2p", store.input_kind)
            self.assertEqual(
                Path(tmpdir) / "t2p" / "gpt-oss-20b" / "commons-io.csv",
                store.runs_file,
            )

    def test_short_model_name_overrides_directory_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(
                tmpdir,
                "t2p",
                "openai/gpt-oss-20b",
                "commons-io.csv",
                short_model_name="gpt_oss_20b",
            )

            self.assertEqual(
                Path(tmpdir) / "t2p" / "gpt_oss_20b" / "commons-io.csv",
                store.runs_file,
            )

    def test_upsert_request_persists_messages_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv")
            prompt = PromptInput(
                id="https://example/test#L1",
                fqs="org.example.Test.testThing()",
                name="testThing",
                code="void testThing() {}",
                url="https://example/test#L1",
                prompt_text="SYSTEM:\nhello",
                messages=[
                    PromptMessage(
                        role="system",
                        content=[PromptContentText(type="text", text="hello")],
                    )
                ],
            )

            with patch("ptc.llm.persistence._timestamp_now", return_value="2026-03-23T10:00:00+00:00"):
                store.upsert_request(prompt)

            row = pd.read_csv(store.runs_file).iloc[0]

            self.assertIn('"role": "system"', row["messages_json"])
            self.assertEqual("commons-io", row["project"])
            self.assertEqual("2026-03-23T10:00:00+00:00", row["created_at"])
            self.assertEqual("2026-03-23T10:00:00+00:00", row["updated_at"])
            self.assertTrue(pd.isna(row["output_raw"]))
            self.assertTrue(pd.isna(row["output_json"]))
            self.assertEqual("unknown", row["error"])

    def test_runner_persists_batch_size_and_max_new_tokens_in_metadata_json(self):
        class FakeProvider(ModelProvider):
            def prompt_mode(self):
                return "json"

            def generate_batch(self, prompts, generation_config):
                return [
                    ProviderGeneration(
                        id=prompt.id,
                        output_text='{"methods":[],"overall_rationale":"No direct match."}',
                    )
                    for prompt in prompts
                ]

        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv")
            edge_df = pd.DataFrame(
                [
                    {
                        "project": "commons-io",
                        "from_name": "testThing",
                        "to_name": "saveItem",
                        "from_url": "https://example/test#L1",
                        "to_url": "https://example/main#L1",
                        "from_file": "src/test/java/Test.java",
                        "to_file": "src/main/java/Main.java",
                        "from_fqs": "org.example.Test.testThing()",
                        "to_fqs": "org.example.Main.saveItem()",
                        "from_sig": "org.example.Test.testThing()",
                        "to_sig": "org.example.Main.saveItem()",
                    }
                ]
            )
            method_code_lookup = {
                "https://example/test#L1": {"name": "testThing", "code": "void testThing() {}"}
            }
            linker = DataFrameMethodLinker(
                provider=FakeProvider(),
                prompt_factory=MethodLinkingPromptFactory(method_code_lookup=method_code_lookup),
                parser=JsonPredictionParser(),
                run_store=store,
                batch_size=1,
                resume_mode="none",
            )

            linker.link_dataframe(edge_df, "t2p", GenerationConfig(max_new_tokens=2048))

            row = pd.read_csv(store.runs_file).iloc[0]
            metadata_json = json.loads(row["metadata_json"])
            self.assertEqual(1, metadata_json["batch_size"])
            self.assertEqual(2048, metadata_json["max_new_tokens"])

    def test_upsert_result_persists_error_and_output_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv")
            prompt = PromptInput(
                id="https://example/test#L1",
                fqs="org.example.Test.testThing()",
                name="testThing",
                code="void testThing() {}",
                url="https://example/test#L1",
                prompt_text="SYSTEM:\nhello",
            )

            with patch("ptc.llm.persistence._timestamp_now", return_value="2026-03-23T10:00:00+00:00"):
                store.upsert_request(prompt)
            with patch("ptc.llm.persistence._timestamp_now", return_value="2026-03-23T11:00:00+00:00"):
                store.upsert_result(
                    prompt_input=prompt,
                    output_raw="raw-output",
                    output_json={"methods": [], "overall_rationale": "No direct match."},
                    error="parser: boom",
                )

            row = pd.read_csv(store.runs_file).iloc[0]

            self.assertEqual("raw-output", row["output_raw"])
            self.assertIn('"overall_rationale": "No direct match."', row["output_json"])
            self.assertEqual("parser: boom", row["error"])
            self.assertEqual("2026-03-23T10:00:00+00:00", row["created_at"])
            self.assertEqual("2026-03-23T11:00:00+00:00", row["updated_at"])
            self.assertEqual({"https://example/test#L1"}, store.load_error_example_ids())

    def test_no_resume_reset_clears_previous_output_and_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv")
            prompt = PromptInput(
                id="https://example/test#L1",
                fqs="org.example.Test.testThing()",
                name="testThing",
                code="void testThing() {}",
                url="https://example/test#L1",
                prompt_text="SYSTEM:\nhello",
            )

            with patch("ptc.llm.persistence._timestamp_now", return_value="2026-03-23T10:00:00+00:00"):
                store.upsert_request(prompt)
            with patch("ptc.llm.persistence._timestamp_now", return_value="2026-03-23T11:00:00+00:00"):
                store.upsert_result(prompt, "bad", None, "provider: boom")
            with patch("ptc.llm.persistence._timestamp_now", return_value="2026-03-23T12:00:00+00:00"):
                store.upsert_request(prompt, overwrite_existing=True)

            row = pd.read_csv(store.runs_file).iloc[0]

            self.assertTrue(pd.isna(row["output_raw"]))
            self.assertTrue(pd.isna(row["output_json"]))
            self.assertEqual("unknown", row["error"])
            self.assertEqual("2026-03-23T10:00:00+00:00", row["created_at"])
            self.assertEqual("2026-03-23T12:00:00+00:00", row["updated_at"])


if __name__ == "__main__":
    unittest.main()
