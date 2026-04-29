import os
import shlex
import subprocess
import tempfile
from pathlib import Path

import pandas as pd
from pandas import DataFrame

import mhc.method_scanner as ms
import mhc.util as util
from mhc.zip import (
    load_zip_index,
    merge_folder_into_tar_gz,
    remove_empty_directory_tree,
    remove_file_if_exists,
    remove_files_with_suffix,
)

DEFAULT_MERGE_THRESHOLD = 10_000


def execute_method_history_if_missing(repository_df: DataFrame, repository_directory: str, data_directory: str,
                                      cache_directory: str, tool_names: list[str],
                                      jar_file_map: dict[str, str],
                                      command_options: str | None = None,
                                      java_options: str | None = None,
                                      timeout_seconds: int = 30 * 60,
                                      shards: int = 1,
                                      shard: int = 1,
                                      merge_threshold: int = DEFAULT_MERGE_THRESHOLD,
                                      merge_only: bool = False,
                                      merge_only_delete_empty: bool = False,
                                      merge_only_delete_tmp: bool = False,
                                      merge_only_delete_lock: bool = False) -> None:
    for tool_name in tool_names:
        for _, repository in repository_df.iterrows():
            repository_name = repository["project"]
            url = repository['url']
            hash = repository['updated_hash']
            method_history_path = util.format_method_history_path(cache_directory, tool_name, repository_name)

            if merge_only:
                merge_folder_into_tar_gz(method_history_path)
                if merge_only_delete_tmp:
                    remove_files_with_suffix(method_history_path, ".tmp")
                if merge_only_delete_lock:
                    remove_file_if_exists(f"{method_history_path}.tar.gz.lock")
                if merge_only_delete_empty:
                    remove_empty_directory_tree(method_history_path)
            else:
                method_history_tar_gz = f"{method_history_path}.tar.gz"
                repository_name_prefix = f"{repository_name}/"
                zip_index = util.remove_prefix_if_exists(load_zip_index(method_history_tar_gz),
                                                         repository_name_prefix) if os.path.exists(
                    method_history_tar_gz) else set()

                method_df = pd.read_csv(util.format_method_list_file(data_directory, repository_name),
                                        keep_default_na=False, na_filter=False)
                method_df = method_df[method_df["expression"] == "method"]
                ms.clone_and_checkout_commit(url, os.path.join(repository_directory, repository_name), hash)
                repo_path = Path(method_history_path)
                unzip_index = set(str(p.relative_to(repo_path)) for p in repo_path.rglob("*.json"))

                for _, method in method_df.iterrows():
                    method_name = method['name']
                    start_line = method['start_line']
                    file = method['file']
                    if pd.notna(method_name) and pd.notna(start_line):
                        method_history_file_suffix = util.format_method_history_file_suffix(file, method_name, start_line)
                        if util.stable_shard_for_key(method_history_file_suffix, shards) != shard:
                            continue
                        method_history_file = os.path.join(method_history_path, method_history_file_suffix)
                        if method_history_file_suffix not in zip_index and method_history_file_suffix not in unzip_index:
                            execute_cmd_method_history_jar(tool_name, jar_file_map[tool_name],
                                                           os.path.join(repository_directory, repository_name),
                                                           url, hash, file, method_name, start_line, method_history_file,
                                                           command_options, java_options, timeout_seconds)
                            unzip_index.add(method_history_file_suffix)
                    if merge_threshold > 0 and len(unzip_index) >= merge_threshold:
                        merge_folder_into_tar_gz(method_history_path)
                        zip_index = util.remove_prefix_if_exists(load_zip_index(method_history_tar_gz),
                                                                 repository_name_prefix)
                        unzip_index = set(str(p.relative_to(repo_path)) for p in repo_path.rglob("*.json"))
                if merge_threshold >= 0:
                    merge_folder_into_tar_gz(method_history_path)


def update_repository_index(repository_df: DataFrame, cache_dir: str, data_dir: str) -> None:
    repository_statistics = {}
    for method_file in Path(data_dir, "method").rglob("*.csv"):
        repository_name = method_file.stem.split("--")[0]
        if repository_name not in repository_statistics:
            repository_statistics[repository_name] = {}
        repository_statistics[repository_name]["methods"] = len(pd.read_csv(method_file))

    for tooName in os.listdir(f"{cache_dir}/history"):
        for zip_file in Path(f"{cache_dir}/history/{tooName}").rglob("*.tar.gz"):
            repository_name = zip_file.name[:-len(".tar.gz")]
            if repository_name not in repository_statistics:
                repository_statistics[repository_name] = {}
            zip_index = load_zip_index(zip_file)
            zip_index = set(filter(lambda file: file.endswith(".json"), zip_index))
            repository_statistics[repository_name][f"history_{tooName}"] = len(zip_index)
    for fan in ["fan-in", "fan-out"]:
        for zip_file in Path(data_dir, fan).rglob("*.tar.gz"):
            repository_name = zip_file.name[:-len(".tar.gz")]
            if repository_name not in repository_statistics:
                repository_statistics[repository_name] = {}
            zip_index = load_zip_index(zip_file)
            zip_index = set(filter(lambda file: file.endswith(".csv"), zip_index))
            repository_statistics[repository_name][f"{fan}"] = len(zip_index)

    repository_index = []
    for project, stats in repository_statistics.items():
        stats["project"] = project
        repository_index.append(stats)

    index_df = pd.merge(repository_df, pd.DataFrame(repository_index), on="project", how="left")
    num_cols = index_df.select_dtypes(include="number").columns
    index_df[num_cols] = index_df[num_cols].astype("Int64")

    output_file = Path(data_dir) / "aggregate" / "repository-history-index.csv"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    index_df.to_csv(output_file, index=False)


def execute_cmd_method_history_jar(tool_name: str,
                                   jar_file: str,
                                   git_project_directory: str,
                                   repository_url: str,
                                   start_commit: str,
                                   file: str,
                                   method_name: str,
                                   start_line: int,
                                   output_file: str,
                                   command_options: str | None = None,
                                   java_options: str | None = None,
                                   timeout_seconds: int = 30 * 60):
    java_cmd = ["java"]
    if java_options:
        java_cmd.extend(shlex.split(java_options))

    if tool_name == 'codeShovel':
        cmd = java_cmd + [
            "-jar", jar_file,
            "-repopath", git_project_directory,
            "-startcommit", start_commit,
            "-filepath", file,
            "-methodname", method_name,
            "-startline", str(start_line),
            "-outfile", output_file
        ]
    if tool_name == 'historyFinder':
        cmd = java_cmd + [
            "-jar", jar_file,
            "-clone-directory", os.path.dirname(git_project_directory),
            "-repository-url", repository_url,
            "-start-commit", start_commit,
            "-file", file,
            "-method-name", method_name,
            "-start-line", str(start_line),
            "-output-file", output_file
        ]
    if tool_name == 'codeTracker':
        cmd = java_cmd + [
            "-jar", jar_file,
            "-clone-directory", os.path.dirname(git_project_directory),
            "-repository-url", repository_url,
            "-start-commit", start_commit,
            "-file", file,
            "-method-name", method_name,
            "-start-line", str(start_line),
            "-output-file", output_file
        ]

    if command_options:
        cmd.extend(shlex.split(command_options))

    if not os.path.exists(output_file):
        print(f"Executing .. {file}")
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp_output_file = tempfile.mkstemp(
            prefix=f"{output_path.stem}.",
            suffix=".tmp",
            dir=output_path.parent,
        )
        os.close(fd)
        try:
            output_option_index = cmd.index("-outfile") + 1 if "-outfile" in cmd else cmd.index("-output-file") + 1
            cmd[output_option_index] = tmp_output_file
            subprocess.run(cmd, check=True, timeout=timeout_seconds)
            os.replace(tmp_output_file, output_file)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"Execution failed: {tool_name} {file} {e}")
            if os.path.exists(tmp_output_file):
                os.remove(tmp_output_file)
