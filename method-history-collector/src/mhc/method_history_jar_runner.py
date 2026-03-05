import os
import subprocess
from pathlib import Path

import pandas as pd
from pandas import DataFrame

import mhc.method_scanner as ms
import mhc.util as util
from mhc.zip import load_zip_index, merge_folder_into_tar_gz


def execute_method_history_if_missing(repository_df: DataFrame, repository_directory: str, data_directory: str,
                                      cache_directory: str, tool_names: list[str],
                                      jar_file_map: dict[str, str]) -> None:
    for tool_name in tool_names:
        for _, repository in repository_df.iterrows():
            repository_name = repository["project"]
            url = repository['url']
            hash = repository['updated_hash']
            method_history_path = util.format_method_history_path(cache_directory, tool_name, repository_name)

            method_history_tar_gz = f"{method_history_path}.tar.gz"
            repository_name_prefix = f"{repository_name}/"
            zip_index = util.remove_prefix_if_exists(load_zip_index(method_history_tar_gz),
                                                     repository_name_prefix) if os.path.exists(
                method_history_tar_gz) else set()

            method_df = pd.read_csv(util.format_method_list_file(data_directory, repository_name),
                                    keep_default_na=False, na_filter=False)
            method_df = method_df[method_df["expression"] == "method"]
            method_df = method_df.sample(frac=1, random_state=42).reset_index(drop=True)
            ms.clone_and_checkout_commit(url, os.path.join(repository_directory, repository_name), hash)
            repo_path = Path(method_history_path)
            unzip_index = set(str(p.relative_to(repo_path)) for p in repo_path.rglob("*.json"))

            for _, method in method_df.iterrows():
                method_name = method['name']
                start_line = method['start_line']
                file = method['file']
                if pd.notna(method_name) and pd.notna(start_line):
                    method_history_file_suffix = util.format_method_history_file_suffix(file, method_name, start_line)
                    method_history_file = os.path.join(method_history_path, method_history_file_suffix)
                    if method_history_file_suffix not in zip_index and method_history_file_suffix not in unzip_index:
                        execute_cmd_method_history_jar(tool_name, jar_file_map[tool_name],
                                                       os.path.join(repository_directory, repository_name),
                                                       url, hash, file, method_name, start_line, method_history_file)
                        unzip_index.add(method_history_file_suffix)
                if len(unzip_index) >= 5000:
                    merge_folder_into_tar_gz(method_history_path)
                    zip_index = util.remove_prefix_if_exists(load_zip_index(method_history_tar_gz),
                                                             repository_name_prefix)
                    unzip_index = set(str(p.relative_to(repo_path)) for p in repo_path.rglob("*.json"))
            merge_folder_into_tar_gz(method_history_path)


def update_repository_index(repository_df: DataFrame, cache_dir: str) -> None:
    repository_statistics = {}
    for method_file in Path(f"{cache_dir}/data/method").rglob("*.csv"):
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
        for zip_file in Path(f"{cache_dir}/data/{fan}").rglob("*.tar.gz"):
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

    index_df.to_csv(
        util.format_repository_history_index_file(cache_dir), index=False)


def execute_cmd_method_history_jar(tool_name: str,
                                   jar_file: str,
                                   git_project_directory: str,
                                   repository_url: str,
                                   start_commit: str,
                                   file: str,
                                   method_name: str,
                                   start_line: int,
                                   output_file: str):
    if tool_name == 'codeShovel':
        cmd = [
            "java", "-jar", jar_file,
            "-repopath", git_project_directory,
            "-startcommit", start_commit,
            "-filepath", file,
            "-methodname", method_name,
            "-startline", str(start_line),
            "-outfile", output_file
        ]
    if tool_name == 'historyFinder':
        cmd = [
            "java", "-jar", jar_file,
            "-clone-directory", os.path.dirname(git_project_directory),
            "-repository-url", repository_url,
            "-start-commit", start_commit,
            "-file", file,
            "-method-name", method_name,
            "-start-line", str(start_line),
            "-output-file", output_file
        ]
    if tool_name == 'codeTracker':
        cmd = [
            "java", "-jar", jar_file,
            "-clone-directory", os.path.dirname(git_project_directory),
            "-repository-url", repository_url,
            "-start-commit", start_commit,
            "-file", file,
            "-method-name", method_name,
            "-start-line", str(start_line),
            "-output-file", output_file
        ]

    if not os.path.exists(output_file):
        print(f"Executing .. {file}")
        try:
            subprocess.run(cmd, check=True, timeout=30 * 60)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
            print(f"Execution failed: {tool_name} {file} {e}")
