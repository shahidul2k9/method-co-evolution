from mhc.method_history_jar_runner import *
from mhc.callgraph import execute_callgraph_per_file
from mhc.class_scanner import scan_class as _scan_class
from mhc.artifact_update import update_artifacts as _update_artifacts
from mhc.complexity_analyzer import ComplexityAnalyzer
from mhc.test_smell import run_test_smell as _run_test_smell
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
        "jnose",
    ]

    def __init__(
        self,
        workspace_directory: str,
        experiment_directory: str,
        repository_directory,
        jar_directory: str,
        history_directory: str | None = None,
    ):
        self.workspace_directory = workspace_directory
        self.experiment_directory = experiment_directory
        self.repository_directory = repository_directory
        self.data_directory = experiment_directory
        self.history_directory = history_directory or str(Path(experiment_directory) / "method-history-gz")
        self.jar_file_map = {}
        self.repository_df = pd.read_csv(Path(experiment_directory) / "project.csv")

        for file in sorted(
            map(os.fspath, Path(jar_directory).rglob("*.jar")),
            key=_jar_preference_key,
        ):
            for pattern in self.TOOL_NAMES:
                if pattern.lower() in file.replace("-", "").lower():
                    self.jar_file_map[pattern] = file
            normalized_file = file.replace("-", "").lower()
            if "jnose" in normalized_file:
                self.jar_file_map["jnose"] = file

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
        artifact_config_path: str | None = None,
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
                self.experiment_directory,
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
                artifact_config_path,
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
        artifact_config_path: str | None = None,
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
                self.experiment_directory,
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
                artifact_config_path,
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
        merge_threshold: int = DEFAULT_MERGE_THRESHOLD,
        merge_interval_seconds: int | None = None,
        max_cache_size: int = 256,
        artifact_config_path: str | None = None,
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
            merge_threshold,
            merge_interval_seconds,
            max_cache_size,
            artifact_config_path,
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
        merge_threshold: int = DEFAULT_MERGE_THRESHOLD,
        merge_interval_seconds: int | None = None,
        max_cache_size: int = 256,
        artifact_config_path: str | None = None,
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
                self.experiment_directory,
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
                max_cache_size,
                artifact_config_path,
            )
        except Exception as e:
            raise e
        finally:
            if not merge_only:
                ms.stop_java_jar()

    def run_complexity_analyzer(self, repositories: list[str], tool_name: str):
        ca = ComplexityAnalyzer(
            self.experiment_directory,
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
            self.experiment_directory,
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

    def update_artifacts(
        self,
        repositories: list[str],
        java_options: str | None,
        artifact_config_path: str | None,
        targets: list[str],
        dry_run: bool = False,
        backup: bool = False,
        replace: bool = False,
    ):
        try:
            ms.start_java_jar(
                [self.jar_file_map["methodParser"]],
                util.java_options_with_logback_config(java_options, self.workspace_directory),
            )
            _update_artifacts(
                self.repository_df[self.repository_df["project"].isin(repositories)],
                self.repository_directory,
                self.data_directory,
                artifact_config_path,
                targets,
                dry_run,
                backup,
                replace,
            )
        finally:
            ms.stop_java_jar()

    def run_test_smell(
        self,
        repositories: list[str],
        tool_name: str,
        stage: str = "all",
        callgraph_dir: str = "callgraph",
    ):
        _run_test_smell(
            self.repository_df,
            self.repository_directory,
            self.data_directory,
            self.jar_file_map,
            repositories,
            tool_name,
            stage,
            callgraph_dir,
        )


def _jar_preference_key(file: str) -> tuple[int, str]:
    normalized = Path(file).name.lower()
    is_fat_or_executable = (
        "jnose-adapter" in normalized
        or "jar-with-dependencies" in normalized
        or "all" in normalized
        or "standalone" in normalized
    )
    return (1 if is_fat_or_executable else 0, normalized)
