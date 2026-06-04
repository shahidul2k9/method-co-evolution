from contextlib import redirect_stdout
from io import StringIO
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

if pd is not None:
    from ptc.generator.filter_t2p_candidate import (
        filter_candidate_df,
        filter_candidate_df_by_ground_truth,
        filter_expanded_candidate_files,
        filter_expanded_candidate_files_by_ground_truth,
    )
    from ptc.generator.run_stats import GenerationStats


@unittest.skipIf(pd is None, "pandas is required for filter candidate tests")
class TestFilterT2PCandidates(unittest.TestCase):
    def test_filter_candidate_df_drops_unneeded_alt_signature_columns(self):
        candidate_df = pd.DataFrame(
            [
                {
                    "from_url": "test://one",
                    "from_fqs_alt": "alt test",
                    "to_url": "prod://a",
                    "to_fqs_alt": "alt prod",
                }
            ]
        )

        filtered_df = filter_candidate_df(candidate_df)

        self.assertEqual(["from_url", "to_url"], filtered_df.columns.tolist())

    def test_filter_candidate_df_by_ground_truth_keeps_only_ground_truth_from_methods(self):
        candidate_df = pd.DataFrame(
            [
                {"from_url": "test://one", "to_url": "prod://a"},
                {"from_url": "test://one", "to_url": "prod://b"},
                {"from_url": "test://two", "to_url": "prod://c"},
            ]
        )
        ground_truth_df = pd.DataFrame([{"from_url": "test://one"}])

        filtered_df = filter_candidate_df_by_ground_truth(candidate_df, ground_truth_df)

        self.assertEqual(2, len(filtered_df))
        self.assertEqual({"test://one"}, set(filtered_df["from_url"]))

    def test_filter_expanded_candidate_files_writes_default_filtered_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expanded_dir = root / "t2p-candidate-expanded"
            filtered_dir = root / "t2p-candidate-filtered"
            expanded_dir.mkdir()
            filtered_dir.mkdir()
            pd.DataFrame(
                [
                    {
                        "from_url": "test://one",
                        "from_fqs_alt": "alt test",
                        "to_url": "prod://a",
                        "to_fqs_alt": "alt prod",
                    }
                ]
            ).to_csv(expanded_dir / "demo.csv", index=False)

            stats = GenerationStats("test")
            with redirect_stdout(StringIO()):
                filter_expanded_candidate_files(
                    expanded_dir,
                    filtered_dir,
                    selected_projects=None,
                    replace=False,
                    stats=stats,
                )

            output_df = pd.read_csv(filtered_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(["from_url", "to_url"], output_df.columns.tolist())
            self.assertEqual([{"from_url": "test://one", "to_url": "prod://a"}], output_df.to_dict("records"))
            self.assertEqual(1, stats.recreated)
            self.assertEqual(1, stats.rows_written)

    def test_filter_expanded_candidate_files_by_ground_truth_filters_matching_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expanded_dir = root / "t2p-candidate-expanded"
            filtered_dir = root / "t2p-candidate-filtered"
            ground_truth_dir = root / "t2p-ground-truth"
            expanded_dir.mkdir()
            filtered_dir.mkdir()
            ground_truth_dir.mkdir()
            pd.DataFrame(
                [
                    {"from_url": "test://one", "from_fqs_alt": "alt", "to_url": "prod://a", "to_fqs_alt": "alt"},
                    {"from_url": "test://two", "from_fqs_alt": "alt", "to_url": "prod://b", "to_fqs_alt": "alt"},
                ]
            ).to_csv(expanded_dir / "demo.csv", index=False)
            pd.DataFrame([{"from_url": "test://one"}]).to_csv(ground_truth_dir / "demo.csv", index=False)

            stats = GenerationStats("test")
            with redirect_stdout(StringIO()):
                filter_expanded_candidate_files_by_ground_truth(
                    expanded_dir,
                    filtered_dir,
                    ground_truth_dir,
                    selected_projects=None,
                    replace=False,
                    stats=stats,
                )

            output_df = pd.read_csv(filtered_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual(["from_url", "to_url"], output_df.columns.tolist())
            self.assertEqual([{"from_url": "test://one", "to_url": "prod://a"}], output_df.to_dict("records"))
            self.assertEqual(1, stats.recreated)
            self.assertEqual(1, stats.rows_written)

    def test_filter_expanded_candidate_files_by_ground_truth_deletes_stale_output_when_missing_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expanded_dir = root / "t2p-candidate-expanded"
            filtered_dir = root / "t2p-candidate-filtered"
            ground_truth_dir = root / "t2p-ground-truth"
            expanded_dir.mkdir()
            filtered_dir.mkdir()
            ground_truth_dir.mkdir()
            pd.DataFrame([{"from_url": "test://one", "to_url": "prod://a"}]).to_csv(
                expanded_dir / "demo.csv",
                index=False,
            )
            stale_output = filtered_dir / "demo.csv"
            pd.DataFrame([{"from_url": "stale://test", "to_url": "stale://prod"}]).to_csv(
                stale_output,
                index=False,
            )

            stats = GenerationStats("test")
            with redirect_stdout(StringIO()):
                filter_expanded_candidate_files_by_ground_truth(
                    expanded_dir,
                    filtered_dir,
                    ground_truth_dir,
                    selected_projects=None,
                    replace=False,
                    stats=stats,
                )

            self.assertFalse(stale_output.exists())
            self.assertEqual(1, stats.deleted_stale)
            self.assertEqual(1, stats.skipped_missing_input)

    def test_filter_expanded_candidate_files_by_ground_truth_does_not_create_output_when_missing_ground_truth(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expanded_dir = root / "t2p-candidate-expanded"
            filtered_dir = root / "t2p-candidate-filtered"
            ground_truth_dir = root / "t2p-ground-truth"
            expanded_dir.mkdir()
            filtered_dir.mkdir()
            ground_truth_dir.mkdir()
            pd.DataFrame([{"from_url": "test://one", "to_url": "prod://a"}]).to_csv(
                expanded_dir / "demo.csv",
                index=False,
            )

            stats = GenerationStats("test")
            with redirect_stdout(StringIO()):
                filter_expanded_candidate_files_by_ground_truth(
                    expanded_dir,
                    filtered_dir,
                    ground_truth_dir,
                    selected_projects=None,
                    replace=False,
                    stats=stats,
                )

            self.assertFalse((filtered_dir / "demo.csv").exists())
            self.assertEqual(1, stats.missing_stale)
            self.assertEqual(1, stats.skipped_missing_input)

    def test_filter_expanded_candidate_files_skips_existing_without_replace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expanded_dir = root / "t2p-candidate-expanded"
            filtered_dir = root / "t2p-candidate-filtered"
            expanded_dir.mkdir()
            filtered_dir.mkdir()
            pd.DataFrame([{"from_url": "test://new", "to_url": "prod://new"}]).to_csv(
                expanded_dir / "demo.csv",
                index=False,
            )
            pd.DataFrame([{"from_url": "test://old", "to_url": "prod://old"}]).to_csv(
                filtered_dir / "demo.csv",
                index=False,
            )

            stats = GenerationStats("test")
            with redirect_stdout(StringIO()) as stdout:
                filter_expanded_candidate_files(
                    expanded_dir,
                    filtered_dir,
                    selected_projects=None,
                    replace=False,
                    stats=stats,
                )

            output_df = pd.read_csv(filtered_dir / "demo.csv", keep_default_na=False, na_filter=False)
            self.assertEqual("test://old", output_df["from_url"].iloc[0])
            self.assertIn("Skipping existing: demo", stdout.getvalue())
            self.assertEqual(1, stats.skipped_existing)

    def test_filter_expanded_candidate_files_deletes_stale_output_for_empty_candidate_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expanded_dir = root / "t2p-candidate-expanded"
            filtered_dir = root / "t2p-candidate-filtered"
            expanded_dir.mkdir()
            filtered_dir.mkdir()
            (expanded_dir / "demo.csv").write_text("", encoding="utf-8")
            stale_output = filtered_dir / "demo.csv"
            pd.DataFrame([{"from_url": "test://old", "to_url": "prod://old"}]).to_csv(
                stale_output,
                index=False,
            )

            stats = GenerationStats("test")
            with redirect_stdout(StringIO()):
                filter_expanded_candidate_files(
                    expanded_dir,
                    filtered_dir,
                    selected_projects=None,
                    replace=False,
                    stats=stats,
                )

            self.assertFalse(stale_output.exists())
            self.assertEqual(1, stats.empty_output)
            self.assertEqual(1, stats.deleted_stale)

    def test_filter_expanded_candidate_files_by_ground_truth_skips_empty_ground_truth_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            expanded_dir = root / "t2p-candidate-expanded"
            filtered_dir = root / "t2p-candidate-filtered"
            ground_truth_dir = root / "t2p-ground-truth"
            expanded_dir.mkdir()
            filtered_dir.mkdir()
            ground_truth_dir.mkdir()
            pd.DataFrame([{"from_url": "test://one", "to_url": "prod://a"}]).to_csv(
                expanded_dir / "demo.csv",
                index=False,
            )
            (ground_truth_dir / "demo.csv").write_text("", encoding="utf-8")
            stale_output = filtered_dir / "demo.csv"
            pd.DataFrame([{"from_url": "test://old", "to_url": "prod://old"}]).to_csv(
                stale_output,
                index=False,
            )

            stats = GenerationStats("test")
            with redirect_stdout(StringIO()):
                filter_expanded_candidate_files_by_ground_truth(
                    expanded_dir,
                    filtered_dir,
                    ground_truth_dir,
                    selected_projects=None,
                    replace=False,
                    stats=stats,
                )

            self.assertFalse(stale_output.exists())
            self.assertEqual(1, stats.empty_output)
            self.assertEqual(1, stats.deleted_stale)


if __name__ == "__main__":
    unittest.main()
