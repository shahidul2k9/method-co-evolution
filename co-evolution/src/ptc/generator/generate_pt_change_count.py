import tarfile
from io import TextIOWrapper
from pathlib import Path

import pandas as pd

from mhc.config import *

repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")

repository_name_map = {row["name"]: row for row in repository_df.to_dict(orient="records")}
for tooName in os.listdir(f"{CACHE_DIRECTORY}/history"):
    history_repository_dfs = [pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False) for
                              repository_history_file in list(Path(f"{DATA_DIRECTORY}/history/{tooName}").rglob("*.csv"))]
    history_df = pd.concat(history_repository_dfs)

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
                    raw_fan_out_df = raw_fan_out_df.groupby("caller_url").last().reset_index()
                    change_df = (
                        raw_fan_out_df[["caller_url", "callee_url"]]
                        .merge(history_df.add_prefix("caller_"), on="caller_url", how="inner")
                        .merge(history_df.add_prefix("callee_"), on="callee_url", how="inner")
                    )
                    fan_in_count_file = f"{DATA_DIRECTORY}/pt-change-count/{tooName}/{repository_name}.csv"
                    os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
                    change_df.to_csv(fan_in_count_file, index=False)
