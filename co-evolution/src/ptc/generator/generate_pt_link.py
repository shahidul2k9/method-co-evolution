import tarfile
from io import TextIOWrapper
from pathlib import Path

import Levenshtein
import pandas as pd

import mhc.util as util
from mhc.config import *

repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")

repository_name_map = {row["repo_name"]: row for row in repository_df.to_dict(orient="records")}


def establish_link(row):
    test_method_name = row["caller_name"]
    production_method_name = row["callee_name"]
    lcs = util.lcs(production_method_name, test_method_name)

    return pd.Series({
        "link_nc": int(production_method_name == test_method_name),
        "link_ncc": int(production_method_name in test_method_name),
        "link_lcs_b": lcs / max(len(production_method_name), len(test_method_name)),
        "link_lcs_u": lcs / len(production_method_name),
        "link_leven": 1 - Levenshtein.distance(production_method_name, test_method_name) / max(
            len(production_method_name),
            len(test_method_name))
    })


# repository_df = repository_df[repository_df["repo_name"].str.startswith("Apktool")]
for _, repo in repository_df.iterrows():
    repository_name = repo["repo_name"]
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
                fan_out_df = pd.read_csv(TextIOWrapper(fan_out_file_content, encoding="utf-8"), na_filter=False,
                                         keep_default_na=False)
                fan_out_df[["link_nc", "link_ncc", "link_lcs_b", "link_lcs_u", "link_leven"]] = fan_out_df.apply(
                    establish_link,
                    axis=1
                ).round(2)
                fan_out_df["link_lc"] = (
                        fan_out_df.groupby("caller_url").cumcount()
                        == fan_out_df.groupby("caller_url")["caller_url"].transform("size") - 1
                ).astype(int)
                fan_out_df.insert(0, "repo_name", repository_name)
                fan_out_df["repo_name"] = [repository_name] * len(fan_out_df)

                fan_in_count_file = f"{DATA_DIRECTORY}/pt-link/{repository_name}.csv"
                os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
                fan_out_df.to_csv(fan_in_count_file, index=False)
pt_link_dfs = [pd.read_csv(file, keep_default_na=False, na_filter=False) for
               file in list(Path(f"{DATA_DIRECTORY}/pt-link").rglob("*.csv"))]
pt_link_df = pd.concat(pt_link_dfs)
pt_link_df.to_csv(f"{DATA_DIRECTORY}/pt-link.csv", index=False)
