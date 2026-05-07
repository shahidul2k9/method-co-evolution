from mhc.method_history_jar_runner import *
from mhc.callgraph import execute_callgraph_per_file
from mhc.class_scanner import scan_class as _scan_class
from mhc.complexity_analyzer import ComplexityAnalyzer
from pathlib import Path
import os
import pandas as pd
import mhc.util as util
from mhc.method_history_jar_runner import DEFAULT_MERGE_THRESHOLD


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
        workspace_directory: str,
        repository_directory,
        data_directory,
        jar_directory: str,
        history_directory: str | None = None,
    ):
        self.workspace_directory = workspace_directory
        self.repository_directory = repository_directory
        self.data_directory = data_directory
        self.history_directory = history_directory or str(Path(workspace_directory) / "history")
        self.jar_file_map = {}
        self.repository_df = pd.read_csv(
            os.path.join(f"{data_directory}/repository/repository.csv")
        )

        for file in list(map(os.fspath, Path(jar_directory).rglob("*.jar"))):
            for pattern in self.TOOL_NAMES:
                if pattern.lower() in file.replace("-", "").lower():
                    self.jar_file_map[pattern] = file

    def scan_class(
        self,
        repositories: list[str],
        java_options: str | None = None,
        replace: bool = False,
        shards: int = 1,
        shard: int = 1,
        merge_only: bool = False,
        merge_only_delete_empty: bool = False,
        merge_only_delete_tmp: bool = False,
        merge_only_delete_lock: bool = False,
        retry_errors: bool = True,
        merge_threshold: int = DEFAULT_MERGE_THRESHOLD,
        merge_interval_seconds: int | None = None,
    ):
        try:
            if not merge_only:
                ms.start_java_jar(
                    [self.jar_file_map["methodParser"]],
                    util.java_options_with_logback_config(java_options, self.workspace_directory),
                )
            _scan_class(
                self.repository_df[self.repository_df["project"].isin(repositories)],
                self.repository_directory,
                self.data_directory,
                self.workspace_directory,
                replace,
                shards,
                shard,
                merge_only,
                merge_only_delete_empty,
                merge_only_delete_tmp,
                merge_only_delete_lock,
                retry_errors,
                merge_threshold,
                merge_interval_seconds,
            )
        except Exception as e:
            raise e
        finally:
            if not merge_only:
                ms.stop_java_jar()

    def scan_method(
        self,
        repositories: list[str],
        java_options: str | None = None,
        replace: bool = False,
        shards: int = 1,
        shard: int = 1,
        merge_only: bool = False,
        merge_only_delete_empty: bool = False,
        merge_only_delete_tmp: bool = False,
        merge_only_delete_lock: bool = False,
        retry_errors: bool = True,
        merge_threshold: int = DEFAULT_MERGE_THRESHOLD,
        merge_interval_seconds: int | None = None,
    ):
        try:
            if not merge_only:
                ms.start_java_jar(
                    [self.jar_file_map["methodParser"]],
                    util.java_options_with_logback_config(java_options, self.workspace_directory),
                )
            ms.scan_method(
                self.repository_df[self.repository_df["project"].isin(repositories)],
                self.repository_directory,
                self.data_directory,
                self.workspace_directory,
                replace,
                shards,
                shard,
                merge_only,
                merge_only_delete_empty,
                merge_only_delete_tmp,
                merge_only_delete_lock,
                retry_errors,
                merge_threshold,
                merge_interval_seconds,
            )
        except Exception as e:
            raise e
        finally:
            if not merge_only:
                ms.stop_java_jar()

    def collect_method_history(
        self,
        repositories: list[str],
        tool_names: list[str],
        command_options: str | None = None,
        java_options: str | None = None,
        timeout_seconds: int = 30 * 60,
        shards: int = 1,
        shard: int = 1,
        merge_threshold: int = DEFAULT_MERGE_THRESHOLD,
        merge_only: bool = False,
        merge_only_delete_empty: bool = False,
        merge_only_delete_tmp: bool = False,
        merge_only_delete_lock: bool = False,
    ):
        execute_method_history_if_missing(
            self.repository_df[self.repository_df["project"].isin(repositories)],
            self.repository_directory,
            self.data_directory,
            self.history_directory,
            tool_names,
            self.jar_file_map,
            command_options,
            java_options,
            timeout_seconds,
            shards,
            shard,
            merge_threshold,
            merge_only,
            merge_only_delete_empty,
            merge_only_delete_tmp,
            merge_only_delete_lock,
        )

    def update_repository_index(self):
        update_repository_index(
            self.repository_df,
            self.history_directory,
            self.data_directory,
        )

    def generate_callgraph(
        self,
        repositories: list[str],
        tool_names: list[str],
        replace: bool = False,
        java_options: str | None = None,
        shards: int = 1,
        shard: int = 1,
        merge_only: bool = False,
        merge_only_delete_empty: bool = False,
        merge_only_delete_tmp: bool = False,
        merge_only_delete_lock: bool = False,
        retry_errors: bool = True,
    ):
        self.generate_callgraph_per_file(
            repositories,
            java_options,
            replace,
            shards,
            shard,
            merge_only,
            merge_only_delete_empty,
            merge_only_delete_tmp,
            merge_only_delete_lock,
            retry_errors,
        )

    def generate_callgraph_per_file(
        self,
        repositories: list[str],
        java_options: str | None = None,
        replace: bool = False,
        shards: int = 1,
        shard: int = 1,
        merge_only: bool = False,
        merge_only_delete_empty: bool = False,
        merge_only_delete_tmp: bool = False,
        merge_only_delete_lock: bool = False,
        retry_errors: bool = True,
    ):
        try:
            if not merge_only:
                ms.start_java_jar(
                    [self.jar_file_map["methodParser"]],
                    util.java_options_with_logback_config(java_options, self.workspace_directory),
                )
            execute_callgraph_per_file(
                self.repository_df[self.repository_df["project"].isin(repositories)],
                self.repository_directory,
                self.data_directory,
                self.workspace_directory,
                replace,
                shards,
                shard,
                merge_only,
                merge_only_delete_empty,
                merge_only_delete_tmp,
                merge_only_delete_lock,
                retry_errors,
            )
        except Exception as e:
            raise e
        finally:
            if not merge_only:
                ms.stop_java_jar()

    def run_complexity_analyzer(self, repositories: list[str], tool_name: str):
        ca = ComplexityAnalyzer(
            self.workspace_directory,
            self.history_directory,
            self.repository_directory,
            self.data_directory,
            repositories,
            self.jar_file_map[tool_name],
        )
        ca.run_complexity_analyzer()

    def generate_method_code(
        self,
        repositories: list[str],
        shards: int = 1,
        shard: int = 1,
        replace: bool = False,
        merge_only: bool = False,
        merge_only_delete_empty: bool = False,
        merge_only_delete_tmp: bool = False,
        merge_only_delete_lock: bool = False,
        retry_errors: bool = True,
        merge_threshold: int = DEFAULT_MERGE_THRESHOLD,
        merge_interval_seconds: int | None = None,
    ):
        ms.generate_method_code(
            self.repository_df[self.repository_df["project"].isin(repositories)],
            self.repository_directory,
            self.data_directory,
            self.workspace_directory,
            replace,
            shards,
            shard,
            merge_only,
            merge_only_delete_empty,
            merge_only_delete_tmp,
            merge_only_delete_lock,
            retry_errors,
            merge_threshold,
            merge_interval_seconds,
        )
