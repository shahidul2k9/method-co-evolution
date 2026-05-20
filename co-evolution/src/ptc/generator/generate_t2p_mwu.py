import os
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import kendalltau

import mhc.util as util
from mhc.artifacts import artifact_group
from ptc.constants import ALL_REPOSITORY, CODE_SHOVEL_UNSUPPORTED_CHANGES
from ptc.experiment_util import build_experiment_parser, list_csv_files, resolve_experiment_filters, resolve_experiment_paths, select_named_items
from ptc.plot_util import man_utest

STAT_COLUMNS = [
    "project",
    "tool",
    "strategy",
    "size",
    "change",
    "corr",
    "corr_p",
    "mwu_u1",
    "mwu_u2",
    "mwu_p",
    "mwu_d",
    "mwu_size",
]
MIN_METHOD_PAIRS_FOR_MWU = 3
code_shovel_unsupported_change_set = {
    f"ch_{change_type.name.lower()}" for change_type in CODE_SHOVEL_UNSUPPORTED_CHANGES
}


def build_parser():
    return build_experiment_parser(
        "Aggregate Mann-Whitney U statistics for linked test/production changes.",
        projects_help="Comma-separated project names to process.",
    )


def build_stat_row(project: str, tool: str, strategy: str, change: str, pair_df: pd.DataFrame) -> dict | None:
    if pair_df.empty:
        return None

    production_change = pair_df[f"to_{change}"]
    test_change = pair_df[f"from_{change}"]
    if production_change.empty or test_change.empty:
        return None

    if len(pair_df) < 2 or production_change.std() == 0 or test_change.std() == 0:
        corr = np.nan
        corr_p = np.nan
    else:
        corr_result = kendalltau(production_change, test_change)
        corr = corr_result.statistic
        corr_p = corr_result.pvalue

    mwu_u1, mwu_p, mwu_d, mwu_size = man_utest(production_change, test_change)
    mwu_u2 = len(production_change) * len(test_change) - mwu_u1
    return {
        "project": project,
        "tool": tool,
        "strategy": strategy,
        "size": len(pair_df),
        "change": change.replace("ch_", ""),
        "corr": round(corr, 2) if pd.notna(corr) else np.nan,
        "corr_p": round(corr_p, 2) if pd.notna(corr_p) else np.nan,
        "mwu_u1": round(mwu_u1, 2),
        "mwu_u2": round(mwu_u2, 2),
        "mwu_p": round(mwu_p, 2),
        "mwu_d": round(mwu_d, 2),
        "mwu_size": mwu_size,
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    stats_rows = []

    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        use_filters=args.use_filters,
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    t2p_change_dir = experiment_directory / "t2p-change"
    if not t2p_change_dir.exists():
        warnings.warn(f"Directory not found, skipping: {t2p_change_dir}")
        return
    tools = select_named_items(
        util.sorted_directory_names(t2p_change_dir),
        selected_tools,
        item_label="tool",
    )
    for tool in tools:
        tool_dir = t2p_change_dir / tool
        if not tool_dir.exists():
            warnings.warn(f"Tool directory not found, skipping: {tool_dir}")
            continue
        strategies = select_named_items(
            util.sorted_directory_names(tool_dir),
            selected_strategies,
            item_label="strategy",
        )
        for strategy in strategies:
            csv_files = list_csv_files(
                t2p_change_dir / tool / strategy,
                selected_projects,
                strict=False,
            )
            history_repository_dfs = [
                pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False)
                for repository_history_file in csv_files
            ]
            history_repository_dfs = [df for df in history_repository_dfs if not df.empty]
            if not history_repository_dfs:
                continue

            df = pd.concat(history_repository_dfs)
            for prefix in ["from_", "to_"]:
                df[f"{prefix}artifact"] = df[f"{prefix}artifact"].map(artifact_group)

            change_cols = [c[len("from_"):] for c in df.columns if c.startswith("from_ch_")]
            projects = select_named_items(
                sorted(df["project"].unique(), key=str.lower),
                selected_projects,
                item_label="project",
                strict=False,
            )
            projects.append(ALL_REPOSITORY)

            for project in projects:
                project_df = df if project == ALL_REPOSITORY else df[df["project"] == project]
                project_size = len(project_df)
                if project_size < MIN_METHOD_PAIRS_FOR_MWU:
                    warnings.warn(
                        "Skipping MWU statistics for "
                        f"project={project}, tool={tool}, strategy={strategy}: "
                        f"size {project_size} is below minimum threshold {MIN_METHOD_PAIRS_FOR_MWU}."
                    )
                    continue

                for change in change_cols:
                    if tool == "codeShovel" and change in code_shovel_unsupported_change_set:
                        continue

                    pair_df = project_df[[f"to_{change}", f"from_{change}"]].dropna()
                    stat_row = build_stat_row(project, tool, strategy, change, pair_df)
                    if stat_row is not None:
                        stats_rows.append(stat_row)

    stats_output_file = experiment_directory / "aggregate" / "t2p-mwu.csv"
    os.makedirs(stats_output_file.parent, exist_ok=True)
    stats_df = pd.DataFrame(stats_rows, columns=STAT_COLUMNS)
    stats_df = stats_df.sort_values(["project", "tool", "strategy", "change"]).reset_index(drop=True)
    stats_df.to_csv(stats_output_file, index=False)


if __name__ == "__main__":
    main()
