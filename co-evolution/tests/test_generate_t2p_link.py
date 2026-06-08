from pathlib import Path
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

from ptc.generator.t2p_link import (
    build_parser,
    filter_test_case_to_main_code_links,
    METHOD_LINK_STRATEGIES,
    _llm_stage_column_name,
    select_one_stage_indices,
    select_link_strategies,
    select_t2p_tech_files,
    strategy_output_key,
)
from ptc.link_strategy import LinkStrategy, strategies_from_keys


@unittest.skipIf(pd is None, "pandas is required for generate_t2p_link tests")
class TestGenerateT2PLink(unittest.TestCase):
    def test_omc_selects_groups_with_one_distinct_target(self):
        frame = pd.DataFrame(
            [
                {"from_url": "testA", "to_url": "prodA"},
                {"from_url": "testB", "to_url": "prodB"},
                {"from_url": "testB", "to_url": "prodB"},
                {"from_url": "testC", "to_url": "prodC"},
                {"from_url": "testC", "to_url": "prodD"},
            ]
        )

        indexes = select_one_stage_indices(frame, LinkStrategy.OMC)

        self.assertEqual([0, 1, 2], list(indexes))

    def test_score_stages_select_threshold_scores_in_rank_order(self):
        frame = pd.DataFrame(
            [
                {
                    "from_url": "f1",
                    "tech_lcs_u": 0.74,
                    "tech_lcs_b": 0.54,
                    "tech_leven": 0.94,
                    "tech_tarantula": 0.94,
                    "tech_tfidf": 0.89,
                    "tech_combined": 0.84,
                },
                {
                    "from_url": "f1",
                    "tech_lcs_u": 0.90,
                    "tech_lcs_b": 0.60,
                    "tech_leven": 0.98,
                    "tech_tarantula": 0.99,
                    "tech_tfidf": 0.95,
                    "tech_combined": 0.90,
                },
                {
                    "from_url": "f2",
                    "tech_lcs_u": 0.80,
                    "tech_lcs_b": 0.70,
                    "tech_leven": 0.96,
                    "tech_tarantula": 0.96,
                    "tech_tfidf": 0.91,
                    "tech_combined": 0.86,
                },
            ]
        )

        self.assertEqual([1, 2], list(select_one_stage_indices(frame, LinkStrategy.LCS_U)))
        self.assertEqual([1, 2], list(select_one_stage_indices(frame, LinkStrategy.LCS_B)))
        self.assertEqual([1, 2], list(select_one_stage_indices(frame, LinkStrategy.LEVEN)))
        self.assertEqual([1, 2], list(select_one_stage_indices(frame, LinkStrategy.TARANTULA)))
        self.assertEqual([1, 2], list(select_one_stage_indices(frame, LinkStrategy.TFIDF)))
        self.assertEqual([1, 2], list(select_one_stage_indices(frame, LinkStrategy.COMBINED)))

    def test_lcs_u_and_lcs_b_use_different_thresholds(self):
        frame = pd.DataFrame(
            [
                {"from_url": "f1", "tech_lcs_u": 0.70, "tech_lcs_b": 0.70},
            ]
        )

        self.assertEqual([], list(select_one_stage_indices(frame, LinkStrategy.LCS_U)))
        self.assertEqual([0], list(select_one_stage_indices(frame, LinkStrategy.LCS_B)))

    def test_all_tc_tracer_technique_stages_have_strategy_keys(self):
        self.assertEqual(LinkStrategy.NC, strategies_from_keys(["nc"]))
        self.assertEqual(LinkStrategy.NCC, strategies_from_keys(["ncc"]))
        self.assertEqual(LinkStrategy.LCS_U, strategies_from_keys(["lcs-u"]))
        self.assertEqual(LinkStrategy.LCS_B, strategies_from_keys(["lcs-b"]))
        self.assertEqual(LinkStrategy.LEVEN, strategies_from_keys(["leven"]))
        self.assertEqual(LinkStrategy.LCBA, strategies_from_keys(["lcba"]))
        self.assertEqual(LinkStrategy.TARANTULA, strategies_from_keys(["tarantula"]))
        self.assertEqual(LinkStrategy.TFIDF, strategies_from_keys(["tfidf"]))
        self.assertEqual(LinkStrategy.COMBINED, strategies_from_keys(["combined"]))
        self.assertEqual(LinkStrategy.TESTLINKERV2, strategies_from_keys(["testlinkerv2"]))
        self.assertEqual("tarantula--combined", strategy_output_key(LinkStrategy.TARANTULA | LinkStrategy.COMBINED))

    def test_build_parser_accepts_comma_separated_strategies(self):
        args = build_parser().parse_args(["--strategies", "nc,ncc"])

        self.assertEqual("nc,ncc", args.strategies)

    def test_select_link_strategies_without_filter_returns_all(self):
        self.assertEqual(METHOD_LINK_STRATEGIES, select_link_strategies(None))

    def test_select_link_strategies_accepts_single_strategy(self):
        self.assertEqual([LinkStrategy.NC], select_link_strategies(["nc"]))

    def test_select_link_strategies_accepts_multiple_strategies_in_configured_order(self):
        self.assertEqual(
            [LinkStrategy.NC, LinkStrategy.NCC],
            select_link_strategies(["nc", "ncc"]),
        )

    def test_select_link_strategies_accepts_composite_strategy(self):
        self.assertEqual(
            [LinkStrategy.OMC | LinkStrategy.NC],
            select_link_strategies(["omc--nc"]),
        )

    def test_select_link_strategies_rejects_unknown_strategy(self):
        with self.assertRaisesRegex(ValueError, "Unknown strategy"):
            select_link_strategies(["unknown"])

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

    def test_testlinker_stage_selects_positive_predictions(self):
        frame = pd.DataFrame(
            [
                {"from_url": "f1", "tech_testlinker": ""},
                {"from_url": "f2", "tech_testlinker": "1"},
                {"from_url": "f3", "tech_testlinker": "0"},
            ]
        )

        indexes = select_one_stage_indices(frame, LinkStrategy.TESTLINKER)

        self.assertEqual([1], list(indexes))
        self.assertEqual("testlinker", strategy_output_key(LinkStrategy.TESTLINKER))

    def test_testlinkerv2_stage_selects_positive_predictions(self):
        frame = pd.DataFrame(
            [
                {"from_url": "f1", "tech_testlinkerv2": ""},
                {"from_url": "f2", "tech_testlinkerv2": "1"},
                {"from_url": "f3", "tech_testlinkerv2": "0"},
            ]
        )

        indexes = select_one_stage_indices(frame, LinkStrategy.TESTLINKERV2)

        self.assertEqual([1], list(indexes))
        self.assertEqual("testlinkerv2", strategy_output_key(LinkStrategy.TESTLINKERV2))

    def test_filters_test_case_methods_to_main_code(self):
        frame = pd.DataFrame(
            [
                {
                    "from_artifact": "#test-code #test-case-method",
                    "to_artifact": "#test-module #main-code",
                    "to_url": "main-in-test-module",
                },
                {
                    "from_artifact": "#test-code #test-helper-method",
                    "to_artifact": "#main-code",
                    "to_url": "helper-source",
                },
                {
                    "from_artifact": "#test-code #test-case-method",
                    "to_artifact": "#doc-module #main-code",
                    "to_url": "doc-main",
                },
            ]
        )

        filtered = filter_test_case_to_main_code_links(frame)

        self.assertEqual(["main-in-test-module", "doc-main"], filtered["to_url"].tolist())

    def test_project_index_uses_project_csv_order_instead_of_available_file_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            experiment_directory = Path(temp_dir)
            pd.DataFrame(
                {"project": ["z-project", "missing-project", "a-project"]}
            ).to_csv(experiment_directory / "project.csv", index=False)
            t2p_tech_directory = experiment_directory / "t2p-tech"
            t2p_tech_directory.mkdir()
            (t2p_tech_directory / "a-project.csv").touch()
            (t2p_tech_directory / "z-project.csv").touch()

            with mock.patch.dict("os.environ", {"ME_PROJECT_INDEX": "0"}):
                selected_files = select_t2p_tech_files(experiment_directory, None)

        self.assertEqual(["z-project.csv"], [path.name for path in selected_files])


if __name__ == "__main__":
    unittest.main()
