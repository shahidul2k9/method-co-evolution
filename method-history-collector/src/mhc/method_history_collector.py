from mhc.method_history_jar_runner import *
from mhc.call_graph import execute_call_graph_if_missing
from mhc.complexity_analyzer import ComplexityAnalyzer
from pathlib import Path
import os
import pandas as pd


class MethodHistoryCollector:
    TOOL_NAMES = [
        "codeShovel",
        "historyFinder",
        "codeTracker",
        "methodParser",
        "complexityAnalyzer",
    ]

    def __init__(
        self,
        cache_directory: str,
        repository_directory,
        data_directory,
        jar_directory: str,
    ):
        self.cache_directory = cache_directory
        self.repository_directory = repository_directory
        self.data_directory = data_directory
        self.jar_file_map = {}
        self.repository_df = pd.read_csv(
            os.path.join(f"{data_directory}/repository/repository.csv")
        )

        for file in list(map(os.fspath, Path(jar_directory).rglob("*.jar"))):
            for pattern in self.TOOL_NAMES:
                if pattern.lower() in file.replace("-", "").lower():
                    self.jar_file_map[pattern] = file

    def scan_method(self, repositories: list[str]):
        try:
            ms.start_java_jar([self.jar_file_map["methodParser"]])
            ms.scan_method(
                self.repository_df[self.repository_df["project"].isin(repositories)],
                self.repository_directory,
                self.data_directory,
                self.cache_directory,
            )
        except Exception as e:
            raise e
        finally:
            ms.stop_java_jar()

    def collect_method_history(
        self,
        repositories: list[str],
        tool_names: list[str],
        command_options: str | None = None,
        java_options: str | None = None,
        timeout_seconds: int = 30 * 60,
    ):
        execute_method_history_if_missing(
            self.repository_df[self.repository_df["project"].isin(repositories)],
            self.repository_directory,
            self.data_directory,
            self.cache_directory,
            tool_names,
            self.jar_file_map,
            command_options,
            java_options,
            timeout_seconds,
        )

    def update_repository_index(self):
        update_repository_index(self.repository_df, self.cache_directory)

    def generate_call_graph(self, repositories: list[str], tool_names: list[str]):
        execute_call_graph_if_missing(
            self.repository_df[self.repository_df["project"].isin(repositories)],
            self.repository_directory,
            self.data_directory,
            self.cache_directory,
            tool_names[-1],
            self.jar_file_map,
        )

    def run_complexity_analyzer(self, repositories: list[str], tool_name: str):
        ca = ComplexityAnalyzer(
            self.cache_directory,
            self.repository_directory,
            self.data_directory,
            repositories,
            self.jar_file_map[tool_name],
        )
        ca.run_complexity_analyzer()
