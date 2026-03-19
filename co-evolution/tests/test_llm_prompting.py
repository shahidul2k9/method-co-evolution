from pathlib import Path
import sys
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.llm.prompting import JsonPredictionParser, MethodLinkingPromptFactory

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

        self.assertIn("linking test methods to production methods", prompt.prompt_text)
        self.assertIn(
            "Test method FQS: org.apache.commons.io.ByteOrderMarkTestCase.charsetName()",
            prompt.prompt_text,
        )
        self.assertIn("Candidate production methods called by the source method:", prompt.prompt_text)
        self.assertIn("fqs=org.apache.commons.io.ByteOrderMark.getCharsetName()", prompt.prompt_text)
        self.assertIn("file=src/main/java/org/apache/commons/io/ByteOrderMark.java", prompt.prompt_text)
        self.assertNotIn("sig=", prompt.prompt_text)
        self.assertNotIn("url=", prompt.prompt_text)
        self.assertNotIn("lcba=", prompt.prompt_text)

    def test_p2t_prompt_contains_real_commons_io_methods(self):
        case_df = _load_group(FAN_IN_FILE, "to_url", P2T_SOURCE_URL)

        prompt = MethodLinkingPromptFactory().build_prompt(case_df, "p2t")

        self.assertIn("linking production methods to test methods", prompt.prompt_text)
        self.assertIn(
            "Production method FQS: org.apache.commons.io.FileUtils.byteCountToDisplaySize(long)",
            prompt.prompt_text,
        )
        self.assertIn("Candidate source methods that call this production method:", prompt.prompt_text)
        self.assertIn(
            "fqs=org.apache.commons.io.FileUtilsTestCase.testByteCountToDisplaySizeBigInteger()",
            prompt.prompt_text,
        )
        self.assertIn(
            "fqs=org.apache.commons.io.FileUtilsTestCase.testByteCountToDisplaySizeLong()",
            prompt.prompt_text,
        )
        self.assertNotIn("sig=", prompt.prompt_text)
        self.assertNotIn("url=", prompt.prompt_text)
        self.assertNotIn("lcba=", prompt.prompt_text)


class TestJsonPredictionParser(unittest.TestCase):
    def test_parse_prediction_maps_candidate_id_and_confidence_from_real_prompt(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        prediction = JsonPredictionParser().parse(
            prompt_input,
            (
                '{"candidate_ids":["c1"],'
                '"candidate_confidences":{"c1":0.91},"confidence":0.93,'
                '"rationale":"Real commons-io example"}'
            ),
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1"], prediction.selected_candidate_ids)
        self.assertEqual([0.91], prediction.selected_candidate_confidences)
        self.assertEqual(
            ["org.apache.commons.io.ByteOrderMark.getCharsetName()"],
            prediction.selected_candidate_sigs,
        )
        self.assertEqual(
            [
                "https://github.com/apache/commons-io/blob/"
                "4077158829de92987367d3149e4ba71356bb5390/src/main/java/"
                "org/apache/commons/io/ByteOrderMark.java#L93"
            ],
            prediction.selected_candidate_urls,
        )
        self.assertAlmostEqual(0.93, prediction.confidence)

    def test_parse_prediction_falls_back_to_none_when_model_returns_non_json_text(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        prediction = JsonPredictionParser().parse(
            prompt_input,
            "The model repeated the prompt and never returned JSON.",
        )

        self.assertEqual("none", prediction.label)
        self.assertEqual([], prediction.selected_candidate_ids)
        self.assertIn("did not return a JSON object", prediction.rationale)

    def test_parse_prediction_skips_echoed_schema_and_uses_real_json_payload(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        prediction = JsonPredictionParser().parse(
            prompt_input,
            (
                '{"candidate_ids":["c1","c2"],'
                '"candidate_confidences":{"c1":0.0,"c2":0.0},"confidence":0.0,'
                '"rationale":"short explanation"}\n'
                'Source method FQS: echoed prompt text\n'
                '{"candidate_ids":["c1"],'
                '"candidate_confidences":{"c1":0.77},"confidence":0.8,'
                '"rationale":"Selected the primary production call."}'
            ),
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1"], prediction.selected_candidate_ids)
        self.assertEqual([0.77], prediction.selected_candidate_confidences)

    def test_parse_prediction_ignores_extra_label_field_from_tiny_model(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        prediction = JsonPredictionParser().parse(
            prompt_input,
            (
                '{"label":"match|one|partial","candidate_ids":["c1","c2"],'
                '"candidate_confidences":null,"confidence":0.0,'
                '"rationale":"Both c1 and c2 are used for testing ByteOrderMark equals()."}'
            ),
        )

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1", "c2"], prediction.selected_candidate_ids)

    def test_parse_prediction_accepts_raw_json_list_of_candidate_ids(self):
        case_df = _load_group(FAN_OUT_FILE, "from_url", T2P_SOURCE_URL)
        prompt_input = MethodLinkingPromptFactory().build_prompt(case_df, "t2p")

        prediction = JsonPredictionParser().parse(prompt_input, '["c1","c2"]')

        self.assertEqual("match", prediction.label)
        self.assertEqual(["c1", "c2"], prediction.selected_candidate_ids)


if __name__ == "__main__":
    unittest.main()
