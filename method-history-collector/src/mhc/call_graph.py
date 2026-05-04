import os
import subprocess
import shlex
from pandas import DataFrame
import  mhc.git_repository as git
import logging
import mhc.util as util

def execute_call_graph_if_missing(repository_df: DataFrame, repository_directory: str, data_directory: str,
                                      cache_directory: str, tool_name: str,
                                      jar_file_map: dict[str, str],
                                      replace: bool = False,
                                      java_options: str | None = None) -> None:
    for _, repository in repository_df.iterrows():
        repository_name = repository["project"]
        url = repository['url']
        commit_hash = repository['updated_hash']
        repository_path = os.path.join(repository_directory, repository_name)
        git.clone_and_checkout_commit(url, repository_path, commit_hash)
        fan_in_path = f"{data_directory}/fanin"
        fan_out_path = f"{data_directory}/callgraph"
        os.makedirs(fan_in_path, exist_ok=True)
        os.makedirs(fan_out_path, exist_ok=True)

        fan_in_output_file = os.path.join(fan_in_path, f"{repository_name}.csv")
        fan_out_output_file = os.path.join(fan_out_path, f"{repository_name}.csv")

        if not replace and os.path.exists(fan_in_output_file) and os.path.exists(fan_out_output_file):
            logging.info(f"Skipping call graph for {repository_name}; outputs already exist")
            continue

        logging.info(f"Executing call graph for {repository_name} {commit_hash}")
        method_mapping_file = util.format_method_mapping_file(
            cache_directory,
            data_directory,
            repository_name,
        )
        java_cmd = ["java"]
        if java_options:
            java_cmd.extend(shlex.split(java_options))
        cmd = java_cmd + [
            "-jar", jar_file_map[tool_name],
            "-command", "method-callgraph",
            "-repository-path", repository_path,
            "-repository-url", url,
            "-start-commit", commit_hash,
            "-target-path", ".",
            "-output-fan-in-file", fan_in_output_file,
            "-output-fan-out-file", fan_out_output_file
        ]
        if method_mapping_file:
            cmd.extend(["-method-mapping-file", method_mapping_file])
        else:
            print(
                "Warning: method mapping file was not passed for "
                f"{repository_name}. Expected one of: "
                f"{util.format_method_list_file(data_directory, repository_name)} "
                f"or {os.path.join(cache_directory, 'method', repository_name + '.csv')}"
            )
        try:
            subprocess.run(cmd, check=True, timeout=24*30*60)
        except subprocess.CalledProcessError as e:
            print(f"Call graph execution failed: {repository_name} {commit_hash} {e} ")
