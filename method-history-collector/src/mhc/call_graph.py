import os
import subprocess
from pandas import DataFrame
import mhc.util as util
import pandas as pd
import  mhc.git_repository as git
import logging

def execute_call_graph_if_missing(repository_df: DataFrame, repository_directory: str, data_directory: str,
                                      cache_directory: str, tool_name: str,
                                      jar_file_map: dict[str, str]) -> None:
    for _, repository in repository_df.iterrows():
        repository_name = repository['name']
        url = repository['url']
        hash = repository['hash']
        repository_path = os.path.join(repository_directory, repository_name)
        git.clone_and_checkout_commit(url, repository_path, hash)
        commits = git.get_all_commit_info(repository_path, hash)
        commit_index = 1
        for commit in commits:
            fan_in_output_file = f"{data_directory}/fan-in/{repository_name}/{repository_name}--fan-in--{commit['hash']}.csv"
            fan_out_output_file = f"{data_directory}/fan-out/{repository_name}/{repository_name}--fan-out--{commit['hash']}.csv"
            if not os.path.exists(fan_in_output_file) or not os.path.exists(fan_out_output_file):
                logging.info(f"Executing call graph for {repository_name} {commit['hash']} {commit_index}/{len(commits)}")
                cmd = [
                    "java", "-jar", jar_file_map[tool_name],
                    "-command", "call-graph",
                    "-repository-path", repository_path,
                    "-repository-url", url,
                    "-start-commit", commit['hash'],
                    "-target-path", ".",
                    "-output-fan-in-file", fan_in_output_file,
                    "-output-fan-out-file", fan_out_output_file
                ]
                try:
                    subprocess.run(cmd, check=True, timeout=1000)
                except subprocess.CalledProcessError as e:
                    print(f"Call graph execution failed: {repository_name} {commit['hash']} {e} ")
            commit_index += 1

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
