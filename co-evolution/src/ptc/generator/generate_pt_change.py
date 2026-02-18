from pathlib import Path

import pandas as pd

from mhc.config import *
from ptc.constants import LinkStrategy, MethodChangeType

repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")
repository_name_map = {row["repo_name"]: row for row in repository_df.to_dict(orient="records")}

pt_link_dfs = [pd.read_csv(file, keep_default_na=False, na_filter=False) for
               file in list(Path(f"{DATA_DIRECTORY}/m2m-link").rglob("*.csv"))]
pt_link_df = pd.concat(pt_link_dfs)
change_count_df_columns = ["url", "method_type", "ch_all", "ch_diff"] + [f"ch_{change_type.name.lower()}" for change_type in MethodChangeType]

for tooName in os.listdir(f"{CACHE_DIRECTORY}/history"):
    history_repository_dfs = [pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False) for
                              repository_history_file in
                              list(Path(f"{DATA_DIRECTORY}/history/{tooName}").rglob("*.csv"))]
    history_df = pd.concat(filter(lambda df: not df.empty, history_repository_dfs))
    for _, repo in repository_df.iterrows():
        repository_name = repo["repo_name"]
        commit_hash = repo["updated_hash"]

        pt_link_file = f"{DATA_DIRECTORY}/m2m-link/{repository_name}.csv"

        if os.path.exists(pt_link_file):
            pt_link_df = pd.read_csv(pt_link_file, keep_default_na=False, na_filter=False)

            # # identify rows that are unique w.r.t caller or callee
            # unique_mask = (
            #         ~pt_link_df.duplicated(subset="caller_url", keep=False) |
            #         ~pt_link_df.duplicated(subset="callee_url", keep=False)
            # )
            #
            # # rows where link_nc or link_ncc is 1
            # link_mask = (pt_link_df["link_nc"] == 1) | (pt_link_df["link_ncc"] == 1)
            #
            # # keep rows that satisfy either condition
            # pt_link_df = pt_link_df[unique_mask | link_mask]

            for link_strategy in LinkStrategy:
                for tool_name in history_df["tool_name"].unique():
                    if link_strategy.value == "lc":
                        score_cols = ["link_lc"]
                    elif link_strategy.value == "max":
                        score_cols = [
                            "link_nc",
                            "link_ncc",
                            "link_lcs_b",
                            "link_lcs_u",
                            "link_leven",
                        ]
                    else:
                        raise ValueError(f"Unknown link strategy: {link_strategy}")

                    tool_df = history_df[
                        (history_df["repo_name"] == repository_name) & (history_df["tool_name"] == tool_name)][change_count_df_columns]

                    pt_link_change_df = (pt_link_df.merge(tool_df.add_prefix("caller_"), on="caller_url", how="inner")
                     .merge(tool_df.add_prefix("callee_"), on="callee_url", how="inner"))

                    pt_link_change_df = (pt_link_change_df[(pt_link_change_df["caller_method_type"] == "test") & (pt_link_change_df["callee_method_type"] == "production")])

                    pt_link_change_df["_row_id"] = pt_link_change_df.index
                    best_links_change_df = (
                        pt_link_change_df
                        .sort_values(
                            by=["caller_url"] + score_cols + ["_row_id"],
                            ascending=[True] + [False] * len(score_cols) + [False],
                        )
                        .groupby("caller_url", as_index=False)
                        .first()
                        .sort_values(by=["_row_id"], ascending=True)
                    )

                    change_df = (
                        best_links_change_df
                        .assign(tool_name=tool_name)
                        .drop(columns=["_row_id"], errors="ignore")
                    )
                    fan_in_count_file = f"{DATA_DIRECTORY}/pt-change/{tooName}/{link_strategy.value}/{repository_name}.csv"
                    os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
                    change_df.to_csv(fan_in_count_file, index=False)
