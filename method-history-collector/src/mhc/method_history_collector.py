
import mhc.method_scanner as ms
from mhc.method_history_jar_runner import *
from pathlib import Path
import os
import pandas as pd


class MethodHistoryCollector:
    def __init__(self, cache_directory: str, repository_directory, data_directory, jar_directory: str):
        self.cache_directory = cache_directory
        self.repository_directory = repository_directory
        self.data_directory = data_directory
        self.jar_file_map = {}
        self.repository_df = pd.read_csv(os.path.join(data_directory, 'repository.csv'))

        patterns = ['javaParser', 'codeShovel', 'historyFinder', 'codeTracker']
        for file in list(map(os.fspath, Path(jar_directory).rglob("*.jar"))):
            for pattern in patterns:
                if pattern.lower() in file.replace('-', '').lower():
                    self.jar_file_map[pattern] = file

    def scan_method(self, repositories: list[str]):
        try:
            assert 'javaParser' in self.jar_file_map
            ms.start_java_parser(self.jar_file_map['javaParser'])
            ms.scan_method(self.repository_df[self.repository_df['name'].isin(repositories)], self.repository_directory, self.data_directory, self.cache_directory)
        except Exception as e:
            raise e
        finally:
            ms.stop_java_parser()

    def collect_method_history(self, repositories: list[str], tool_names: list[str]):
        execute_method_history_if_missing(self.repository_df[self.repository_df['name'].isin(repositories)],
                                          self.repository_directory,
                                          self.data_directory,
                                          tool_names, self.jar_file_map)