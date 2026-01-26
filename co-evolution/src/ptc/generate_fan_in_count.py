import os.path
import tarfile
from io import TextIOWrapper

import pandas as pd

import mhc.util as util
from mhc.config import *

repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")

repository_name_map = {row["name"]: row for row in repository_df.to_dict(orient="records")}
for _, repo in repository_df.iterrows():
    repository_name = repo["name"]
    commit_hash = repo["hash"]
    fan_in_zip_file = f"{DATA_DIRECTORY}/fan-in/{repository_name}.tar.gz"
    fan_in_file_suffix = f"{repository_name}/{repository_name}--fan-in--{commit_hash}.csv"
    fan_in_file = f"{DATA_DIRECTORY}/fan-in/{fan_in_file_suffix}"
    if os.path.exists(fan_in_zip_file):
        with tarfile.open(fan_in_zip_file, "r:gz") as tar:
            # Get list of files inside archive
            members = tar.getmembers()
            fan_in_files = {m.name for m in members}

            if fan_in_file_suffix in fan_in_files:
                member = tar.getmember(fan_in_file_suffix)
                fan_in_file_content = tar.extractfile(member)
                raw_fan_in_df = pd.read_csv(TextIOWrapper(fan_in_file_content, encoding="utf-8"), na_filter=False, keep_default_na=False)
                # fan_in_count_df = raw_fan_in_df.groupby("callee_url").size().reset_index()
                # fan_in_count_df = fan_in_count_df.rename({"callee_url": "url"})
                fan_in_count_df = (
                    raw_fan_in_df["callee_url"]
                    .value_counts()
                    .reset_index(name="fan_in")
                    .rename(columns={"callee_url": "url", "index": "url"})
                )
                method_df = pd.read_csv(util.format_method_list_file(DATA_DIRECTORY, repository_name),
                                        keep_default_na=False)
                fan_in_count_file = f"{DATA_DIRECTORY}/fan-in-count/{repository_name}--fan-in.csv"
                os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
                pd.merge(method_df, fan_in_count_df, on="url", how="inner").to_csv(
                    fan_in_count_file, index=False)
                break
