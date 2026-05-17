import logging
from pathlib import Path
import os
import pandas as pd
from mhc.artifacts import is_test_case_method, is_main_code
from pytctracer.config.constants.technique_threshold import TechniqueThreshold

from ptc.experiment_util import build_experiment_parser, list_csv_files, resolve_experiment_filters, resolve_experiment_paths
from ptc.link_strategy import *

LINK_STRATEGY_PRIORITY: list[LinkStrategy] = [
    LinkStrategy.OMC,
    LinkStrategy.NC,
    LinkStrategy.NCC,
    LinkStrategy.LCBA,
    LinkStrategy.LC,
    LinkStrategy.MAX,
    LinkStrategy.LCS_U,
    LinkStrategy.LCS_B,
    LinkStrategy.LEVEN,
    LinkStrategy.TARANTULA,
    LinkStrategy.TFIDF,
    LinkStrategy.COMBINED,
    LinkStrategy.LLM_GPT_OSS_20B,
    LinkStrategy.LLM_GPT_OSS_120B,
    LinkStrategy.LLM_QWEN_2D5B,
    LinkStrategy.TESTLINKER,
]
METHOD_LINK_STRATEGIES: list[LinkStrategy] = [
    LinkStrategy.OMC,
    LinkStrategy.NC,
    LinkStrategy.NCC,
    LinkStrategy.LC,
    LinkStrategy.LCBA,
    LinkStrategy.MAX,
    LinkStrategy.LCS_U,
    LinkStrategy.LCS_B,
    LinkStrategy.LEVEN,
    LinkStrategy.TARANTULA,
    LinkStrategy.TFIDF,
    LinkStrategy.COMBINED,
    LinkStrategy.OMC | LinkStrategy.NC,
    LinkStrategy.OMC | LinkStrategy.NC | LinkStrategy.NCC,
    LinkStrategy.OMC | LinkStrategy.NC | LinkStrategy.NCC | LinkStrategy.LCBA,
    LinkStrategy.OMC | LinkStrategy.NC | LinkStrategy.NCC | LinkStrategy.MAX,
    LinkStrategy.OMC | LinkStrategy.NC | LinkStrategy.NCC | LinkStrategy.LCS_U,
    LinkStrategy.OMC | LinkStrategy.NC | LinkStrategy.NCC | LinkStrategy.LCS_B,
    LinkStrategy.OMC | LinkStrategy.NC | LinkStrategy.NCC | LinkStrategy.LEVEN,
    LinkStrategy.OMC | LinkStrategy.NC | LinkStrategy.NCC | LinkStrategy.COMBINED,
    LinkStrategy.LLM_GPT_OSS_20B,
    LinkStrategy.LLM_GPT_OSS_120B,
    LinkStrategy.LLM_QWEN_2D5B,
    LinkStrategy.TESTLINKER,

]

SCORE_STAGE_THRESHOLDS: dict[LinkStrategy, tuple[str, float]] = {
    LinkStrategy.LCS_U: ("tech_lcs_u", TechniqueThreshold.THRESHOLD_FOR_LCSU.value),
    LinkStrategy.LCS_B: ("tech_lcs_b", TechniqueThreshold.THRESHOLD_FOR_LCSB.value),
    LinkStrategy.LEVEN: ("tech_leven", TechniqueThreshold.THRESHOLD_FOR_LEVENSHTEIN.value),
    LinkStrategy.TARANTULA: ("tech_tarantula", TechniqueThreshold.THRESHOLD_FOR_LEVENSHTEIN.value),
    LinkStrategy.TFIDF: ("tech_tfidf", TechniqueThreshold.THRESHOLD_FOR_TFIDF.value),
    LinkStrategy.COMBINED: ("tech_combined", TechniqueThreshold.THRESHOLD_FOR_COMBINED.value),
}


def build_parser():
    return build_experiment_parser(
        "Generate test-to-production links from method-to-method technique scores.",
        include_tools=False,
        include_strategies=False,
        projects_help="Comma-separated project names to process.",
    )


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
    indexes = pt_link_df.iloc[:0].index
    match stage:
        case LinkStrategy.OMC:
            candidate_mask = (~pt_link_df.duplicated(subset=["from_url"], keep=False))
            indexes = pt_link_df.loc[candidate_mask].index
        case LinkStrategy.NC:
            indexes = pt_link_df.loc[pt_link_df["tech_nc"] > 0].index

        case LinkStrategy.NCC:
            indexes = pt_link_df.loc[pt_link_df["tech_ncc"] > 0].index

        case LinkStrategy.LC:
            indexes = pt_link_df.loc[pt_link_df["tech_lc"] > 0].index

        case LinkStrategy.LCBA:
            indexes = pt_link_df.loc[pt_link_df["tech_lcba"] > 0].index

        case LinkStrategy.MAX:
            score_cols = [
                "tech_nc",
                "tech_ncc",
                "tech_lcs_u",
                "tech_lcs_b",
                "tech_leven",
                "tech_lcba",
                "tech_tarantula",
                "tech_tfidf",
                "tech_combined",
            ]
            candidates = pt_link_df.loc[pt_link_df[score_cols].max(axis=1) > 0]
            indexes = (
                candidates.assign(_idx=candidates.index)
                .sort_values(
                    by=["from_url"] + score_cols + ["_idx"],
                    ascending=[True] + [False] * len(score_cols) + [True],
                )["_idx"]
                .astype(int)
                .pipe(pd.Index)
            )
        case _ if stage in SCORE_STAGE_THRESHOLDS:
            column_name, threshold = SCORE_STAGE_THRESHOLDS[stage]
            indexes = _select_score_stage_indices(pt_link_df, column_name, threshold)

        case _ if stage in {
            LinkStrategy.LLM_GPT_OSS_20B,
            LinkStrategy.LLM_GPT_OSS_120B,
            LinkStrategy.LLM_QWEN_2D5B,
        }:
            indexes = _select_llm_stage_indices(pt_link_df, stage)
        case LinkStrategy.TESTLINKER:
            indexes = _select_binary_stage_indices(pt_link_df, "tech_testlinker")
        case _:
            raise ValueError(f"Unsupported stage: {stage}")
    return indexes


def _select_score_stage_indices(pt_link_df: pd.DataFrame, column_name: str, threshold: float) -> pd.Index:
    if column_name not in pt_link_df.columns:
        return pt_link_df.iloc[:0].index

    score_values = pd.to_numeric(pt_link_df[column_name], errors="coerce")
    candidates = pt_link_df.loc[score_values >= threshold].copy()
    if candidates.empty:
        return candidates.index

    return (
        candidates.assign(_score=score_values.loc[candidates.index], _idx=candidates.index)
        .sort_values(
            by=["from_url", "_score", "_idx"],
            ascending=[True, False, True],
        )["_idx"]
        .astype(int)
        .pipe(pd.Index)
    )


def _select_llm_stage_indices(pt_link_df: pd.DataFrame, stage: LinkStrategy) -> pd.Index:
    llm_column = _llm_stage_column_name(pt_link_df, stage)
    if llm_column is None:
        return pt_link_df.iloc[:0].index
    llm_values = pd.to_numeric(pt_link_df[llm_column], errors="coerce")
    return pt_link_df.loc[llm_values > 0].index


def _select_binary_stage_indices(pt_link_df: pd.DataFrame, column_name: str) -> pd.Index:
    if column_name not in pt_link_df.columns:
        return pt_link_df.iloc[:0].index
    values = pd.to_numeric(pt_link_df[column_name], errors="coerce")
    return pt_link_df.loc[values > 0].index


def _llm_stage_column_name(pt_link_df: pd.DataFrame, stage: LinkStrategy) -> str | None:
    strategy_name = strategy_key(stage)
    underscore_strategy_name = strategy_name.replace("-", "_")
    candidates = [
        f"tech_llm_{strategy_name}",
        f"tech_llm_{underscore_strategy_name}",
        f"tech_{strategy_name}",
        f"tech_{underscore_strategy_name}",
    ]
    for column_name in candidates:
        if column_name in pt_link_df.columns:
            return column_name
    return None


def _stage_mask_by_caller(pt_link_df: pd.DataFrame, candidate_idx: pd.Index, keep_mask: pd.Series) -> pd.Series:
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
        # from_url = pt_link_df.at[idx, "from_url"]
        # if from_url not in seen_callers:
        #     new_mask.at[idx] = True
        #     seen_callers.add(from_url)
        new_mask.at[idx] = True
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
        # stage_candidate_idx.to_series(index = False).to_csv(f"{EXPERIMENT_DIRECTORY}/aggregate/stage-index-{project}.csv")
        if len(stage_candidate_idx) > 0:
            keep_mask = _stage_mask_by_caller(pt_link_df=pt_link_df, candidate_idx=stage_candidate_idx,
                                              keep_mask=keep_mask)

    return keep_mask


def strategy_output_key(mask: LinkStrategy) -> str:
    """Stable key for path/logging (single or composite)."""
    parts = [STRATEGY_KEYS.get(atomic_link) for atomic_link in iter_atomic_strategies(mask)]
    return "--".join(parts) if parts else "none"


def filter_test_case_to_main_code_links(t2p_link_df: pd.DataFrame) -> pd.DataFrame:
    return t2p_link_df[
        t2p_link_df["from_artifact"].map(is_test_case_method)
        & t2p_link_df["to_artifact"].map(is_main_code)
    ].copy()


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    _, selected_projects, _ = resolve_experiment_filters(
        use_filters=args.use_filters,
        projects=args.projects,
    )
    for t2p_tech_file in list_csv_files(experiment_directory / "t2p-tech", selected_projects, strict=False):
        t2p_tech_df = pd.read_csv(t2p_tech_file, keep_default_na=False, na_filter=False)
        assert len(t2p_tech_df["project"].unique()) == 1, "Each file must be for the same repository_name"
        repository_name = t2p_tech_df["project"].iloc[0]
        method_df = pd.read_csv(experiment_directory / "method" / f"{repository_name}.csv", keep_default_na=False, na_filter=False)
        method_df = method_df[["url", "artifact"]]

        t2p_link_df = (t2p_tech_df.merge(method_df.add_prefix("from_"), on="from_url", how="inner")
                       .merge(method_df.add_prefix("to_"), on="to_url", how="inner"))

        t2p_link_df = filter_test_case_to_main_code_links(t2p_link_df)


        # Remove constructor unless all the to_url are constructors
        is_constructor = t2p_link_df["to_expression"].str.contains("constructor", case=False, na=False)
        groups_with_methods = t2p_link_df.groupby("from_url")["to_expression"].transform(
            lambda x: (~x.str.contains("constructor", case=False, na=False)).any()
        )
        t2p_link_df = t2p_link_df[~(is_constructor & groups_with_methods)]

        for link_strategy in METHOD_LINK_STRATEGIES:
            keep_mask = select_links_cascade(t2p_link_df, link_strategy)
            unique_t2p_link_df = t2p_link_df.loc[keep_mask].copy()
            unique_t2p_link_df = unique_t2p_link_df.drop_duplicates(subset=["from_url", "to_url"])
            print(repository_name, strategy_output_key(link_strategy), len(unique_t2p_link_df))
            t2p_file = experiment_directory / "t2p-link" / strategy_output_key(link_strategy) / f"{repository_name}.csv"
            os.makedirs(t2p_file.parent, exist_ok=True)
            unique_t2p_link_df.to_csv(t2p_file, index=False)


if __name__ == "__main__":
    main()
