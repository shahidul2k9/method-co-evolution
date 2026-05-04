from pathlib import Path
import sys
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PTC_SRC_DIRECTORY = REPOSITORY_ROOT / "co-evolution" / "src"
MHC_SRC_DIRECTORY = REPOSITORY_ROOT / "method-history-collector" / "src"
for source_directory in (PTC_SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(source_directory) not in sys.path:
        sys.path.insert(0, str(source_directory))

from mhc.constant import CACHE_DIRECTORY
from ptc.llm.main import default_output_root, resolve_api_type, resolve_input_file, resolve_method_code_file
from ptc.llm.providers.openai_responses import (
    normalize_openai_model_name,
    translate_provider_error,
)

TEST_CACHE_DIRECTORY = Path(CACHE_DIRECTORY) / "test" / "llm-m2m-link"


class TestLlmMainHelpers(unittest.TestCase):
    def test_resolve_input_file_from_cache_directory_for_t2p(self):
        input_file = resolve_input_file(str(TEST_CACHE_DIRECTORY), "commons-io", "t2p")

        self.assertEqual(
            TEST_CACHE_DIRECTORY / "data" / "t2p-candidate" / "commons-io.csv",
            input_file,
        )

    def test_resolve_input_file_from_cache_directory_for_p2t(self):
        input_file = resolve_input_file(str(TEST_CACHE_DIRECTORY), "commons-io", "p2t")

        self.assertEqual(
            TEST_CACHE_DIRECTORY / "data" / "fanin" / "commons-io.csv",
            input_file,
        )

    def test_default_output_root_uses_cache_directory_when_present(self):
        self.assertEqual(
            TEST_CACHE_DIRECTORY / "data" / "llm",
            default_output_root(str(TEST_CACHE_DIRECTORY)),
        )

    def test_resolve_method_code_file_from_cache_directory(self):
        method_code_file = resolve_method_code_file(str(TEST_CACHE_DIRECTORY), "commons-io")

        self.assertEqual(
            TEST_CACHE_DIRECTORY / "data" / "method-code" / "commons-io.csv",
            method_code_file,
        )

    def test_resolve_api_type_uses_openai_responses_for_gpt_oss(self):
        self.assertEqual(
            "openai-responses",
            resolve_api_type("auto", "openai/gpt-oss-20b"),
        )

    def test_resolve_api_type_defaults_to_huggingface_for_non_gpt_model(self):
        self.assertEqual(
            "huggingface",
            resolve_api_type("auto", "Qwen/Qwen2.5-0.5B-Instruct"),
        )

    def test_normalize_openai_model_name_strips_openai_prefix(self):
        self.assertEqual(
            "gpt-oss-20b",
            normalize_openai_model_name("openai/gpt-oss-20b"),
        )

    def test_normalize_openai_model_name_keeps_prefix_for_custom_base_url(self):
        self.assertEqual(
            "openai/gpt-oss-20b:free",
            normalize_openai_model_name(
                "openai/gpt-oss-20b:free",
                "https://openrouter.ai/api/v1",
            ),
        )

    def test_translate_provider_error_adds_openrouter_privacy_hint(self):
        error = Exception(
            "Error code: 404 - {'error': {'message': 'No endpoints available matching your "
            "guardrail restrictions and data policy. Configure: https://openrouter.ai/settings/privacy'}}"
        )

        translated = translate_provider_error(error, "https://openrouter.ai/api/v1")

        self.assertIn("OpenRouter could not route this request", translated)
        self.assertIn("https://openrouter.ai/settings/privacy", translated)


if __name__ == "__main__":
    unittest.main()
