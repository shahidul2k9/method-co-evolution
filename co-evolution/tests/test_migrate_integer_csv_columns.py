import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.migrate_integer_csv_columns import (
    migrate_file,
    normalize_integer_columns,
    parse_targets,
    run_migration,
)


class IntegerCsvMigrationTest(unittest.TestCase):
    def test_normalize_integer_columns_repairs_float_shaped_values(self):
        df = pd.DataFrame(
            {
                "start_line": ["72.0", 80.0, "96", "", None, "12.5"],
                "name": ["a", "b", "c", "d", "e", "f"],
            }
        )

        normalized = normalize_integer_columns(df, ["start_line"])

        self.assertEqual(["72", "80", "96", "", "", "12.5"], normalized["start_line"].tolist())
        self.assertEqual(["a", "b", "c", "d", "e", "f"], normalized["name"].tolist())

    def test_migrate_file_rewrites_method_csv_and_creates_backup(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            csv_file = Path(temp_directory) / "lucene.csv"
            pd.DataFrame(
                [
                    {
                        "name": "testBigrams",
                        "start_line": "72.0",
                        "end_line": 80.0,
                        "abstract": "0.0",
                    }
                ]
            ).to_csv(csv_file, index=False)

            result = migrate_file(csv_file, "method", backup=True)

            self.assertTrue(result.written)
            self.assertEqual(1, result.changed_rows)
            self.assertEqual(3, result.changed_cells)
            self.assertTrue((Path(temp_directory) / "bk_lucene.csv").exists())
            output = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual("72", output.loc[0, "start_line"])
            self.assertEqual("80", output.loc[0, "end_line"])
            self.assertEqual("0", output.loc[0, "abstract"])

    def test_migrate_file_dry_run_does_not_write(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            csv_file = Path(temp_directory) / "lucene.csv"
            pd.DataFrame([{"from_start": "72.0", "to_lcba": "0.0"}]).to_csv(csv_file, index=False)

            result = migrate_file(csv_file, "callgraph", dry_run=True)

            self.assertFalse(result.written)
            output = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual("72.0", output.loc[0, "from_start"])
            self.assertEqual("0.0", output.loc[0, "to_lcba"])

    def test_run_migration_filters_projects_and_targets(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            data_directory = Path(temp_directory)
            method_dir = data_directory / "method"
            callgraph_dir = data_directory / "callgraph"
            method_dir.mkdir()
            callgraph_dir.mkdir()
            pd.DataFrame([{"start_line": "72.0"}]).to_csv(method_dir / "lucene.csv", index=False)
            pd.DataFrame([{"start_line": "82.0"}]).to_csv(method_dir / "jgit.csv", index=False)
            pd.DataFrame([{"from_start": "96.0"}]).to_csv(callgraph_dir / "lucene.csv", index=False)

            results = run_migration(data_directory, ["method"], projects={"lucene"})

            self.assertEqual(1, len(results))
            lucene = pd.read_csv(method_dir / "lucene.csv", dtype=str, keep_default_na=False, na_filter=False)
            jgit = pd.read_csv(method_dir / "jgit.csv", dtype=str, keep_default_na=False, na_filter=False)
            callgraph = pd.read_csv(callgraph_dir / "lucene.csv", dtype=str, keep_default_na=False, na_filter=False)
            self.assertEqual("72", lucene.loc[0, "start_line"])
            self.assertEqual("82.0", jgit.loc[0, "start_line"])
            self.assertEqual("96.0", callgraph.loc[0, "from_start"])

    def test_parse_targets_rejects_unknown_target(self):
        with self.assertRaises(Exception):
            parse_targets("method,unknown")


if __name__ == "__main__":
    unittest.main()
