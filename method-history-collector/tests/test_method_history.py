import unittest
from mhc.method_history_collector import *
import pandas as pd

class MyTestCase(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(MyTestCase, self).__init__(*args, **kwargs)
        df = pd.read_csv("../../data/repository.csv")
        cache_dir = '../../.cache'
        self.repositories = df['name'].tolist()[1:2]
        self.method_collector =  MethodHistoryCollector(cache_dir, os.path.join(cache_dir, 'repository'), cache_dir,
                                                        os.path.join(cache_dir, 'lib'))
    def test_method_listing(self):
        self.method_collector.scan_method(self.repositories)

    def test_history_collection(self):
        self.method_collector.collect_method_history(self.repositories, ['codeShovel'])

if __name__ == '__main__':
    unittest.main()
