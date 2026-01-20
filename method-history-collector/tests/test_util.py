import unittest

import mhc.util as util


class UtilCase(unittest.TestCase):
    def test_method_file_to_url_conversion(self):
        method_url = util.convert_method_file_to_method_url("https://github.com/elastic/elasticsearch",
                                                            "92be385f8ea3d39cc42155417d208ba82423d983",
                                                            "test/framework/src/main/java/org/elasticsearch/action/support/ActionTestUtils--assertNoFailureListener--61.json")
        self.assertEqual(
            "https://github.com/elastic/elasticsearch/blob/92be385f8ea3d39cc42155417d208ba82423d983/test/framework/src/main/java/org/elasticsearch/action/support/ActionTestUtils.java#L61",
            method_url)
if __name__ == '__main__':
    unittest.main()
