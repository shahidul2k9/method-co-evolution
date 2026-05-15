from pathlib import Path
import sys
import unittest

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

try:
    import pandas as pd
except ImportError:  # pragma: no cover - local shell may not have pandas installed
    pd = None

from ptc.generator.expand_t2p_candidate import expand_candidate_df


@unittest.skipIf(pd is None, "pandas is required for expand candidate tests")
class TestExpandT2PCandidates(unittest.TestCase):
    def test_direct_call_depth_is_one(self):
        fan_out_df = pd.DataFrame(
            [
                {
                    "project": "demo",
                    "from_url": "test://A.testCopy",
                    "from_name": "testCopy",
                    "to_url": "prod://A.copy",
                    "to_name": "copy",
                    "to_call_depth": "",
                }
            ]
        )
        method_df = pd.DataFrame(
            [
                {"url": "test://A.testCopy", "artifact": "#test-code #test-case-method"},
                {"url": "prod://A.copy", "artifact": "#main-code"},
            ]
        )

        expanded_df = expand_candidate_df(fan_out_df, method_df)

        self.assertEqual(1, len(expanded_df))
        self.assertEqual(1, expanded_df.loc[0, "to_call_depth"])

    def test_test_helper_call_expands_to_main_code_with_depth(self):
        fan_out_df = pd.DataFrame(
            [
                {
                    "project": "demo",
                    "from_url": "test://A.testCopy",
                    "from_name": "testCopy",
                    "to_url": "test-util://A.helper",
                    "to_name": "helper",
                    "to_call_depth": "",
                    "to_caller_url": "",
                },
                {
                    "project": "demo",
                    "from_url": "test-util://A.helper",
                    "from_name": "helper",
                    "to_url": "prod://A.copy",
                    "to_name": "copy",
                    "to_call_depth": "",
                    "to_caller_url": "",
                },
            ]
        )
        method_df = pd.DataFrame(
            [
                {"url": "test://A.testCopy", "artifact": "#test-code #test-case-method"},
                {"url": "test-util://A.helper", "artifact": "#test-code #test-helper-method"},
                {"url": "prod://A.copy", "artifact": "#test-module #main-code"},
            ]
        )

        expanded_df = expand_candidate_df(fan_out_df, method_df)

        test_rows = expanded_df[expanded_df["from_url"] == "test://A.testCopy"].reset_index(drop=True)
        self.assertEqual(2, len(test_rows))
        self.assertEqual("test-util://A.helper", test_rows.loc[0, "to_url"])
        self.assertEqual(1, test_rows.loc[0, "to_call_depth"])
        self.assertEqual("prod://A.copy", test_rows.loc[1, "to_url"])
        self.assertEqual(2, test_rows.loc[1, "to_call_depth"])
        self.assertEqual("test-util://A.helper", test_rows.loc[1, "to_caller_url"])

    def test_duplicate_helper_calls_keep_original_rows_and_expand_once_per_occurrence(self):
        fan_out_df = pd.DataFrame(
            [
                {
                    "project": "demo",
                    "from_url": "test://A.testPlugins",
                    "from_name": "testPlugins",
                    "to_url": "test-util://A.findPlugin",
                    "to_name": "findPlugin",
                    "to_call_depth": "",
                    "to_caller_url": "",
                },
                {
                    "project": "demo",
                    "from_url": "test://A.testPlugins",
                    "from_name": "testPlugins",
                    "to_url": "test-util://A.findPlugin",
                    "to_name": "findPlugin",
                    "to_call_depth": "",
                    "to_caller_url": "",
                },
                {
                    "project": "demo",
                    "from_url": "test-util://A.findPlugin",
                    "from_name": "findPlugin",
                    "to_url": "prod://Plugin.getShortName",
                    "to_name": "getShortName",
                    "to_call_depth": "",
                    "to_caller_url": "",
                },
                {
                    "project": "demo",
                    "from_url": "test-util://A.findPlugin",
                    "from_name": "findPlugin",
                    "to_url": "test-util://A.findPlugin",
                    "to_name": "findPlugin",
                    "to_call_depth": "",
                    "to_caller_url": "",
                },
            ]
        )
        method_df = pd.DataFrame(
            [
                {"url": "test://A.testPlugins", "artifact": "#test-code #test-case-method"},
                {"url": "test-util://A.findPlugin", "artifact": "#test-code #test-helper-method"},
                {"url": "prod://Plugin.getShortName", "artifact": "#main-code"},
            ]
        )

        expanded_df = expand_candidate_df(fan_out_df, method_df)
        test_rows = expanded_df[expanded_df["from_url"] == "test://A.testPlugins"].reset_index(drop=True)

        self.assertEqual(
            ["findPlugin", "getShortName", "findPlugin", "getShortName"],
            test_rows["to_name"].tolist(),
        )
        self.assertEqual([1, 2, 1, 2], test_rows["to_call_depth"].tolist())


if __name__ == "__main__":
    unittest.main()
