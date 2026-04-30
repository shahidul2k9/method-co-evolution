from pathlib import Path
import sys
import tempfile
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

try:
    import pandas as pd
except ImportError:  # pragma: no cover - local shell may not have pandas installed
    pd = None

from ptc.generator.generate_m2m_tech import (
    apply_llm_techniques,
    apply_testlinker_technique,
    apply_traceability_techniques,
    llm_strategy_directory_names,
)


@unittest.skipIf(pd is None, "pandas is required for generate_m2m_tech tests")
class TestApplyLlmTechniques(unittest.TestCase):
    def test_traceability_techniques_score_all_pairs_in_batch(self):
        candidate_df = pd.DataFrame(
            [
                {
                    "from_url": "test://CalculatorTest.testAdd",
                    "from_name": "testadd",
                    "to_url": "prod://Calculator.add",
                    "to_name": "add",
                    "to_call_depth": 1,
                    "to_lcba": 1,
                },
                {
                    "from_url": "test://CalculatorTest.testAdd",
                    "from_name": "testadd",
                    "to_url": "prod://Calculator.format",
                    "to_name": "format",
                    "to_call_depth": 2,
                    "to_lcba": 0,
                },
                {
                    "from_url": "test://CalculatorTest.testFormat",
                    "from_name": "testformat",
                    "to_url": "prod://Calculator.format",
                    "to_name": "format",
                    "to_call_depth": 1,
                    "to_lcba": 1,
                },
            ]
        )

        result_df = apply_traceability_techniques(candidate_df)

        for column_name in [
            "tech_nc",
            "tech_ncc",
            "tech_lcs_b",
            "tech_lcs_u",
            "tech_leven",
            "tech_lcba",
            "tech_tarantula",
            "tech_tfidf",
            "tech_combined",
        ]:
            self.assertIn(column_name, result_df.columns)

        self.assertEqual(1, result_df.loc[0, "tech_nc"])
        self.assertEqual(0, result_df.loc[1, "tech_nc"])
        self.assertEqual(1, result_df.loc[2, "tech_nc"])
        self.assertEqual(1, result_df.loc[0, "tech_lcba"])
        self.assertEqual(0, result_df.loc[1, "tech_lcba"])
        self.assertGreater(result_df.loc[0, "tech_tarantula"], result_df.loc[1, "tech_tarantula"])
        self.assertGreater(result_df.loc[0, "tech_tfidf"], result_df.loc[1, "tech_tfidf"])
        self.assertGreater(result_df.loc[0, "tech_combined"], result_df.loc[1, "tech_combined"])

    def test_name_similarity_techniques_use_pytctracer_scaling(self):
        candidate_df = pd.DataFrame(
            [
                {
                    "from_url": "test://CalculatorTest.testThing",
                    "from_name": "testthing",
                    "to_url": "prod://Util.thing",
                    "to_name": "thing",
                    "to_call_depth": 1,
                    "to_lcba": 0,
                },
                {
                    "from_url": "test://CalculatorTest.testThing",
                    "from_name": "testthing",
                    "to_url": "prod://Util.thin",
                    "to_name": "thin",
                    "to_call_depth": 2,
                    "to_lcba": 0,
                },
                {
                    "from_url": "test://OtherTest.testOther",
                    "from_name": "testother",
                    "to_url": "prod://Util.other",
                    "to_name": "other",
                    "to_call_depth": 1,
                    "to_lcba": 0,
                }
            ]
        )

        result_df = apply_traceability_techniques(candidate_df)

        self.assertEqual(1, result_df.loc[0, "tech_nc"])
        self.assertEqual(1, result_df.loc[0, "tech_ncc"])
        self.assertAlmostEqual(1.0, result_df.loc[0, "tech_lcs_b"])
        self.assertAlmostEqual(1.0, result_df.loc[0, "tech_lcs_u"])
        self.assertAlmostEqual(1.0, result_df.loc[0, "tech_leven"])
        self.assertLess(result_df.loc[1, "tech_lcs_b"], 1.0)
        self.assertLess(result_df.loc[1, "tech_lcs_u"], 1.0)
        self.assertLess(result_df.loc[1, "tech_leven"], 1.0)

    def test_existing_prediction_file_maps_rows_to_zero_or_one(self):
        candidate_df = pd.DataFrame(
            [
                {"from_url": "f1", "to_url": "t1"},
                {"from_url": "f1", "to_url": "t2"},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            prediction_root = Path(tmpdir)
            prediction_dir = prediction_root / "qwen_2d5b"
            prediction_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {"from_url": "f1", "to_url": "t1", "label_pred": 1},
                    {"from_url": "f1", "to_url": "t2", "label_pred": 0},
                ]
            ).to_csv(prediction_dir / "demo.csv", index=False)

            result_df = apply_llm_techniques(
                t2p_candidate_df=candidate_df,
                project="demo",
                llm_directory_names=["qwen_2d5b"],
                llm_prediction_root=prediction_root,
            )

            self.assertEqual([1, 0], result_df["tech_llm_qwen_2d5b"].tolist())

    def test_missing_prediction_file_creates_null_column(self):
        candidate_df = pd.DataFrame([{"from_url": "f1", "to_url": "t1"}])

        with tempfile.TemporaryDirectory() as tmpdir:
            result_df = apply_llm_techniques(
                t2p_candidate_df=candidate_df,
                project="demo",
                llm_directory_names=["gpt_oss_20b"],
                llm_prediction_root=Path(tmpdir),
            )

            self.assertIn("tech_llm_gpt_oss_20b", result_df.columns)
            self.assertTrue(result_df["tech_llm_gpt_oss_20b"].isna().all())

    def test_missing_prediction_row_stays_null_while_other_rows_map(self):
        candidate_df = pd.DataFrame(
            [
                {"from_url": "f1", "to_url": "t1"},
                {"from_url": "f1", "to_url": "t2"},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            prediction_root = Path(tmpdir)
            prediction_dir = prediction_root / "qwen_2d5b"
            prediction_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {"from_url": "f1", "to_url": "t1", "label_pred": 1},
                ]
            ).to_csv(prediction_dir / "demo.csv", index=False)

            result_df = apply_llm_techniques(
                t2p_candidate_df=candidate_df,
                project="demo",
                llm_directory_names=["qwen_2d5b"],
                llm_prediction_root=prediction_root,
            )

            self.assertEqual(1, result_df.loc[0, "tech_llm_qwen_2d5b"])
            self.assertTrue(pd.isna(result_df.loc[1, "tech_llm_qwen_2d5b"]))

    def test_multiple_models_add_multiple_columns(self):
        candidate_df = pd.DataFrame([{"from_url": "f1", "to_url": "t1", "tech_leven": 0.5}])

        with tempfile.TemporaryDirectory() as tmpdir:
            prediction_root = Path(tmpdir)
            qwen_prediction_dir = prediction_root / "qwen_2d5b"
            qwen_prediction_dir.mkdir(parents=True, exist_ok=True)
            pd.DataFrame(
                [
                    {"from_url": "f1", "to_url": "t1", "label_pred": 1},
                ]
            ).to_csv(qwen_prediction_dir / "demo.csv", index=False)

            result_df = apply_llm_techniques(
                t2p_candidate_df=candidate_df,
                project="demo",
                llm_directory_names=["qwen_2d5b", "gpt_oss_20b"],
                llm_prediction_root=prediction_root,
            )

            self.assertEqual(0.5, result_df.loc[0, "tech_leven"])
            self.assertEqual(1, result_df.loc[0, "tech_llm_qwen_2d5b"])
            self.assertTrue(pd.isna(result_df.loc[0, "tech_llm_gpt_oss_20b"]))

    def test_llm_strategy_directory_names_use_link_strategy_keys(self):
        self.assertEqual(
            ["gpt-oss-20b", "gpt-oss-120b", "qwen-2d5b"],
            llm_strategy_directory_names(),
        )

    def test_testlinker_prediction_file_maps_to_tech_column(self):
        candidate_df = pd.DataFrame(
            [
                {"from_url": "f1", "to_url": "t1"},
                {"from_url": "f1", "to_url": "t2"},
            ]
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            prediction_root = Path(tmpdir)
            pd.DataFrame(
                [
                    {"from_url": "f1", "to_url": "t1", "label_pred": 1},
                    {"from_url": "f1", "to_url": "t2", "label_pred": 0},
                ]
            ).to_csv(prediction_root / "demo.csv", index=False)

            result_df = apply_testlinker_technique(
                t2p_candidate_df=candidate_df,
                project="demo",
                testlinker_prediction_root=prediction_root,
            )

            self.assertEqual([1, 0], result_df["tech_testlinker"].tolist())

    def test_missing_testlinker_prediction_file_creates_null_column(self):
        candidate_df = pd.DataFrame([{"from_url": "f1", "to_url": "t1"}])

        with tempfile.TemporaryDirectory() as tmpdir:
            result_df = apply_testlinker_technique(
                t2p_candidate_df=candidate_df,
                project="demo",
                testlinker_prediction_root=Path(tmpdir),
            )

            self.assertIn("tech_testlinker", result_df.columns)
            self.assertTrue(result_df["tech_testlinker"].isna().all())


if __name__ == "__main__":
    unittest.main()
