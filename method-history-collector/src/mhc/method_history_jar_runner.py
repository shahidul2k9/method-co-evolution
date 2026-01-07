import os
import subprocess
from pandas import DataFrame
import util as util
import pandas as pd
import  method_scanner as ms


def execute_method_history_if_missing(repository_df: DataFrame, repository_directory: str, data_directory: str,
                                      cache_directory: str, tool_names: list[str],
                                      jar_file_map: dict[str, str]) -> None:
    for tool_name in tool_names:
        for _, repository in repository_df.iterrows():
            repository_name = repository['name']
            url = repository['url']
            hash = repository['hash']
            method_df = pd.read_csv(util.format_method_list_file(data_directory, repository_name))
            ms.clone_and_checkout_commit(url,os.path.join(repository_directory, repository_name),hash)
            for _, method in method_df.iterrows():
                method_name = method['method_name']
                start_line = method['start_line']
                file = method['file']
                method_history_file = util.format_method_history_file(cache_directory, tool_name, repository_name, file,
                                                                      method_name, start_line)
                if not os.path.exists(method_history_file):
                    execute_cmd_method_history_jar(tool_name, jar_file_map[tool_name],
                                                   os.path.join(repository_directory, repository_name),
                                                   url, hash, file, method_name, start_line, method_history_file)


def update_method_history_index(repository_df: DataFrame, data_directory: str, cache_directory: str,
                           tool_names: list[str]) -> None:
    records = []
    for _, repository in repository_df.iterrows():
        repository_name = repository['name']
        method_list_file = util.format_method_list_file(data_directory, repository_name)
        if os.path.exists(method_list_file):
            method_df = pd.read_csv(method_list_file)
            record = {'name': repository_name, 'methods': len(method_df)}

            for tool_name in tool_names:
                method_count = 0
                for _, method in method_df.iterrows():
                    method_name = method['method_name']
                    start_line = method['start_line']
                    file = method['file']
                    method_history_file = util.format_method_history_file(cache_directory, tool_name, repository_name, file,
                                                                          method_name, start_line)
                    if os.path.exists(method_history_file):
                        method_count += 1
                record[tool_name] = method_count
            records.append(record)
    pd.DataFrame(records).to_csv(util.format_repository_history_index_file(cache_directory), index=False)


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
            subprocess.run(cmd, check=True, timeout=1000)
        except subprocess.CalledProcessError as e:
            print(f"Execution failed: {tool_name} {file} {e} ")
