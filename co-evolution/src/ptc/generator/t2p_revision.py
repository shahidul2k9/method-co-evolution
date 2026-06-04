import os
import warnings
from pathlib import Path

import pandas as pd

from ptc.constants import MethodChangeType
from mhc.command_util import (
    build_experiment_parser,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_revision_columns,
    select_named_items,
)
from ptc.generator.run_stats import GenerationStats, should_generate, unlink_stale_output

CHANGE_COLUMNS = [
    "ch_all",
    "ch_diff",
    *[f"ch_{change_type.name.lower()}" for change_type in MethodChangeType],
]


def build_parser():
    return build_experiment_parser(
        "Merge test-to-production links with method change data.",
        include_replace=True,
        projects_help="Comma-separated project names to process.",
        strategies_help="Comma-separated strategy names to process.",
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("t2p_revision")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    selected_change_columns = select_revision_columns(CHANGE_COLUMNS, preferred_order=CHANGE_COLUMNS)
    tool_dirs = [
        name for name in os.listdir(experiment_directory / "method-history")
        if os.path.isdir(experiment_directory / "method-history" / name)
    ]
    for tooName in select_named_items(tool_dirs, selected_tools, item_label="tool"):
        for change_file in list_csv_files(experiment_directory / "method-history" / tooName, selected_projects, strict=False):
            repository_name = change_file.stem
            change_df = None
            change_columns = []
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
                t2p_change_file = experiment_directory / "t2p-change" / tooName / t2p_strategy / change_file.name
                label = f"{repository_name} [{tooName}/{t2p_strategy}]"
                if not os.path.exists(t2p_file):
                    unlink_stale_output(
                        t2p_change_file,
                        reason=f"Skipping: {label} (missing t2p-link file)",
                        stats=stats,
                    )
                    continue
                if not should_generate(t2p_change_file, replace=args.replace, label=label, stats=stats):
                    continue

                if change_df is None:
                    change_df = pd.read_csv(change_file, keep_default_na=False, na_filter=False, low_memory=False)
                    change_columns = [column for column in selected_change_columns if column in change_df.columns]
                    change_df = change_df[["url", *change_columns]]

                print("Processing:", label)
                t2p_tech_df = pd.read_csv(t2p_file, keep_default_na=False, na_filter=False)

                t2p_change_df = (t2p_tech_df.merge(change_df.add_prefix("from_"), on="from_url", how="inner")
                                 .merge(change_df.add_prefix("to_"), on="to_url", how="inner"))
                paired_change_columns = [
                    prefixed_column
                    for change_column in change_columns
                    for prefixed_column in (f"from_{change_column}", f"to_{change_column}")
                ]
                t2p_change_df["tool"] = tooName
                output_columns = list(t2p_tech_df.columns)
                if "project" in output_columns:
                    output_columns.insert(output_columns.index("project") + 1, "tool")
                else:
                    output_columns = ["tool"] + output_columns
                t2p_change_df = t2p_change_df[output_columns + paired_change_columns]

                os.makedirs(t2p_change_file.parent, exist_ok=True)
                t2p_change_df.to_csv(t2p_change_file, index=False)
                if t2p_change_df.empty:
                    stats.record_empty_output()
                stats.record_write(len(t2p_change_df))
    stats.print_summary()


if __name__ == "__main__":
    main()
