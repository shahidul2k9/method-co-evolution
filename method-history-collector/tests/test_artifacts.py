import sys
import unittest
from pathlib import Path

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.artifacts import encode_tags, has_tag, is_test_method, is_production_code


class ArtifactHelperTest(unittest.TestCase):
    def test_encode_and_has_tag_use_hash_delimited_tags(self):
        artifact = encode_tags(["test-code", "test-unit", "test-method"])

        self.assertEqual("#test-code #test-unit #test-method", artifact)
        self.assertTrue(has_tag(artifact, "test-method"))
        self.assertTrue(has_tag(artifact, "#test-method"))
        self.assertTrue(is_test_method(artifact))
        self.assertFalse(has_tag(artifact, "test"))

    def test_has_tag_tolerates_legacy_compact_tags(self):
        artifact = "#test-code#test-unit#test-method"

        self.assertTrue(has_tag(artifact, "test-method"))
        self.assertFalse(has_tag(artifact, "test"))

    def test_production_code_helper(self):
        self.assertTrue(is_production_code("#production-code"))
        self.assertFalse(is_production_code("#production-resource"))


if __name__ == "__main__":
    unittest.main()
