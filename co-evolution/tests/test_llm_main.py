from pathlib import Path
import sys
import unittest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PTC_SRC_DIRECTORY = REPOSITORY_ROOT / "co-evolution" / "src"
MHC_SRC_DIRECTORY = REPOSITORY_ROOT / "method-history-collector" / "src"
for source_directory in (PTC_SRC_DIRECTORY, MHC_SRC_DIRECTORY):
    if str(source_directory) not in sys.path:
        sys.path.insert(0, str(source_directory))

from mhc.constant import CACHE_DIRECTORY
from ptc.llm.main import default_output_root, resolve_input_file

TEST_CACHE_DIRECTORY = Path(CACHE_DIRECTORY) / "test" / "llm-m2m-link"


class TestLlmMainHelpers(unittest.TestCase):
    def test_resolve_input_file_from_cache_directory_for_t2p(self):
        input_file = resolve_input_file(str(TEST_CACHE_DIRECTORY), "commons-io", "t2p")

        self.assertEqual(
            TEST_CACHE_DIRECTORY / "data" / "t2p-candidate" / "commons-io.csv",
            input_file,
        )

    def test_resolve_input_file_from_cache_directory_for_p2t(self):
        input_file = resolve_input_file(str(TEST_CACHE_DIRECTORY), "commons-io", "p2t")

        self.assertEqual(
            TEST_CACHE_DIRECTORY / "data" / "fan-in" / "commons-io.csv",
            input_file,
        )

    def test_default_output_root_uses_cache_directory_when_present(self):
        self.assertEqual(
            TEST_CACHE_DIRECTORY / "data" / "llm",
            default_output_root(str(TEST_CACHE_DIRECTORY)),
        )


if __name__ == "__main__":
    unittest.main()
