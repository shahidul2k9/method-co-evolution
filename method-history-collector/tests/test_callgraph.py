import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.callgraph import execute_callgraph_if_missing


class CallGraphRunnerTest(unittest.TestCase):
    def test_passes_method_mapping_file_when_method_scan_exists(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            root = Path(temp_directory)
            data_directory = root / "data"
            method_mapping_file = data_directory / "method" / "demo.csv"
            method_mapping_file.parent.mkdir(parents=True)
            method_mapping_file.write_text("project,name\n", encoding="utf-8")

            repository_df = pd.DataFrame(
                [
                    {
                        "project": "demo",
                        "url": "https://github.com/example/demo",
                        "updated_hash": "abc123",
                    }
                ]
            )

            with patch("mhc.callgraph.git.clone_and_checkout_commit"), patch(
                "mhc.callgraph.subprocess.run"
            ) as run_command:
                execute_callgraph_if_missing(
                    repository_df,
                    str(root / "repository"),
                    str(data_directory),
                    str(root / "cache"),
                    "methodParser",
                    {"methodParser": "method-parser.jar"},
                )

            command = run_command.call_args.args[0]
            self.assertIn("-method-mapping-file", command)
            self.assertEqual(
                str(method_mapping_file),
                command[command.index("-method-mapping-file") + 1],
            )


if __name__ == "__main__":
    unittest.main()
