import sys
import unittest
from pathlib import Path

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.config import (
    resolve_experiment_directory,
    resolve_experiment_output_directory,
    resolve_history_directory,
    resolve_jar_directory,
    resolve_repository_directory,
)


class TestExperimentPaths(unittest.TestCase):
    def test_explicit_experiment_resolves_runtime_directories_under_workspace(self):
        workspace = "/tmp/workspace"

        self.assertEqual(Path("/tmp/workspace/experiment/exp-a"), resolve_experiment_directory(workspace, "exp-a"))
        self.assertEqual(
            Path("/tmp/workspace/experiment/exp-a"),
            resolve_experiment_output_directory(workspace, "exp-a"),
        )
        self.assertEqual(
            Path("/tmp/workspace/experiment/exp-a/history"),
            resolve_history_directory(workspace, "exp-a"),
        )
        self.assertEqual(
            Path("/tmp/workspace/experiment/exp-a/repository"),
            resolve_repository_directory(workspace, "exp-a"),
        )

    def test_shared_jar_stays_under_base_workspace(self):
        self.assertEqual(Path("/tmp/workspace/jar"), resolve_jar_directory("/tmp/workspace"))

if __name__ == "__main__":
    unittest.main()
