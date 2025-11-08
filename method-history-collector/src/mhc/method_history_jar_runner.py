import os
import subprocess
from pandas import DataFrame
import mhc.util as util
import pandas as pd


def execute_method_history_if_missing(repository_df: DataFrame,
                                      repository_directory: str,
                                      data_directory: str,
                                      tool_names: list[str],
                                      jar_file_map: dict[str, str]) -> None:
    for tool_name in tool_names:
        for _, repository in repository_df.iterrows():
            repository_name = repository['name']
            url = repository['url']
            hash = repository['hash']
            method_df = pd.read_csv(util.format_method_list_file(data_directory, repository_name))
            for _, method in method_df.iterrows():
                method_name = method['method_name']
                start_line = method['start_line']
                file = method['file']
                method_history_file = util.format_method_history_file(data_directory, tool_name, file,
                                                                      method_name, start_line)
                if not os.path.exists(method_history_file):
                    execute_cmd_method_history_jar(tool_name, jar_file_map[tool_name],
                                                   os.path.join(repository_directory, repository_name),
                                                   url, hash, file, method_name, start_line, method_history_file)


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
