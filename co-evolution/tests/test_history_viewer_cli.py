from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PTC_SRC_DIRECTORY = REPOSITORY_ROOT / "co-evolution" / "src"
if str(PTC_SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PTC_SRC_DIRECTORY))

from ptc.history_viewer.cli import build_reload_child_command, has_snapshot_changed, snapshot_mtimes


class TestHistoryViewerCli(unittest.TestCase):
    def test_build_reload_child_command_preserves_serve_arguments(self) -> None:
        args = argparse.Namespace(
            host="127.0.0.1",
            port=8765,
            workspace_directory="/tmp/cache",
            experiment_name="exp-a",
        )

        command = build_reload_child_command(args)

        self.assertEqual(sys.executable, command[0])
        self.assertEqual(["-m", "ptc.history_viewer.cli", "serve"], command[1:4])
        self.assertIn("--workspace-directory", command)
        self.assertIn("/tmp/cache", command)
        self.assertIn("--experiment-name", command)
        self.assertIn("exp-a", command)

    def test_snapshot_change_detects_file_modification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            file_path = root / "viewer.py"
            file_path.write_text("print('v1')\n", encoding="utf-8")

            first = snapshot_mtimes([file_path])
            file_path.write_text("print('v2')\n", encoding="utf-8")
            second = snapshot_mtimes([file_path])

            self.assertTrue(has_snapshot_changed(first, second))


if __name__ == "__main__":
    unittest.main()
