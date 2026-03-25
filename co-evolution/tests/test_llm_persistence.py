import tempfile
import unittest
from pathlib import Path
import sys
import csv
from unittest.mock import patch

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.llm.models import PromptContentText, PromptInput, PromptMessage
from ptc.llm.persistence import CsvRunStore

try:
    import pandas as pd
except ImportError:  # pragma: no cover - local shell may not have pandas installed
    pd = None


class TestCsvRunStore(unittest.TestCase):
    def test_completed_ids_and_csv_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "fan-out", "openai/gpt-oss-20b", "commons-io.csv")
            import csv

            with store.predictions_file.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "project",
                        "from_name",
                        "to_name",
                        "from_url",
                        "to_url",
                        "from_fqs",
                        "to_fqs",
                        "llm_id",
                        "llm_pred",
                        "llm_names",
                        "llm_output",
                        "created_at",
                        "updated_at",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "project": "commons-io",
                        "from_name": "testSaveItem",
                        "to_name": "saveItem",
                        "from_url": "https://example/source#L1",
                        "to_url": "https://example/prod#L10",
                        "from_fqs": "org.example.Test.testSaveItem()",
                        "to_fqs": "org.example.Prod.saveItem()",
                        "llm_id": "https://example/source#L1",
                        "llm_pred": "1",
                        "llm_names": "saveItem|validateItem",
                        "llm_output": "{}",
                        "created_at": "2026-03-23T10:00:00+00:00",
                        "updated_at": "2026-03-23T10:00:00+00:00",
                    }
                )

            self.assertEqual({"https://example/source#L1"}, store.load_completed_example_ids())
            csv_text = store.predictions_file.read_text(encoding="utf-8")
            self.assertIn("llm_id", csv_text)
            self.assertIn("https://example/source#L1", csv_text)
            self.assertIn("saveItem|validateItem", csv_text)
            self.assertEqual("t2p", store.input_kind)
            self.assertEqual(
                Path(tmpdir) / "t2p" / "gpt-oss-20b" / "prediction" / "commons-io.csv",
                store.predictions_file,
            )
            self.assertEqual(
                Path(tmpdir) / "t2p" / "gpt-oss-20b" / "request" / "commons-io.csv",
                store.requests_file,
            )
            self.assertEqual(
                Path(tmpdir) / "t2p" / "gpt-oss-20b" / "error" / "commons-io.csv",
                store.failures_file,
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
                Path(tmpdir) / "t2p" / "gpt_oss_20b" / "prediction" / "commons-io.csv",
                store.predictions_file,
            )

    def test_append_request_persists_messages_json(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv")
            prompt = PromptInput(
                id="id-1",
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
                store.append_request(prompt)

            with store.requests_file.open("r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))

            self.assertIn('"role": "system"', row["messages_json"])
            self.assertEqual("2026-03-23T10:00:00+00:00", row["created_at"])
            self.assertEqual("2026-03-23T10:00:00+00:00", row["updated_at"])

    def test_append_failure_persists_timestamps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv")

            with patch("ptc.llm.persistence._timestamp_now", return_value="2026-03-23T11:00:00+00:00"):
                store.append_failure("id-1", "provider", "boom")

            with store.failures_file.open("r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))

            self.assertEqual("id-1", row["id"])
            self.assertEqual("provider", row["stage"])
            self.assertEqual("boom", row["error"])
            self.assertEqual("2026-03-23T11:00:00+00:00", row["created_at"])
            self.assertEqual("2026-03-23T11:00:00+00:00", row["updated_at"])

    @unittest.skipIf(pd is None, "pandas is required for prediction persistence tests")
    def test_write_prediction_snapshot_sets_and_preserves_timestamps(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv")
            snapshot_df = pd.DataFrame(
                [
                    {
                        "project": "commons-io",
                        "from_name": "testSaveItem",
                        "to_name": "saveItem",
                        "from_url": "https://example/source#L1",
                        "to_url": "https://example/prod#L10",
                        "from_fqs": "org.example.Test.testSaveItem()",
                        "to_fqs": "org.example.Prod.saveItem()",
                        "llm_id": "https://example/source#L1",
                        "llm_pred": 1,
                        "llm_names": "saveItem|validateItem",
                        "llm_output": "{}",
                    }
                ]
            )

            with patch("ptc.llm.persistence._timestamp_now", return_value="2026-03-23T12:00:00+00:00"):
                store.write_prediction_snapshot(snapshot_df)

            with patch("ptc.llm.persistence._timestamp_now", return_value="2026-03-23T13:00:00+00:00"):
                store.write_prediction_snapshot(snapshot_df)

            with store.predictions_file.open("r", encoding="utf-8", newline="") as handle:
                row = next(csv.DictReader(handle))

            self.assertEqual("2026-03-23T12:00:00+00:00", row["created_at"])
            self.assertEqual("2026-03-23T13:00:00+00:00", row["updated_at"])


if __name__ == "__main__":
    unittest.main()
