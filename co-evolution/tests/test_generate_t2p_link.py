from pathlib import Path
import sys
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

try:
    import pandas as pd
except ImportError:  # pragma: no cover
    pd = None

from ptc.generator.generate_t2p_link import (
    _llm_stage_column_name,
    select_one_stage_indices,
)
from ptc.link_strategy import LinkStrategy


@unittest.skipIf(pd is None, "pandas is required for generate_t2p_link tests")
class TestGenerateT2PLink(unittest.TestCase):
    def test_llm_stage_uses_hyphenated_column_name(self):
        frame = pd.DataFrame(
            [
                {"from_url": "f1", "tech_llm_gpt-oss-20b": 1},
                {"from_url": "f2", "tech_llm_gpt-oss-20b": 0},
            ]
        )

        indexes = select_one_stage_indices(frame, LinkStrategy.LLM_GPT_OSS_20B)

        self.assertEqual([0], list(indexes))
        self.assertEqual("tech_llm_gpt-oss-20b", _llm_stage_column_name(frame, LinkStrategy.LLM_GPT_OSS_20B))

    def test_llm_stage_accepts_underscore_compat_column_name(self):
        frame = pd.DataFrame(
            [
                {"from_url": "f1", "tech_llm_qwen_2d5b": 0},
                {"from_url": "f2", "tech_llm_qwen_2d5b": 1},
            ]
        )

        indexes = select_one_stage_indices(frame, LinkStrategy.LLM_QWEN_2D5B)

        self.assertEqual([1], list(indexes))
        self.assertEqual("tech_llm_qwen_2d5b", _llm_stage_column_name(frame, LinkStrategy.LLM_QWEN_2D5B))

    def test_llm_stage_treats_empty_strings_as_missing(self):
        frame = pd.DataFrame(
            [
                {"from_url": "f1", "tech_llm_gpt-oss-20b": ""},
                {"from_url": "f2", "tech_llm_gpt-oss-20b": "1"},
                {"from_url": "f3", "tech_llm_gpt-oss-20b": "0"},
            ]
        )

        indexes = select_one_stage_indices(frame, LinkStrategy.LLM_GPT_OSS_20B)

        self.assertEqual([1], list(indexes))


if __name__ == "__main__":
    unittest.main()
