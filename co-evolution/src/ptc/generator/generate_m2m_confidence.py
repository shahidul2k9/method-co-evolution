import Levenshtein
import pandas as pd

import mhc.util as util
from mhc.config import *
from pytctracer.techniques.naming_conventions import *
from pytctracer.techniques.levenshtein_distance import *
from pytctracer.techniques.longest_common_subsequence import *
from pytctracer.techniques.last_call_before_assert import *

nc = NamingConventions()
ncc = NamingConventionsContains()
ld = LevenshteinDistance()
lcsUnit = LongestCommonSubsequenceUnit()
lcsBoth = LongestCommonSubsequenceUnit()


repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")

repository_name_map = {row["project"]: row for row in repository_df.to_dict(orient="records")}


def establish_confidence(row):
    test_method_name = row["from_name"]
    production_method_name = row["to_name"]
    return pd.Series({
        "confidence_nc": nc._compute_nc_score(production_method_name, test_method_name),
        "confidence_ncc": ncc._compute_nc_score(production_method_name, test_method_name),
        "confidence_lcs_b": lcsBoth._compute_lcs_score(production_method_name, test_method_name),
        "confidence_lcs_u": lcsUnit._compute_lcs_score(production_method_name, test_method_name),
        "confidence_leven": ld._compute_levenshtein_score(production_method_name, test_method_name)})


# repository_df = repository_df[repository_df["project"].str.startswith("Apktool")]
for _, repo in repository_df.iterrows():
    repository_name = repo["project"]
    commit_hash = repo["updated_hash"]
    fan_out_file_suffix = f"{repository_name}.csv"
    # fan_out_file_suffix = f"{repository_name}--fan-out--{commit_hash}.csv"
    fan_out_file = f"{DATA_DIRECTORY}/fan-out/{fan_out_file_suffix}"
    if os.path.exists(fan_out_file):
        fan_out_df = pd.read_csv(fan_out_file, na_filter=False, keep_default_na=False)
        fan_out_df = fan_out_df[fan_out_df["to_url"].str.strip() != ""]
        fan_out_df[["confidence_nc", "confidence_ncc", "confidence_lcs_b", "confidence_lcs_u", "confidence_leven"]] = fan_out_df.apply(
            establish_confidence,
            axis=1
        ).round(2)
        fan_out_df["confidence_lc"] = (
                fan_out_df.groupby("from_url").cumcount()
                == fan_out_df.groupby("from_url")["from_url"].transform("size") - 1
        ).astype(int)
        fan_out_df = util.convert_float_int_columns_to_nullable_int(fan_out_df)

        fan_in_count_file = f"{DATA_DIRECTORY}/m2m-confidence/{repository_name}.csv"
        os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
        fan_out_df.to_csv(fan_in_count_file, index=False)