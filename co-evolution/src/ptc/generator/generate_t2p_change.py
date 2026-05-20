import os
import warnings
from pathlib import Path

import pandas as pd

from ptc.constants import MethodChangeType
from ptc.experiment_util import (
    build_experiment_parser,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)

CHANGE_COLUMNS = [
    "ch_all",
    "ch_diff",
    *[f"ch_{change_type.name.lower()}" for change_type in MethodChangeType],
]


def build_parser():
    return build_experiment_parser(
        "Merge test-to-production links with method change data.",
        include_tools=False,
        projects_help="Comma-separated project names to process.",
        strategies_help="Comma-separated strategy names to process.",
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    _, selected_projects, selected_strategies = resolve_experiment_filters(
        use_filters=args.use_filters,
        projects=args.projects,
        strategies=args.strategies,
    )
    tool_dirs = [
        name for name in os.listdir(experiment_directory / "method-history")
        if os.path.isdir(experiment_directory / "method-history" / name)
    ]
    for tooName in tool_dirs:
        for change_file in list_csv_files(experiment_directory / "method-history" / tooName, selected_projects, strict=False):
            change_df = pd.read_csv(change_file, keep_default_na=False, na_filter=False)
            change_df = change_df[["url", *CHANGE_COLUMNS]]

            repository_name = change_file.stem
            t2p_strategy_dirs = [
                name for name in os.listdir(experiment_directory / "t2p-link")
                if os.path.isdir(experiment_directory / "t2p-link" / name)
            ]
            for t2p_strategy in select_named_items(
                t2p_strategy_dirs,
                selected_strategies,
                item_label="strategy",
            ):
                t2p_file = experiment_directory / "t2p-link" / t2p_strategy / change_file.name
                if os.path.exists(t2p_file):
                    t2p_tech_df = pd.read_csv(t2p_file, keep_default_na=False, na_filter=False)

                    t2p_change_df = (t2p_tech_df.merge(change_df.add_prefix("from_"), on="from_url", how="inner")
                                     .merge(change_df.add_prefix("to_"), on="to_url", how="inner"))
                    paired_change_columns = [
                        prefixed_column
                        for change_column in CHANGE_COLUMNS
                        for prefixed_column in (f"from_{change_column}", f"to_{change_column}")
                    ]
                    t2p_change_df = t2p_change_df[
                        list(t2p_tech_df.columns) + paired_change_columns
                    ]

                    t2p_change_file = experiment_directory / "t2p-change" / tooName / t2p_strategy / change_file.name
                    os.makedirs(t2p_change_file.parent, exist_ok=True)
                    t2p_change_df.to_csv(t2p_change_file, index=False)
                else:
                    warnings.warn(f"{t2p_file} does not exist")


if __name__ == "__main__":
    main()
