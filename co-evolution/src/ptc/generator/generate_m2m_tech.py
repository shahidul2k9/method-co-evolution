import os
from pathlib import Path

import pandas as pd
from pytctracer.techniques.levenshtein_distance import *
from pytctracer.techniques.longest_common_subsequence import *
from pytctracer.techniques.naming_conventions import *

import mhc.util as util
from mhc.config import *
from ptc.link_strategy import LinkStrategy, STRATEGY_KEYS

# ---------------------------
# Config
# ---------------------------

MAX_EXPANSION_DEPTH = 5

FANOUT_DIR = f"{DATA_DIRECTORY}/fan-out"
METHOD_DIR = f"{DATA_DIRECTORY}/method"
T2P_CANDIDATE_DIR = f"{DATA_DIRECTORY}/t2p-candidate"
OUTPUT_DIR = f"{DATA_DIRECTORY}/m2m-tech"
LLM_PREDICTION_DIR = Path(CACHE_DIRECTORY) / "data" / "llm" / "t2p-link"

os.makedirs(T2P_CANDIDATE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ---------------------------
# Techniques
# ---------------------------

nc = NamingConventions()
ncc = NamingConventionsContains()
ld = LevenshteinDistance()
lcsUnit = LongestCommonSubsequenceUnit()
lcsBoth = LongestCommonSubsequenceUnit()

def llm_strategy_directory_names() -> list[str]:
    return [
        STRATEGY_KEYS[strategy]
        for strategy in STRATEGY_KEYS
        if strategy.name.startswith("LLM_")
    ]


def apply_llm_techniques(
    t2p_candidate_df: pd.DataFrame,
    project: str,
    llm_directory_names: list[str],
    llm_prediction_root: Path = LLM_PREDICTION_DIR,
) -> pd.DataFrame:
    enriched_df = t2p_candidate_df.copy()

    for directory_name in llm_directory_names:
        column_name = f"tech_{directory_name}"
        prediction_file = llm_prediction_root / directory_name / f"{project}.csv"

        if not prediction_file.exists():
            enriched_df[column_name] = pd.Series([pd.NA] * len(enriched_df), dtype="Int64")
            continue

        prediction_df = pd.read_csv(prediction_file, keep_default_na=False, na_filter=False)
        required_columns = {"from_url", "to_url", "label_pred"}
        missing_columns = required_columns.difference(prediction_df.columns)
        if missing_columns:
            raise ValueError(
                f"Prediction file {prediction_file} is missing required columns: {sorted(missing_columns)}"
            )

        llm_match_df = (
            prediction_df.loc[:, ["from_url", "to_url", "label_pred"]]
            .drop_duplicates(subset=["from_url", "to_url"], keep="last")
            .rename(columns={"label_pred": column_name})
        )
        llm_match_df[column_name] = pd.to_numeric(llm_match_df[column_name], errors="coerce").astype("Int64")
        enriched_df = enriched_df.merge(llm_match_df, on=["from_url", "to_url"], how="left")

    return enriched_df


# ---------------------------
# Confidence computation
# ---------------------------

def establish_confidence(row):
    test_name = row["from_name"].lower()
    production_name = row["to_name"].lower()

    return pd.Series({
        "tech_nc": nc._compute_nc_score(production_name, test_name),
        "tech_ncc": ncc._compute_nc_score(production_name, test_name),
        "tech_lcs_b": lcsBoth._compute_lcs_score(production_name, test_name),
        "tech_lcs_u": lcsUnit._compute_lcs_score(production_name, test_name),
        "tech_leven": ld._compute_levenshtein_score(production_name, test_name)
    })


# ---------------------------
# Main Processing
# ---------------------------

def main() -> None:
    repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")
    llm_directory_names = llm_strategy_directory_names()

    for _, repo in repository_df.iterrows():
        project = repo["project"]
        commit_hash = repo["updated_hash"]

        t2p_candidate_file = f"{T2P_CANDIDATE_DIR}/{project}.csv"
        method_file = f"{METHOD_DIR}/{project}.csv"

        if os.path.exists(t2p_candidate_file):
            print("Processing:", project)

            t2p_candidate_df = pd.read_csv(t2p_candidate_file, na_filter=False, keep_default_na=False)

            # ---------------------------
            # Apply Techniques
            # ---------------------------

            t2p_candidate_df[[
                "tech_nc",
                "tech_ncc",
                "tech_lcs_b",
                "tech_lcs_u",
                "tech_leven"
            ]] = t2p_candidate_df.apply(
                establish_confidence,
                axis=1
            ).round(2)

            t2p_candidate_df["tech_lc"] = (
                    t2p_candidate_df.groupby("from_url").cumcount()
                    == t2p_candidate_df.groupby("from_url")["from_url"].transform("size") - 1
            ).astype(int)

            t2p_candidate_df["tech_lcba"] = t2p_candidate_df["to_lcba"].astype(int)
            t2p_candidate_df = apply_llm_techniques(
                t2p_candidate_df=t2p_candidate_df,
                project=project,
                llm_directory_names=llm_directory_names,
            )

            expanded_df = util.convert_float_int_columns_to_nullable_int(t2p_candidate_df)

            output_file = f"{OUTPUT_DIR}/{project}.csv"
            expanded_df.to_csv(output_file, index=False)

    print("Finished.")


if __name__ == "__main__":
    main()
