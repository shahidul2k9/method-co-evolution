import os
import subprocess
from pandas import DataFrame
import  mhc.git_repository as git
import logging
import mhc.util as util
from pathlib import Path
from mhc.zip import load_zip_index, merge_folder_into_tar_gz

def execute_call_graph_if_missing(repository_df: DataFrame, repository_directory: str, data_directory: str,
                                      cache_directory: str, tool_name: str,
                                      jar_file_map: dict[str, str]) -> None:
    for _, repository in repository_df.iterrows():
        repository_name = repository["project"]
        url = repository['url']
        hash = repository['updated_hash']
        repository_path = os.path.join(repository_directory, repository_name)
        git.clone_and_checkout_commit(url, repository_path, hash)
        commits = git.get_all_commit_info(repository_path, hash)
        assert commits[0]['hash'] == hash, "The first commit should be the commit hash in the repository file"
        commit_index = 1
        # fan_in_path = f"{data_directory}/fan-in-gz/{repository_name}"
        # fan_out_path = f"{data_directory}/fan-out-gz/{repository_name}"
        fan_in_path = f"{data_directory}/fan-in"
        fan_out_path = f"{data_directory}/fan-out"

        fan_in_tar_gz = f"{fan_in_path}.tar.gz"
        repository_name_prefix = f"{repository_name}/"
        fan_in_zip_index = util.remove_prefix_if_exists(load_zip_index(fan_in_tar_gz),
                                                 repository_name_prefix) if os.path.exists(
            fan_in_tar_gz) else set()
        fan_in_repo_path = Path(fan_in_path)
        fan_in_unzip_index = set(str(p.relative_to(fan_in_repo_path)) for p in fan_in_repo_path.rglob("*.csv"))
        for commit in commits:
            # fan_in_output_file_suffix = f"{repository_name}--fan-in--{commit['hash']}.csv"
            fan_in_output_file_suffix = f"{repository_name}.csv"
            fan_in_output_file = os.path.join(fan_in_path, fan_in_output_file_suffix)
            # fan_out_output_file_suffix = f"{repository_name}--fan-out--{commit['hash']}.csv"
            fan_out_output_file_suffix = f"{repository_name}.csv"
            fan_out_output_file = os.path.join(fan_out_path, fan_out_output_file_suffix)

            if fan_in_output_file_suffix not in fan_in_zip_index and fan_in_output_file_suffix not in fan_in_unzip_index:
                logging.info(f"Executing call graph for {repository_name} {commit['hash']} {commit_index}/{len(commits)}")
                method_mapping_file = util.format_method_mapping_file(
                    cache_directory,
                    data_directory,
                    repository_name,
                )
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
                    fan_in_unzip_index.add(fan_in_output_file_suffix)
                except subprocess.CalledProcessError as e:
                    print(f"Call graph execution failed: {repository_name} {commit['hash']} {e} ")
        #         if len(fan_in_unzip_index) >= 1000:
        #             merge_folder_into_tar_gz(fan_in_path)
        #             merge_folder_into_tar_gz(fan_out_path)
        #             fan_in_zip_index =  util.remove_prefix_if_exists(load_zip_index(fan_in_tar_gz), repository_name_prefix)
        #             fan_in_unzip_index = set(str(p.relative_to(fan_in_repo_path)) for p in fan_in_repo_path.rglob("*.csv"))
        #     commit_index += 1
        # merge_folder_into_tar_gz(fan_in_path)
        # merge_folder_into_tar_gz(fan_out_path)
            break
