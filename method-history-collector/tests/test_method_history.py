import unittest

import pandas as pd

from mhc.config import *
from mhc.method_history_collector import *

CODE_SHOVEL_REPOSITORIES = ["checkstyle", "commons-lang", "flink", "hibernate-orm", "javaparser", "jgit", "junit4",
                            "junit5", "okhttp", "spring-framework", "commons-io", "elasticsearch", "hadoop",
                            "hibernate-search", "intellij-community", "jetty.project", "lucene-solr", "mockito", "pmd",
                            "spring-boot"]


class MethodHistoryTestCase(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(MethodHistoryTestCase, self).__init__(*args, **kwargs)
        df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")
        self.repositories = df['name'].tolist()
        self.method_collector = MethodHistoryCollector(CACHE_DIRECTORY, REPOSITORY_DIRECTORY, DATA_DIRECTORY,
                                                       JAR_DIRECTORY)

    # def test_method_listing(self):
    #     self.method_collector.scan_method(self.repositories)

    # def test_history_collection(self):
    #     self.method_collector.collect_method_history(self.repositories, ['historyFinder'])

    # def test_repository_index(self):
    #     self.method_collector.update_repository_index()


if __name__ == '__main__':
    unittest.main()
