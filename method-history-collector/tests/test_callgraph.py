import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.callgraph import (
    CALLGRAPH_CACHE_COLUMNS,
    CALLGRAPH_COLUMNS,
    CALLGRAPH_ERROR_COLUMN,
    CALLGRAPH_ERROR_MAX_LENGTH,
    CALLGRAPH_ERROR_MARKER,
    CALLGRAPH_FLAG_COLUMN,
    _build_callgraph_error_marker,
    _build_callgraph_scan_marker,
    _finalize_callgraph,
    _fan_in_from_fan_out,
    _load_cached_callgraph_files,
)


class CallGraphRunnerTest(unittest.TestCase):
    def test_fan_in_from_fan_out_swaps_callee_and_caller(self):
        fan_out = pd.DataFrame(
            [
                {
                    "project": "demo",
                    "from_name": "caller",
                    "to_name": "callee",
                    "from_url": "caller-url",
                    "to_url": "callee-url",
                    "from_expression": "method",
                    "to_expression": "method_call",
                    "from_pkg": "demo",
                    "to_pkg": "demo.target",
                    "from_fqn": "demo.Caller.caller",
                    "to_fqn": "demo.Target.callee",
                    "from_fqs": "demo.Caller.caller()",
                    "from_tctracer_fqs": "caller()",
                    "from_testlinker_fqs": "caller()",
                    "from_testlinker_fqp": "[]",
                    "to_fqs": "demo.Target.callee()",
                    "to_tctracer_fqs": "callee()",
                    "to_testlinker_fqs": "callee()",
                    "to_testlinker_fqp": "[]",
                    "from_start": 10,
                    "from_end": 20,
                    "to_start": 30,
                    "to_end": 40,
                    "from_invocation": 15,
                    "to_invocation": None,
                    "from_lcba": 0,
                    "to_lcba": 1,
                    "from_file": "src/Caller.java",
                    "to_file": "src/Target.java",
                    "from_caller_url": None,
                    "to_caller_url": None,
                    "from_call_depth": None,
                    "to_call_depth": None,
                    "hash": "abc123",
                    "from_resolver": "javaparser",
                    "to_resolver": "mapping",
                }
            ],
            columns=CALLGRAPH_COLUMNS,
        )

        fan_in = _fan_in_from_fan_out(fan_out)

        self.assertEqual(["callee"], fan_in["from_name"].tolist())
        self.assertEqual(["caller"], fan_in["to_name"].tolist())
        self.assertEqual(["callee-url"], fan_in["from_url"].tolist())
        self.assertEqual(["caller-url"], fan_in["to_url"].tolist())
        self.assertTrue(fan_in["from_invocation"].isna().all())
        self.assertTrue(fan_in["to_invocation"].isna().all())
        self.assertEqual(CALLGRAPH_COLUMNS, fan_in.columns.tolist())

    def test_finalize_callgraph_writes_callgraph_and_fanin_outputs(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / "cache.csv"
            lock_file = root / "cache.lock"
            callgraph_file = root / "data" / "callgraph" / "demo.csv"
            fanin_file = root / "data" / "fanin" / "demo.csv"
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "from_file": "src/Caller.java",
                        "from_name": "caller",
                        "to_name": "callee",
                        "from_url": "caller-url",
                        "to_url": "callee-url",
                        "hash": "abc123",
                    }
                ],
                columns=CALLGRAPH_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = _finalize_callgraph(
                str(cache_file),
                str(callgraph_file),
                str(fanin_file),
                str(root / "data" / ".callgraph-error" / "demo.csv"),
                {"src/Caller.java"},
                str(lock_file),
            )

            self.assertTrue(merged)
            self.assertFalse(cache_file.exists())
            self.assertFalse(lock_file.exists())
            self.assertEqual(["caller"], pd.read_csv(callgraph_file)["from_name"].tolist())
            self.assertEqual(["callee"], pd.read_csv(fanin_file)["from_name"].tolist())

    def test_error_markers_are_retryable_for_shard_processing(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            cache_file = Path(temp_directory) / "cache.csv"
            pd.DataFrame(
                [
                    _build_callgraph_error_marker("src/Broken.java"),
                    _build_callgraph_scan_marker("src/Done.java"),
                    {
                        **{col: None for col in CALLGRAPH_CACHE_COLUMNS},
                        "from_file": "src/Caller.java",
                        "from_name": "caller",
                        "to_name": "callee",
                        "hash": "abc123",
                    },
                ],
                columns=CALLGRAPH_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            self.assertEqual(
                {"src/Done.java", "src/Caller.java"},
                _load_cached_callgraph_files(str(cache_file)),
            )

    def test_finalize_waits_until_all_files_are_tried(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / "cache.csv"
            lock_file = root / "cache.lock"
            callgraph_file = root / "data" / "callgraph" / "demo.csv"
            fanin_file = root / "data" / "fanin" / "demo.csv"
            error_file = root / "data" / ".callgraph-error" / "demo.csv"
            lock_file.write_text("", encoding="utf-8")
            pd.DataFrame(
                [_build_callgraph_scan_marker("src/Done.java")],
                columns=CALLGRAPH_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = _finalize_callgraph(
                str(cache_file),
                str(callgraph_file),
                str(fanin_file),
                str(error_file),
                {"src/Done.java", "src/Missing.java"},
                str(lock_file),
            )

            self.assertFalse(merged)
            self.assertTrue(cache_file.exists())
            self.assertTrue(lock_file.exists())
            self.assertFalse(callgraph_file.exists())
            self.assertFalse(fanin_file.exists())

    def test_finalize_writes_failed_files_to_callgraph_error_folder(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            cache_file = root / "cache.csv"
            callgraph_file = root / "data" / "callgraph" / "demo.csv"
            fanin_file = root / "data" / "fanin" / "demo.csv"
            error_file = root / "data" / ".callgraph-error" / "demo.csv"
            pd.DataFrame(
                [
                    {
                        **{col: None for col in CALLGRAPH_CACHE_COLUMNS},
                        "project": "demo",
                        "from_file": "src/Caller.java",
                        "from_name": "caller",
                        "to_name": "callee",
                        "hash": "abc123",
                    },
                    _build_callgraph_error_marker("src/Broken.java"),
                    _build_callgraph_scan_marker("src/Empty.java"),
                ],
                columns=CALLGRAPH_CACHE_COLUMNS,
            ).to_csv(cache_file, index=False)

            merged = _finalize_callgraph(
                str(cache_file),
                str(callgraph_file),
                str(fanin_file),
                str(error_file),
                {"src/Caller.java", "src/Broken.java", "src/Empty.java"},
            )

            self.assertTrue(merged)
            self.assertFalse(cache_file.exists())
            self.assertEqual(["caller"], pd.read_csv(callgraph_file)["from_name"].tolist())
            error_df = pd.read_csv(error_file)
            self.assertEqual(["src/Broken.java"], error_df["from_file"].tolist())
            self.assertEqual([CALLGRAPH_ERROR_MARKER], error_df[CALLGRAPH_FLAG_COLUMN].tolist())
            self.assertIn(CALLGRAPH_ERROR_COLUMN, error_df.columns)

    def test_error_marker_stores_truncated_error_text_in_private_column(self):
        marker = _build_callgraph_error_marker("src/Broken.java", "x" * 300)

        self.assertEqual(CALLGRAPH_ERROR_MARKER, marker[CALLGRAPH_FLAG_COLUMN])
        self.assertEqual(CALLGRAPH_ERROR_MAX_LENGTH, len(marker[CALLGRAPH_ERROR_COLUMN]))


if __name__ == "__main__":
    unittest.main()
