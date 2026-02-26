import os
import pandas as pd
import glob
import uuid
import shutil
import tarfile
import subprocess


class ComplexityAnalyzer:
    def __init__(
        self,
        cache_directory: str,
        repository_directory: str,
        data_directory: str,
        repo_list: list[str],
        jar_file_path: str,
    ):
        self.cache_directory = cache_directory
        self.repository_directory = repository_directory
        self.data_directory = data_directory
        self.repo_list = repo_list
        self.jar_file_path = jar_file_path

        self.project_info_path = os.path.join(
            self.data_directory,
            "repository",
            f"project_info_{str(uuid.uuid4())}.txt",
        )
        self.repository_df_path = os.path.join(
            self.data_directory, "repository", "repository.csv"
        )

        self.history_json_dir = os.path.join(self.repository_directory, "historyJSON")
        os.makedirs(self.history_json_dir, exist_ok=True)

        self.output_dir = os.path.join(
            self.data_directory, "complexity_analyzer_output"
        )
        os.makedirs(self.output_dir, exist_ok=True)

        self.temp_dirs = []

        self.create_project_info()
        self.copy_extract_structure_history_tar()

    def __del__(self):
        self.delete_file(self.project_info_path)
        for temp_dir in self.temp_dirs:
            self.delete_directory(temp_dir)

    def delete_file(self, file_path: str):
        if os.path.exists(file_path):
            os.remove(file_path)

    def delete_directory(self, directory_path: str):
        if os.path.isdir(directory_path):
            shutil.rmtree(directory_path)

    def create_project_info(self):
        repo_stat = []

        repository_df = pd.read_csv(self.repository_df_path)
        repository_df = repository_df[repository_df["repo_name"].isin(self.repo_list)]

        for _, row in repository_df.iterrows():
            repo_stat.append(
                {
                    "name": row["repo_name"],
                    "latest_commit_date": row["updated_at"],
                    "latest_commit_hash": row["updated_hash"],
                    "first_commit_date": row["created_at"],
                    "first_commit_hash": row["created_hash"],
                }
            )

        repo_stat_df = pd.DataFrame(repo_stat)
        repo_stat_df.to_csv(self.project_info_path, index=False, header=False, sep="\t")

    def copy_extract_structure_history_tar(self):
        for repo_name in self.repo_list:
            source_tar_path = os.path.join(
                self.cache_directory, "history", "historyFinder", f"{repo_name}.tar.gz"
            )

            destination_tar_path = os.path.join(
                self.history_json_dir, f"{repo_name}.tar.gz"
            )

            shutil.copy2(source_tar_path, destination_tar_path)

            extracted_dir = os.path.join(
                self.history_json_dir, repo_name + "_raw_history"
            )
            os.makedirs(extracted_dir, exist_ok=True)
            with tarfile.open(destination_tar_path, "r:gz") as tar:
                tar.extractall(path=extracted_dir)
            self.delete_file(destination_tar_path)

            restructured_dir = os.path.join(self.history_json_dir, repo_name)
            os.makedirs(restructured_dir, exist_ok=True)
            self.temp_dirs.append(restructured_dir)

            file_number = 1
            json_files = glob.glob(f"{extracted_dir}/**/*.json", recursive=True)
            for file in json_files:
                shutil.copy2(
                    file, os.path.join(restructured_dir, f"{file_number}.json")
                )
                file_number += 1

            self.delete_directory(extracted_dir)

    def run_complexity_analyzer(self):
        command = [
            "java",
            "-Xmx10240m",
            "-jar",
            self.jar_file_path,
            "-projectsInfo",
            self.project_info_path,
            "-codeShovelHistoryDir",
            self.history_json_dir,
            "-resultDir",
            self.output_dir,
            "-filterOutTestMethods",
            "false",
        ]
        try:
            subprocess.run(command, check=True)
        except subprocess.CalledProcessError as e:
            raise e
        finally:
            self.delete_file(self.project_info_path)
            for temp_dir in self.temp_dirs:
                self.delete_directory(temp_dir)
