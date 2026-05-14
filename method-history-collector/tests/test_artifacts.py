import sys
import unittest
from pathlib import Path

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.artifacts import encode_tags, has_tag, is_test_case_method, is_production, is_main_code


class ArtifactHelperTest(unittest.TestCase):
    def test_encode_and_has_tag_use_hash_delimited_tags(self):
        artifact = encode_tags(["test-code", "test-case-method"])

        self.assertEqual("#test-code #test-case-method", artifact)
        self.assertTrue(has_tag(artifact, "test-case-method"))
        self.assertTrue(has_tag(artifact, "#test-case-method"))
        self.assertTrue(is_test_case_method(artifact))
        self.assertFalse(has_tag(artifact, "test"))

    def test_has_tag_tolerates_legacy_compact_tags(self):
        artifact = "#test-code#test-case-method"

        self.assertTrue(has_tag(artifact, "test-case-method"))
        self.assertFalse(has_tag(artifact, "test"))

    def test_production_code_helper(self):
        self.assertTrue(is_main_code("#test-module #main-code"))
        self.assertTrue(is_production("#main-code"))
        self.assertFalse(is_production("#test-module #main-code"))
        self.assertFalse(is_production("#doc-module #main-code"))
        self.assertFalse(is_production("#main-resource"))


if __name__ == "__main__":
    unittest.main()
