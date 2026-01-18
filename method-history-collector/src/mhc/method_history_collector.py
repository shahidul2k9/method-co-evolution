
from method_history_jar_runner import *
from call_graph import execute_call_graph_if_missing
from pathlib import Path
import os
import pandas as pd


class MethodHistoryCollector:
    TOOL_NAMES = [ 'codeShovel', 'historyFinder', 'codeTracker', 'methodParser']
    def __init__(self, cache_directory: str, repository_directory, data_directory, repository_file_name:str,
                 jar_directory: str):
        self.cache_directory = cache_directory
        self.repository_directory = repository_directory
        self.data_directory = data_directory
        self.jar_file_map = {}
        self.repository_df = pd.read_csv(os.path.join(f"{data_directory}/repository", repository_file_name))

        patterns = ['javaParserCore', 'SymbolSolverCore']
        patterns.extend(self.TOOL_NAMES)
        for file in list(map(os.fspath, Path(jar_directory).rglob("*.jar"))):
            for pattern in patterns:
                if pattern.lower() in file.replace('-', '').lower():
                    self.jar_file_map[pattern] = file

    def scan_method(self, repositories: list[str]):
        try:
            assert 'javaParserCore' in self.jar_file_map
            ms.start_java_jar([self.jar_file_map['methodParser']])
            ms.scan_method(self.repository_df[self.repository_df['name'].isin(repositories)], self.repository_directory, self.data_directory, self.cache_directory)
        except Exception as e:
            raise e
        finally:
            ms.stop_java_jar()

    def collect_method_history(self, repositories: list[str], tool_names: list[str]):
        execute_method_history_if_missing(self.repository_df[self.repository_df['name'].isin(repositories)],
                                          self.repository_directory, self.data_directory, self.cache_directory,
                                          tool_names, self.jar_file_map)
    def update_execute_index(self):
        update_method_history_index(self.repository_df, self.data_directory, self.cache_directory, self.TOOL_NAMES)

    def generate_call_graph(self, repositories: list[str], tool_names: list[str]):
        execute_call_graph_if_missing(self.repository_df[self.repository_df['name'].isin(repositories)],
                                          self.repository_directory, self.data_directory, self.cache_directory,
                                          tool_names[-1], self.jar_file_map)
