import logging
from pathlib import Path

import pandas as pd

from mhc.config import *
from ptc.link_strategy import *

ONE_TO_ONE_MAPPING = False

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
    LinkStrategy.LCBA,
    LinkStrategy.MAX,
    LinkStrategy.O2O | LinkStrategy.NC,
    LinkStrategy.O2O | LinkStrategy.NC | LinkStrategy.NCC,
    LinkStrategy.O2O | LinkStrategy.NC | LinkStrategy.NCC | LinkStrategy.LCBA,
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
        candidate_mask = (~pt_link_df.duplicated(subset=["from_url"], keep=False))

        return pt_link_df.loc[candidate_mask].index

    if stage == LinkStrategy.NC:
        return pt_link_df.loc[pt_link_df["tech_nc"] > 0].index

    if stage == LinkStrategy.NCC:
        return pt_link_df.loc[pt_link_df["tech_ncc"] > 0].index

    if stage == LinkStrategy.LCBA:
        return pt_link_df.loc[pt_link_df["tech_lcs_b"] > 0].index

    if stage == LinkStrategy.LC:
        return pt_link_df.loc[pt_link_df["tech_lc"] > 0].index

    if stage == LinkStrategy.LCBA:
        return pt_link_df.loc[pt_link_df["tech_lcba"] > 0].index

    if stage == LinkStrategy.MAX:
        score_cols = ["tech_nc", "tech_ncc", "tech_lcs_b", "tech_lcs_u", "tech_leven", "tech_lcba"]
        candidates = pt_link_df.loc[pt_link_df[score_cols].max(axis=1) > 0]
        if candidates.empty:
            return candidates.index[:0]

        # sort only (no dedup) - preserves ranking for later one-hot selection
        return (
            candidates.assign(_idx=candidates.index)
            .sort_values(
                by=["from_url"] + score_cols + ["_idx"],
                ascending=[True] + [False] * len(score_cols) + [True],
            )["_idx"]
            .astype(int)
            .pipe(pd.Index)
        )

    raise ValueError(f"Unsupported stage: {stage}")


def _stage_mask_by_caller(pt_link_df: pd.DataFrame, candidate_idx: pd.Index, keep_mask: pd.Series, one_hot:bool) -> pd.Series:
    """
    Augment and return a NEW keep_mask using stage candidates.

    Rules:
    - Skip from_url already selected in keep_mask
    - If candidate_idx contains multiple rows for the same from_url,
      keep only the first one (candidate_idx order is preserved)
      :param one_hot:
    """
    new_mask = keep_mask.copy()

    # callers already selected by previous stages
    seen_callers = set(pt_link_df.loc[new_mask, "from_url"])

    for idx in candidate_idx:
        from_url = pt_link_df.at[idx, "from_url"]
        if from_url not in seen_callers or not one_hot:
            new_mask.at[idx] = True
            seen_callers.add(from_url)
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
    - Enforces one-hot per from_url in outer loop
    - Preserves stage order defined by LINK_STRATEGY_PRIORITY
    """
    keep_mask = pd.Series(False, index=pt_link_df.index)

    for stage in iter_atomic_strategies(composite):
        stage_candidate_idx = select_one_stage_indices(pt_link_df, stage)
        # stage_candidate_idx.to_series(index = False).to_csv(f"{DATA_DIRECTORY}/aggregate/stage-index-{project}.csv")
        if len(stage_candidate_idx) > 0:
            keep_mask = _stage_mask_by_caller(pt_link_df=pt_link_df, candidate_idx=stage_candidate_idx,
                                              keep_mask=keep_mask, one_hot=ONE_TO_ONE_MAPPING)

    return keep_mask


def strategy_output_key(mask: LinkStrategy) -> str:
    """Stable key for path/logging (single or composite)."""
    parts = [s.name.lower() for s in iter_atomic_strategies(mask)]
    return "-".join(parts) if parts else "none"


for m2m_link_file in list(Path(f"{DATA_DIRECTORY}/m2m-tech").rglob("*.csv")):
    m2m_link_df = pd.read_csv(m2m_link_file, keep_default_na=False, na_filter=False)
    assert len(m2m_link_df["project"].unique()) == 1, "Each file must be for the same repository_name"
    repository_name = m2m_link_df["project"].iloc[0]
    method_df = pd.read_csv(f"{DATA_DIRECTORY}/method/{repository_name}.csv", keep_default_na=False, na_filter=False)
    method_df = method_df[["url", "artifact"]]

    t2p_link_df = (m2m_link_df.merge(method_df.add_prefix("from_"), on="from_url", how="inner")
                   .merge(method_df.add_prefix("to_"), on="to_url", how="inner"))

    t2p_link_df = (t2p_link_df[(t2p_link_df["from_artifact"] == "test") & (t2p_link_df["to_artifact"] == "production")])

    for link_strategy in METHOD_LINK_STRATEGIES:
        keep_mask = select_links_cascade(t2p_link_df, link_strategy)
        change_df = t2p_link_df.loc[keep_mask].copy()
        print(repository_name, link_strategy, strategy_output_key(link_strategy), len(change_df))
        # Optional safety check: exactly one selected row per from_url
        counts = change_df["from_url"].value_counts()
        if ONE_TO_ONE_MAPPING:
            assert (counts == 1).all(), "Duplicate from_url selections found"
        t2p_file = f"{DATA_DIRECTORY}/t2p-link/{strategy_output_key(link_strategy)}/{repository_name}.csv"
        os.makedirs(os.path.dirname(t2p_file), exist_ok=True)
        change_df.to_csv(t2p_file, index=False)
