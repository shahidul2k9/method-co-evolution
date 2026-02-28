import Levenshtein
import pandas as pd

import mhc.util as util
from mhc.config import *

repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")

repository_name_map = {row["repo_name"]: row for row in repository_df.to_dict(orient="records")}


def establish_confidence(row):
    test_method_name = row["from_name"]
    production_method_name = row["to_name"]
    lcs = util.lcs(production_method_name, test_method_name)

    return pd.Series({
        "confidence_nc": int(production_method_name == test_method_name),
        "confidence_ncc": int(production_method_name in test_method_name),
        "confidence_lcs_b": lcs / max(len(production_method_name), len(test_method_name)),
        "confidence_lcs_u": lcs / len(production_method_name),
        "confidence_leven": 1 - Levenshtein.distance(production_method_name, test_method_name) / max(
            len(production_method_name),
            len(test_method_name))
    })


# repository_df = repository_df[repository_df["repo_name"].str.startswith("Apktool")]
for _, repo in repository_df.iterrows():
    repository_name = repo["repo_name"]
    commit_hash = repo["updated_hash"]
    fan_out_file_suffix = f"{repository_name}.csv"
    # fan_out_file_suffix = f"{repository_name}--fan-out--{commit_hash}.csv"
    fan_out_file = f"{DATA_DIRECTORY}/fan-out/{fan_out_file_suffix}"
    if os.path.exists(fan_out_file):
        fan_out_df = pd.read_csv(fan_out_file, na_filter=False, keep_default_na=False)
        fan_out_df[["confidence_nc", "confidence_ncc", "confidence_lcs_b", "confidence_lcs_u", "confidence_leven"]] = fan_out_df.apply(
            establish_confidence,
            axis=1
        ).round(2)
        fan_out_df["confidence_lc"] = (
                fan_out_df.groupby("from_url").cumcount()
                == fan_out_df.groupby("from_url")["from_url"].transform("size") - 1
        ).astype(int)
        # fan_out_df["repo_name"] = [repository_name] * len(fan_out_df)

        fan_in_count_file = f"{DATA_DIRECTORY}/m2m-confidence/{repository_name}.csv"
        os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
        fan_out_df.to_csv(fan_in_count_file, index=False)