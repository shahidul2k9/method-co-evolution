import unittest
from mhc.method_history_collector import *
import pandas as pd

CODE_SHOVEL_REPOSITORIES = ["checkstyle", "commons-lang", "flink", "hibernate-orm", "javaparser", "jgit", "junit4",
                            "junit5", "okhttp", "spring-framework", "commons-io", "elasticsearch", "hadoop",
                            "hibernate-search", "intellij-community", "jetty.project", "lucene-solr", "mockito", "pmd",
                            "spring-boot"]


class MyTestCase(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(MyTestCase, self).__init__(*args, **kwargs)
        df = pd.read_csv("data/repository.csv")
        cache_dir = '.cache'
        filtered_repositories = df['name'].tolist()
        for name in ['jclouds', 'Essentials']:
            filtered_repositories.remove(name)
        # self.repositories = filtered_repositories
        self.repositories = CODE_SHOVEL_REPOSITORIES
        # self.repositories = ['checkstyle']
        self.method_collector = MethodHistoryCollector(cache_dir, os.path.join(cache_dir, 'repository'),
                                                       os.path.join(cache_dir, "data"), "repository.csv",
                                                       os.path.join(cache_dir, 'jar'))

    def test_method_listing(self):
        self.method_collector.scan_method(self.repositories)

    def test_history_collection(self):
        self.method_collector.collect_method_history(self.repositories, ['historyFinder'])

    def test_history_collection_with_command_line(self):
        self.method_collector.collect_method_history(self.repositories, ['historyFinder'])

    def test_method_history_index(self):
        self.method_collector.update_execute_index()


if __name__ == '__main__':
    unittest.main()
