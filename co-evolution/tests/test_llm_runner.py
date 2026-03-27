from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.llm.models import GenerationConfig, ProviderGeneration
from ptc.llm.main import load_method_code_lookup
from ptc.llm.persistence import CsvRunStore
from ptc.llm.prompting import JsonPredictionParser, MethodLinkingPromptFactory
from ptc.llm.runner import DataFrameMethodLinker, ModelProvider

try:
    import pandas as pd
except ImportError:  # pragma: no cover - local shell may not have pandas installed
    pd = None


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FAN_OUT_FILE = REPOSITORY_ROOT / ".white" / "data" / "fan-out" / "commons-io.csv"
METHOD_CODE_FILE = REPOSITORY_ROOT / ".white" / "data" / "method-code" / "commons-io.csv"

MATCH_SOURCE_URL = (
    "https://github.com/apache/commons-io/blob/"
    "4077158829de92987367d3149e4ba71356bb5390/src/test/java/"
    "org/apache/commons/io/ByteOrderMarkTestCase.java#L45"
)
EMPTY_SOURCE_URL = (
    "https://github.com/apache/commons-io/blob/"
    "4077158829de92987367d3149e4ba71356bb5390/src/main/java/"
    "org/apache/commons/io/ByteOrderMark.java#L93"
)


def _load_group(source_url: str):
    if pd is None:
        raise unittest.SkipTest("pandas is required for dataframe linker tests")
    if not FAN_OUT_FILE.exists():
        raise unittest.SkipTest(f"Required fixture CSV is missing: {FAN_OUT_FILE}")

    frame = pd.read_csv(FAN_OUT_FILE, keep_default_na=False, na_filter=False)
    group = frame[frame["from_url"] == source_url].copy()
    if group.empty:
        raise unittest.SkipTest(f"Could not find fixture group {source_url} in {FAN_OUT_FILE}")
    return group


class FakeProvider(ModelProvider):
    def __init__(self):
        self.calls = 0

    def prompt_mode(self):
        return "json"

    def generate_batch(self, prompts, generation_config):
        self.calls += 1
        return [
            ProviderGeneration(
                id=prompt.id,
                output_text='{"methods":[{"name":"getCharsetName","confidence":0.9,"rationale":"Direct getter under test"}],"overall_rationale":"One clear match."}',
            )
            for prompt in prompts
        ]


@unittest.skipIf(pd is None, "pandas is required for dataframe linker tests")
class TestDataFrameMethodLinker(unittest.TestCase):
    def test_link_dataframe_persists_predictions_and_resumes_with_real_commons_io_group(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FakeProvider()
            linker = DataFrameMethodLinker(
                provider=provider,
                prompt_factory=MethodLinkingPromptFactory(method_code_lookup=load_method_code_lookup(METHOD_CODE_FILE)),
                parser=JsonPredictionParser(),
                run_store=CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv"),
                batch_size=2,
                resume_mode="all",
            )
            edge_df = _load_group(MATCH_SOURCE_URL)

            result_df = linker.link_dataframe(edge_df, "t2p", GenerationConfig())
            self.assertEqual(1, provider.calls)
            self.assertTrue((result_df["llm_predicted_match"] == 1).all())

            run_csv = Path(tmpdir) / "t2p" / "gpt-oss-20b" / "commons-io.csv"
            self.assertTrue(run_csv.exists())
            run_text = run_csv.read_text(encoding="utf-8")
            self.assertIn("output_raw", run_text)
            self.assertIn("output_json", run_text)
            self.assertIn("getCharsetName", run_text)

            linker.link_dataframe(edge_df, "t2p", GenerationConfig())
            self.assertEqual(1, provider.calls)

    def test_link_dataframe_marks_real_empty_candidate_group_without_model_call(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            provider = FakeProvider()
            linker = DataFrameMethodLinker(
                provider=provider,
                prompt_factory=MethodLinkingPromptFactory(method_code_lookup=load_method_code_lookup(METHOD_CODE_FILE)),
                parser=JsonPredictionParser(),
                run_store=CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv"),
                batch_size=2,
                resume_mode="all",
            )
            edge_df = _load_group(EMPTY_SOURCE_URL)

            result_df = linker.link_dataframe(edge_df, "t2p", GenerationConfig())

            self.assertEqual(0, provider.calls)
            self.assertTrue((result_df["llm_label"] == "none").all())
            self.assertTrue((result_df["llm_predicted_match"] == 0).all())

    def test_resume_errors_reruns_only_rows_with_existing_error(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_store = CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv")
            provider = FakeProvider()
            linker = DataFrameMethodLinker(
                provider=provider,
                prompt_factory=MethodLinkingPromptFactory(method_code_lookup=load_method_code_lookup(METHOD_CODE_FILE)),
                parser=JsonPredictionParser(),
                run_store=run_store,
                batch_size=2,
                resume_mode="error",
            )
            edge_df = _load_group(MATCH_SOURCE_URL)
            prompt = linker.prompt_factory.build_prompt(edge_df, "t2p", prompt_format="json")
            run_store.upsert_request(prompt)
            run_store.upsert_result(
                prompt_input=prompt,
                output_raw="broken",
                output_json=None,
                error="parser: boom",
            )

            result_df = linker.link_dataframe(edge_df, "t2p", GenerationConfig())

            self.assertEqual(1, provider.calls)
            self.assertTrue((result_df["llm_predicted_match"] == 1).all())

    def test_resume_none_reruns_all_rows_even_with_existing_error_rows(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            run_store = CsvRunStore(tmpdir, "t2p", "openai/gpt-oss-20b", "commons-io.csv")
            provider = FakeProvider()
            linker = DataFrameMethodLinker(
                provider=provider,
                prompt_factory=MethodLinkingPromptFactory(method_code_lookup=load_method_code_lookup(METHOD_CODE_FILE)),
                parser=JsonPredictionParser(),
                run_store=run_store,
                batch_size=2,
                resume_mode="none",
            )
            edge_df = _load_group(MATCH_SOURCE_URL)
            prompt = linker.prompt_factory.build_prompt(edge_df, "t2p", prompt_format="json")
            run_store.upsert_request(prompt)
            run_store.upsert_result(
                prompt_input=prompt,
                output_raw="broken",
                output_json=None,
                error="parser: boom",
            )

            result_df = linker.link_dataframe(edge_df, "t2p", GenerationConfig())

            self.assertEqual(1, provider.calls)
            self.assertTrue((result_df["llm_predicted_match"] == 1).all())


if __name__ == "__main__":
    unittest.main()
