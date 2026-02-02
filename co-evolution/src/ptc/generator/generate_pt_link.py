import tarfile
from io import TextIOWrapper
from pathlib import Path

import pandas as pd

from mhc.config import *

repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")

repository_name_map = {row["name"]: row for row in repository_df.to_dict(orient="records")}

def is_corresponding_production_method(test_method_name, test_file, production_method_name, production_file):
    return f"test{production_method_name.lower()}" == test_method_name

for _, repo in repository_df.iterrows():
    repository_name = repo["name"]
    commit_hash = repo["updated_hash"]
    fan_out_zip_file = f"{DATA_DIRECTORY}/fan-out/{repository_name}.tar.gz"
    fan_out_file_suffix = f"{repository_name}/{repository_name}--fan-out--{commit_hash}.csv"
    fan_out_file = f"{DATA_DIRECTORY}/fan-out/{fan_out_file_suffix}"
    if os.path.exists(fan_out_zip_file):
        with tarfile.open(fan_out_zip_file, "r:gz") as tar:
            members = tar.getmembers()
            fan_out_files = {m.name for m in members}
            if fan_out_file_suffix in fan_out_files:
                fan_out_file_content = tar.extractfile(tar.getmember(fan_out_file_suffix))
                raw_fan_out_df = pd.read_csv(TextIOWrapper(fan_out_file_content, encoding="utf-8"), na_filter=False,
                                             keep_default_na=False)
                # Last call
                # raw_fan_out_df = raw_fan_out_df.groupby("caller_url").last().reset_index()
                raw_fan_out_df["linked"] = raw_fan_out_df.apply(lambda row: "yes" if is_corresponding_production_method(row["caller_name"], row["caller_file"], row["callee_name"], row["callee_file"]) else "no", axis=1)
                raw_fan_out_df["name"] = [repository_name] * len(raw_fan_out_df)

                fan_in_count_file = f"{DATA_DIRECTORY}/pt-link/{repository_name}.csv"
                os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
                raw_fan_out_df.to_csv(fan_in_count_file, index=False)
    if repository_name.startswith("d"):
        break
pt_link_dfs = [pd.read_csv(file, keep_default_na=False, na_filter=False) for
                          file in list(Path(f"{DATA_DIRECTORY}/pt-link").rglob("*.csv"))]
pt_link_df = pd.concat(pt_link_dfs)
pt_link_df.to_csv(f"{DATA_DIRECTORY}/pt-link.csv", index=False)