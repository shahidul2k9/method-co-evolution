from pathlib import Path

import pandas as pd

from mhc.config import *
from ptc.constants import MethodChangeType
from ptc.link_strategy import *
LINK_STRATEGY_PRIORITY: list[LinkStrategy] = [
    LinkStrategy.O2O,
    LinkStrategy.NC,
    LinkStrategy.NCC,
    LinkStrategy.LCBA,
    LinkStrategy.LC,
    LinkStrategy.MAX,
]
METHOD_LINK_STRATEGIES: list[LinkStrategy] = [
    LinkStrategy.O2O,
    LinkStrategy.NC,
    LinkStrategy.NCC,
    LinkStrategy.LC,
    LinkStrategy.MAX,
    LinkStrategy.O2O | LinkStrategy.NC | LinkStrategy.NCC,
    LinkStrategy.O2O | LinkStrategy.NC | LinkStrategy.NCC | LinkStrategy.LC,
    LinkStrategy.O2O | LinkStrategy.NC | LinkStrategy.NCC | LinkStrategy.MAX,

]
def iter_atomic_strategies(mask: LinkStrategy) -> list[LinkStrategy]:
    """Return enabled single strategies in fixed priority order."""
    return [s for s in LINK_STRATEGY_PRIORITY if s in mask]

def select_one_stage_indices(
    pt_link_df: pd.DataFrame,
    stage: LinkStrategy,
) -> pd.Index:
    """
    Select row indices for ONE atomic stage only.

    Assumes pt_link_df is the original dataframe.
    This function does not know about keep_mask or caller exclusion.

    - Non-MAX stages: filter only (no sorting, no dedup)
    - MAX stage: filter + sort only (no dedup)
    """
    if pt_link_df.empty:
        return pt_link_df.index[:0]

    if stage == LinkStrategy.O2O:
        candidate_mask = (
            ~pt_link_df.duplicated(subset="caller_url", keep=False)
            | ~pt_link_df.duplicated(subset="callee_url", keep=False)
        )
        return pt_link_df.loc[candidate_mask].index

    if stage == LinkStrategy.NC:
        return pt_link_df.loc[pt_link_df["link_nc"] == 1].index

    if stage == LinkStrategy.NCC:
        return pt_link_df.loc[pt_link_df["link_ncc"] == 1].index

    if stage == LinkStrategy.LCBA:
        return pt_link_df.loc[pt_link_df["link_lcs_b"] > 0].index

    if stage == LinkStrategy.LC:
        return pt_link_df.loc[pt_link_df["link_lc"] > 0].index

    if stage == LinkStrategy.MAX:
        score_cols = ["link_nc", "link_ncc", "link_lcs_b", "link_lcs_u", "link_leven"]
        candidates = pt_link_df.loc[pt_link_df[score_cols].max(axis=1) > 0]
        if candidates.empty:
            return candidates.index[:0]

        # sort only (no dedup) - preserves ranking for later one-hot selection
        return (
            candidates.assign(_idx=candidates.index)
            .sort_values(
                by=["caller_url"] + score_cols + ["_idx"],
                ascending=[True] + [False] * len(score_cols) + [True],
            )["_idx"]
            .astype(int)
            .pipe(pd.Index)
        )

    raise ValueError(f"Unsupported stage: {stage}")


def _stage_mask_one_hot_by_caller(
    pt_link_df: pd.DataFrame,
    candidate_idx: pd.Index,
    keep_mask: pd.Series,
) -> pd.Series:
    """
    Augment and return a NEW keep_mask using stage candidates.

    Rules:
    - Skip caller_url already selected in keep_mask
    - If candidate_idx contains multiple rows for the same caller_url,
      keep only the first one (candidate_idx order is preserved)
    """
    new_mask = keep_mask.copy()

    # callers already selected by previous stages
    seen_callers = set(pt_link_df.loc[new_mask, "caller_url"])

    for idx in candidate_idx:
        caller = pt_link_df.at[idx, "caller_url"]
        if caller in seen_callers:
            continue
        new_mask.at[idx] = True
        seen_callers.add(caller)

    return new_mask

def select_links_cascade(
    pt_link_df: pd.DataFrame,
    composite: LinkStrategy,
) -> pd.Series:
    """
    Greedy cascade over ORIGINAL pt_link_df.
    Returns keep_mask (boolean Series aligned to pt_link_df.index).

    Behavior:
    - Calls select_one_stage_indices(pt_link_df, stage) on the original dataframe
    - Enforces one-hot per caller_url in outer loop
    - Preserves stage order defined by LINK_STRATEGY_PRIORITY
    """
    keep_mask = pd.Series(False, index=pt_link_df.index)

    for stage in iter_atomic_strategies(composite):
        stage_candidate_idx = select_one_stage_indices(pt_link_df, stage)
        if len(stage_candidate_idx) == 0:
            continue

        keep_mask = _stage_mask_one_hot_by_caller(
            pt_link_df=pt_link_df,
            candidate_idx=stage_candidate_idx,
            keep_mask=keep_mask,
        )

    return keep_mask


def strategy_output_key(mask: LinkStrategy) -> str:
    """Stable key for path/logging (single or composite)."""
    parts = [s.name.lower() for s in iter_atomic_strategies(mask)]
    return "-".join(parts) if parts else "none"

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
            for tool_name in history_df["tool_name"].unique():
                tool_df = history_df[
                    (history_df["repo_name"] == repository_name) & (history_df["tool_name"] == tool_name)][change_count_df_columns]

                pt_link_change_df = (pt_link_df.merge(tool_df.add_prefix("caller_"), on="caller_url", how="inner")
                 .merge(tool_df.add_prefix("callee_"), on="callee_url", how="inner"))

                pt_link_change_df = (pt_link_change_df[(pt_link_change_df["caller_method_type"] == "test") & (pt_link_change_df["callee_method_type"] == "production")])

                for link_strategy in METHOD_LINK_STRATEGIES:
                    keep_mask = select_links_cascade(pt_link_change_df, link_strategy)
                    change_df = pt_link_change_df.loc[keep_mask].copy()
                    print(tool_name, repository_name, link_strategy, strategy_output_key(link_strategy), len(change_df))
                    # Optional safety check: exactly one selected row per caller_url
                    counts = change_df["caller_url"].value_counts()
                    assert (counts == 1).all(), "Duplicate caller_url selections found"
                    change_df = change_df.assign(tool_name=tool_name)
                    fan_in_count_file = f"{DATA_DIRECTORY}/pt-change/{tooName}/{strategy_output_key(link_strategy)}/{repository_name}.csv"
                    os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
                    change_df.to_csv(fan_in_count_file, index=False)
