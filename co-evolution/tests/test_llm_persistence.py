import tempfile
import unittest
from pathlib import Path
import sys

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.llm.persistence import CsvRunStore


class TestCsvRunStore(unittest.TestCase):
    def test_completed_ids_and_csv_export(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CsvRunStore(tmpdir, "fan-out", "openai/gpt-oss-20b", "commons-io.csv")
            import csv

            with store.predictions_file.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=[
                        "llm_id",
                        "llm_fqs",
                        "llm_url",
                        "llm_label",
                        "llm_confidence",
                        "llm_predicted_candidate_ids",
                        "llm_predicted_sigs",
                        "llm_predicted_urls",
                        "llm_rationale",
                        "llm_raw_output",
                    ],
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "llm_id": "https://example/source#L1",
                        "llm_fqs": "org.example.Test.testSaveItem()",
                        "llm_url": "https://example/source#L1",
                        "llm_label": "match",
                        "llm_confidence": "0.9",
                        "llm_predicted_candidate_ids": "c1|c2",
                        "llm_predicted_sigs": "org.example.Prod.one()|org.example.Prod.two()",
                        "llm_predicted_urls": "https://example/prod#L10|https://example/prod#L20",
                        "llm_rationale": "test rationale",
                        "llm_raw_output": "{}",
                    }
                )

            self.assertEqual({"https://example/source#L1"}, store.load_completed_example_ids())
            csv_text = store.predictions_file.read_text(encoding="utf-8")
            self.assertIn("llm_id", csv_text)
            self.assertIn("https://example/source#L1", csv_text)
            self.assertIn("c1|c2", csv_text)
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


if __name__ == "__main__":
    unittest.main()
