import os.path
import tarfile
from io import TextIOWrapper

import pandas as pd

import mhc.util as util
from mhc.config import *
def read_fan_count_if_exists(fan_zip_file: str, fan_file_suffix: str, url_column: str, fan_column:str):
    if os.path.exists(fan_zip_file):
        with tarfile.open(fan_zip_file, "r:gz") as tar:
            members = tar.getmembers()
            fan_files = {m.name for m in members}

            if fan_file_suffix in fan_files:
                member = tar.getmember(fan_file_suffix)
                fan_file_content = tar.extractfile(member)
                raw_fan_df = pd.read_csv(TextIOWrapper(fan_file_content, encoding="utf-8"), na_filter=False,
                                             keep_default_na=False)
                fan_count_df = (
                    raw_fan_df[url_column]
                    .value_counts()
                    .reset_index(name=fan_column)
                    .rename(columns={url_column: "url", "index": "url"})
                )
                return fan_count_df
    return None

repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")

repository_name_map = {row["name"]: row for row in repository_df.to_dict(orient="records")}
for _, repo in repository_df.iterrows():
    repository_name = repo["name"]
    commit_hash = repo["hash"]
    fan_dfs = []
    for url_column, fan in [("caller_url", "fan-out"), ("callee_url", "fan-in")]:
        fan_zip_file = f"{DATA_DIRECTORY}/{fan}/{repository_name}.tar.gz"
        fan_file_suffix = f"{repository_name}/{repository_name}--{fan}--{commit_hash}.csv"
        fan_file = f"{DATA_DIRECTORY}/{fan}/{fan_file_suffix}"
        fan_dfs.append(read_fan_count_if_exists(fan_zip_file, fan_file_suffix, url_column, fan.replace("-", "_")))
    fan_out_df, fan_in_df = fan_dfs
    if fan_out_df is not None and fan_in_df is not None:
        in_out_df = pd.merge(fan_out_df, fan_in_df, on="url", how="outer")
        in_out_df[["fan_out", "fan_in"]] = in_out_df[["fan_out", "fan_in"]].fillna(0).astype(int)
        method_df = pd.read_csv(util.format_method_list_file(DATA_DIRECTORY, repository_name), keep_default_na=False, na_filter=False)
        fan_in_count_file = f"{DATA_DIRECTORY}/fan-in-out-count/{repository_name}--fan-in-out-count.csv"
        os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
        pd.merge(method_df, in_out_df, on="url", how="inner").to_csv(
            fan_in_count_file, index=False)


