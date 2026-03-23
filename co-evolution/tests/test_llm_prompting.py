from pathlib import Path
import sys
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.llm.prompting import JsonPredictionParser, MethodLinkingPromptFactory
from ptc.llm.models import PromptInput

try:
    import pandas as pd
except ImportError:  # pragma: no cover - local shell may not have pandas installed
    pd = None


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
FAN_OUT_FILE = REPOSITORY_ROOT / ".white" / "data" / "fan-out" / "commons-io.csv"
FAN_IN_FILE = REPOSITORY_ROOT / ".white" / "data" / "fan-in" / "commons-io.csv"

T2P_SOURCE_URL = (
    "https://github.com/apache/commons-io/blob/"
    "4077158829de92987367d3149e4ba71356bb5390/src/test/java/"
    "org/apache/commons/io/ByteOrderMarkTestCase.java#L45"
)
P2T_SOURCE_URL = (
    "https://github.com/apache/commons-io/blob/"
    "4077158829de92987367d3149e4ba71356bb5390/src/main/java/"
    "org/apache/commons/io/FileUtils.java#L416"
)


def _load_group(csv_file: Path, group_column: str, group_value: str):
    if pd is None:
        raise unittest.SkipTest("pandas is required for dataframe prompt tests")
    if not csv_file.exists():
        raise unittest.SkipTest(f"Required fixture CSV is missing: {csv_file}")

    frame = pd.read_csv(csv_file, keep_default_na=False, na_filter=False)
    group = frame[frame[group_column] == group_value].copy()
    if group.empty:
        raise unittest.SkipTest(f"Could not find fixture group {group_value} in {csv_file}")
    return group


class TestMethodLinkPromptFactory(unittest.TestCase):
    def test_t2p_prompt_contains_real_commons_io_methods(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)

        prompt = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        self.assertEqual(2, len(prompt.messages))
        self.assertEqual("system", prompt.messages[0].role)
        self.assertEqual("user", prompt.messages[1].role)
        self.assertIn("expert in identifying which production method is being tested", prompt.prompt_text.lower())
        self.assertIn(
            "Fully qualified signature (FQS) of test method: "
            "org.apache.commons.io.ByteOrderMarkTestCase.charsetName()",
            prompt.prompt_text,
        )
        self.assertIn("Candidate production methods called by the test method:", prompt.prompt_text)
        self.assertIn("org.apache.commons.io.ByteOrderMark.getCharsetName()", prompt.prompt_text)
        self.assertNotIn("c1:", prompt.prompt_text)
        self.assertEqual("json_schema", prompt.response_format["type"])
        self.assertEqual("method_link_prediction", prompt.response_format["name"])

    def test_t2p_conventional_prompt_requests_labeled_output(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)

        prompt = MethodLinkingPromptFactory().build_prompt(case_df, "t2p", prompt_format="text")

        self.assertIsNone(prompt.response_format)
        self.assertIn("Answer: <exact candidate FQS from the list above or NONE>", prompt.prompt_text)
        self.assertIn("Start immediately with Answer:", prompt.prompt_text)
        self.assertIn("Do not include analysis", prompt.prompt_text)
        self.assertNotIn("c1:", prompt.prompt_text)

    def test_p2t_prompt_contains_real_commons_io_methods(self):
        case_df = _load_group(FAN_IN_FILE, "to_url", P2T_SOURCE_URL)

        prompt = MethodLinkingPromptFactory().build_prompt(case_df, "p2t")

        self.assertEqual(2, len(prompt.messages))
        self.assertIn("expert in identifying which test method exercises a given production method", prompt.prompt_text.lower())
        self.assertIn(
            "Fully qualified signature (FQS) of production method: "
            "org.apache.commons.io.FileUtils.byteCountToDisplaySize(long)",
            prompt.prompt_text,
        )
        self.assertIn("Candidate test methods that call this production method:", prompt.prompt_text)
        self.assertIn(
            "org.apache.commons.io.FileUtilsTestCase.testByteCountToDisplaySizeBigInteger()",
            prompt.prompt_text,
        )
        self.assertIn(
            "org.apache.commons.io.FileUtilsTestCase.testByteCountToDisplaySizeLong()",
            prompt.prompt_text,
        )
        self.assertEqual("json_schema", prompt.response_format["type"])


class TestJsonPredictionParser(unittest.TestCase):
    def test_parse_prediction_maps_candidate_id_and_confidence_from_real_prompt(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        prediction = JsonPredictionParser().parse(
            prompt_input,
            '{"answer":"org.apache.commons.io.ByteOrderMark.getCharsetName()"}',
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1"], prediction.selected_candidate_ids)
        self.assertEqual(
            "org.apache.commons.io.ByteOrderMark.getCharsetName()",
            prediction.selected_candidate_fqs,
        )
        self.assertEqual(
            "https://github.com/apache/commons-io/blob/"
            "4077158829de92987367d3149e4ba71356bb5390/src/main/java/"
            "org/apache/commons/io/ByteOrderMark.java#L93",
            prediction.selected_candidate_url,
        )
        self.assertIsNone(prediction.confidence)

    def test_parse_prediction_falls_back_to_none_when_model_returns_non_json_text(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        prediction = JsonPredictionParser().parse(
            prompt_input,
            "The model repeated the prompt and never returned JSON.",
        )

        self.assertEqual("none", prediction.label)
        self.assertEqual([], prediction.selected_candidate_ids)
        self.assertIn("did not return a usable answer", prediction.rationale)

    def test_placeholder_schema_payload_is_not_treated_as_prediction(self):
        placeholder_payload = {
            "answer": "",
        }

        self.assertFalse(JsonPredictionParser._looks_like_prediction_payload(placeholder_payload))

    def test_parse_prediction_accepts_json_answer(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        prediction = JsonPredictionParser().parse(
            prompt_input,
            '{"answer":"org.apache.commons.io.ByteOrderMark.getCharsetName()"}',
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1"], prediction.selected_candidate_ids)

    def test_parse_prediction_accepts_raw_json_string_answer(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        prediction = JsonPredictionParser().parse(
            prompt_input,
            '"org.apache.commons.io.ByteOrderMark.getCharsetName()"',
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1"], prediction.selected_candidate_ids)

    def test_parse_prediction_accepts_answer_line(self):
        case_df = _load_group(FAN_IN_FILE, "to_url", P2T_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "p2t", prompt_format="text")
        first_candidate = prompt_input.candidate_lookup["c1"]["fqs"]

        prediction = JsonPredictionParser().parse(
            prompt_input,
            f"Answer: {first_candidate}",
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1"], prediction.selected_candidate_ids)
        self.assertIsNone(prediction.confidence)

    def test_parse_prediction_accepts_answer_none_for_no_match(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p", prompt_format="text")

        prediction = JsonPredictionParser().parse(
            prompt_input,
            "Answer: NONE",
        )

        self.assertEqual("none", prediction.label)
        self.assertEqual([], prediction.selected_candidate_ids)
        self.assertIsNone(prediction.confidence)

    def test_parse_prediction_ignores_preamble_and_resolves_unique_truncated_method(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p", prompt_format="text")
        first_candidate = prompt_input.candidate_lookup["c1"]["fqs"]
        truncated_candidate = first_candidate.split("(", 1)[0] + "("

        prediction = JsonPredictionParser().parse(
            prompt_input,
            (
                "We need to determine which production method is under test.\n"
                "The test likely focuses on the first candidate.\n\n"
                f"Answer: {truncated_candidate}"
            ),
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1"], prediction.selected_candidate_ids)
        self.assertIsNone(prediction.confidence)

    def test_parse_prediction_accepts_inline_answer(self):
        prompt_input = PromptInput(
            id="dirwalker-case",
            fqs="org.apache.commons.io.DirectoryWalkerTestCase.testMissingStartDirectory()",
            url="https://example/test#L1",
            prompt_text="",
            candidate_lookup={
                "c1": {
                    "fqs": "org.apache.commons.io.DirectoryWalker.walk(File, Collection)",
                    "sig": "org.apache.commons.io.DirectoryWalker.walk(File, Collection)",
                    "url": "https://example/prod#L10",
                }
            },
        )

        prediction = JsonPredictionParser().parse(
            prompt_input,
            (
                "We need to locate DirectoryWalkerTestCase in Apache Commons IO. "
                "The testMissingStartDirectory likely tests that the walk method throws for a missing directory. "
                "So the right response is Answer: org.apache.commons.io.DirectoryWalker.walk(File, Collection)."
            ),
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1"], prediction.selected_candidate_ids)
        self.assertIsNone(prediction.confidence)

    def test_parse_prediction_recovers_from_quoted_answer_with_trailing_assistant_token(self):
        prompt_input = PromptInput(
            id="write-lines-case",
            fqs=(
                "org.apache.commons.io.FileUtilsTestCase."
                "testWriteLines_5argsWithAppendOptionFalse_ShouldDeletePreviousFileLines()"
            ),
            url="https://example/test#L20",
            prompt_text="",
            candidate_lookup={
                "c1": {
                    "fqs": "org.apache.commons.io.FileUtils.forceDelete(File)",
                    "sig": "org.apache.commons.io.FileUtils.forceDelete(File)",
                    "url": "https://example/prod#L10",
                },
                "c2": {
                    "fqs": "org.apache.commons.io.FileUtils.writeStringToFile(File, String, Charset)",
                    "sig": "org.apache.commons.io.FileUtils.writeStringToFile(File, String, Charset)",
                    "url": "https://example/prod#L20",
                },
                "c3": {
                    "fqs": "org.apache.commons.io.FileUtils.readFileToString(File, Charset)",
                    "sig": "org.apache.commons.io.FileUtils.readFileToString(File, Charset)",
                    "url": "https://example/prod#L30",
                },
                "c4": {
                    "fqs": "org.apache.commons.io.FileUtils.writeLines(File, String, Collection, String, boolean)",
                    "sig": "org.apache.commons.io.FileUtils.writeLines(File, String, Collection, String, boolean)",
                    "url": "https://example/prod#L40",
                },
            },
        )

        prediction = JsonPredictionParser().parse(
            prompt_input,
            (
                "\"\n\n"
                "We need to determine which production method is being tested by the test method. "
                "The test method name: testWriteLines_5argsWithAppendOptionFalse_ShouldDeletePreviousFileLines. "
                "So it's testing writeLines with 5 args, append option false, should delete previous file lines. "
                "So likely the method under test is writeLines(File, String, Collection, String, boolean). "
                "That is the candidate. The other methods are forceDelete, writeStringToFile, readFileToString. "
                "The test likely calls writeLines. So answer: "
                "\"Answer: org.apache.commons.io.FileUtils.writeLines(File, String, Collection, String, boolean)\"."
                "assistantfinalAnswer: org.apache.commons.io.FileUtils.writeLines(File, String, Collection, String, boolean)"
            ),
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c4"], prediction.selected_candidate_ids)
        self.assertEqual(
            "org.apache.commons.io.FileUtils.writeLines(File, String, Collection, String, boolean)",
            prediction.selected_candidate_fqs,
        )
        self.assertIsNone(prediction.confidence)


if __name__ == "__main__":
    unittest.main()
