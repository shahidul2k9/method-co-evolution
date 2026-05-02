import unittest
import tempfile
from pathlib import Path

import mhc.util as util


class UtilCase(unittest.TestCase):
    def test_method_file_to_url_conversion(self):
        method_url = util.convert_method_file_to_method_url("https://github.com/elastic/elasticsearch",
                                                            "92be385f8ea3d39cc42155417d208ba82423d983",
                                                            "test/framework/src/main/java/org/elasticsearch/action/support/ActionTestUtils--assertNoFailureListener--61.json")
        self.assertEqual(
            "https://github.com/elastic/elasticsearch/blob/92be385f8ea3d39cc42155417d208ba82423d983/test/framework/src/main/java/org/elasticsearch/action/support/ActionTestUtils.java#L61",
            method_url)

    def test_stable_shard_for_key_is_one_based_and_repeatable(self):
        shard = util.stable_shard_for_key("src/Foo--bar--10.json", 20)
        self.assertGreaterEqual(shard, 1)
        self.assertLessEqual(shard, 20)
        self.assertEqual(shard, util.stable_shard_for_key("src/Foo--bar--10.json", 20))

    def test_java_options_with_logback_config_uses_cache_config_when_present(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            cache_directory = Path(temp_directory)
            logback_file = cache_directory / "config" / "logback.xml"
            logback_file.parent.mkdir(parents=True)
            logback_file.write_text("<configuration />", encoding="utf-8")

            options = util.java_options_with_logback_config("-Xmx2g", str(cache_directory))

            self.assertIn("-Xmx2g", options)
            self.assertIn(f"-Dlogback.configurationFile={logback_file}", options)

    def test_java_options_with_logback_config_leaves_options_when_config_missing(self):
        with tempfile.TemporaryDirectory() as temp_directory:
            self.assertEqual(
                "-Xmx2g",
                util.java_options_with_logback_config("-Xmx2g", temp_directory),
            )
if __name__ == '__main__':
    unittest.main()
