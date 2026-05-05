import argparse
import os
from pathlib import Path

import pandas as pd

import mhc.util as util
from mhc.config import WORKSPACE_DIRECTORY, DATA_DIRECTORY
from ptc.constants import CODE_SHOVEL_UNSUPPORTED_CHANGES, MethodChangeType
from ptc.experiment_util import (
    build_experiment_parser,
    list_csv_files,
    resolve_experiment_filters,
    select_named_items,
)

CHANGE_COLUMNS = [
    "ch_all",
    "ch_diff",
    *[f"ch_{change_type.name.lower()}" for change_type in MethodChangeType],
]
OUTPUT_FILE = Path(WORKSPACE_DIRECTORY) / "data" / "aggregate" / "t2p-delta.csv"
CODE_SHOVEL_UNSUPPORTED_CHANGE_SET = {
    f"ch_{change_type.name.lower()}" for change_type in CODE_SHOVEL_UNSUPPORTED_CHANGES
}


def build_parser() -> argparse.ArgumentParser:
    return build_experiment_parser(
        "Aggregate counts where test changes exceed production changes.",
        filters_help="Apply tool, project, and strategy filters.",
        tools_help="Comma-separated tool names to include.",
        projects_help="Comma-separated project names to include.",
        strategies_help="Comma-separated strategy names to include.",
    )


def build_row(tool: str, strategy: str, project: str, df: pd.DataFrame) -> dict:
    row = {
        "project": project,
        "tool": tool,
        "strategy": strategy,
        "methods": len(df),
    }

    for change in CHANGE_COLUMNS:
        from_column = f"from_{change}"
        to_column = f"to_{change}"

        if tool == "codeShovel" and change in CODE_SHOVEL_UNSUPPORTED_CHANGE_SET:
            row[change] = 0
            continue

        if from_column not in df.columns or to_column not in df.columns:
            row[change] = 0
            continue

        pair_df = df[[from_column, to_column]].apply(pd.to_numeric, errors="coerce").dropna()
        row[change] = int((pair_df[from_column] > pair_df[to_column]).sum())

    return row


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        use_filters=args.use_filters,
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )

    input_root = Path(DATA_DIRECTORY) / "t2p-change"
    tools = select_named_items(
        util.sorted_directory_names(input_root),
        selected_tools,
        item_label="tool",
    )

    rows = []
    for tool in tools:
        strategies = select_named_items(
            util.sorted_directory_names(input_root / tool),
            selected_strategies,
            item_label="strategy",
        )
        for strategy in strategies:
            csv_files = list_csv_files(input_root / tool / strategy, selected_projects, strict=False)
            for csv_file in csv_files:
                df = pd.read_csv(csv_file, keep_default_na=False, na_filter=False)
                if df.empty:
                    continue

                rows.append(build_row(tool, strategy, csv_file.stem, df))

    output_columns = ["project", "tool", "strategy", "methods", *CHANGE_COLUMNS]
    output_df = pd.DataFrame(rows, columns=output_columns)
    if not output_df.empty:
        output_df = output_df.sort_values(["project", "tool", "strategy"]).reset_index(drop=True)
        for column in ["methods", *CHANGE_COLUMNS]:
            output_df[column] = output_df[column].astype("Int64")

    os.makedirs(OUTPUT_FILE.parent, exist_ok=True)
    output_df.to_csv(OUTPUT_FILE, index=False)


if __name__ == "__main__":
    main()
