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

from ptc.generator.filter_t2p_candidate_ground_truth import (
    filter_candidate_df,
)


@unittest.skipIf(pd is None, "pandas is required for candidate filter tests")
class TestFilterT2PCandidateGroundTruth(unittest.TestCase):
    def test_filter_candidate_df_keeps_only_ground_truth_from_methods(self):
        candidate_df = pd.DataFrame(
            [
                {"from_url": "test://one", "to_url": "prod://a"},
                {"from_url": "test://one", "to_url": "prod://b"},
                {"from_url": "test://two", "to_url": "prod://c"},
            ]
        )
        ground_truth_df = pd.DataFrame([{"from_url": "test://one"}])

        filtered_df = filter_candidate_df(candidate_df, ground_truth_df)

        self.assertEqual(2, len(filtered_df))
        self.assertEqual({"test://one"}, set(filtered_df["from_url"]))


if __name__ == "__main__":
    unittest.main()
