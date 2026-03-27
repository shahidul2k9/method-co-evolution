import csv
import tempfile
import unittest
from pathlib import Path
import sys
from unittest.mock import patch

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.llm.models import PromptContentText, PromptInput, PromptMessage
from ptc.llm.persistence import CsvRunStore


class TestCsvRunStore(unittest.TestCase):
    def test_completed_ids_and_csv_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "fan-out", "openai/gpt-oss-20b", "commons-io.csv")

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
                        "error": "",
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

            with store.runs_file.open("r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))

            self.assertIn('"role": "system"', row["messages_json"])
            self.assertEqual("commons-io", row["project"])
            self.assertEqual("2026-03-23T10:00:00+00:00", row["created_at"])
            self.assertEqual("2026-03-23T10:00:00+00:00", row["updated_at"])
            self.assertEqual("null", row["output_json"])

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

            with store.runs_file.open("r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))

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

            with store.runs_file.open("r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))

            self.assertEqual("", row["output_raw"])
            self.assertEqual("null", row["output_json"])
            self.assertEqual("", row["error"])
            self.assertEqual("2026-03-23T10:00:00+00:00", row["created_at"])
            self.assertEqual("2026-03-23T12:00:00+00:00", row["updated_at"])


if __name__ == "__main__":
    unittest.main()
