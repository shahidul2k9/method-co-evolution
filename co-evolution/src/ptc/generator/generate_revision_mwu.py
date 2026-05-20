import os
import warnings

import pandas as pd

import mhc.util as util
from mhc.artifacts import is_main_code, is_test_code
from ptc.constants import ALL_REPOSITORY, MethodChangeType
from ptc.experiment_util import (
    build_experiment_parser,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)
from ptc.generator.generate_t2p_mwu import MIN_METHOD_PAIRS_FOR_MWU
from ptc.plot_util import man_utest

METHOD_KINDS = ["test-code", "main-code"]
CHANGE_COLUMNS = [
    "ch_all",
    "ch_diff",
    *[f"ch_{change_type.name.lower()}" for change_type in MethodChangeType],
]
SIZE_MARKER_COLUMNS = {
    "negligible": "N",
    "small": "S",
    "medium": "M",
    "large": "L",
}
STAT_COLUMNS = [
    "project",
    "tool",
    "change",
    "size",
    "main_size",
    "test_size",
    "mwu_u1",
    "mwu_u2",
    "mwu_p",
    "mwu_d",
    "mwu_size",
    "N",
    "S",
    "M",
    "L",
]


def classify_method_kind(artifact: str | None) -> str | None:
    if is_test_code(artifact):
        return "test-code"
    if is_main_code(artifact):
        return "main-code"
    return None


def order_change_columns(columns: list[str]) -> list[str]:
    preferred_columns = [column for column in CHANGE_COLUMNS if column in columns]
    extra_columns = [column for column in columns if column not in preferred_columns]
    return preferred_columns + extra_columns


def build_parser():
    return build_experiment_parser(
        "Aggregate Mann-Whitney U statistics for test-code and main-code method revisions.",
        include_strategies=False,
        projects_help="Comma-separated project names to process.",
    )


def build_stat_row(project: str, tool: str, change: str, project_df: pd.DataFrame) -> dict | None:
    main_change = pd.to_numeric(
        project_df[project_df["method_kind"] == "main-code"][change],
        errors="coerce",
    ).dropna()
    test_change = pd.to_numeric(
        project_df[project_df["method_kind"] == "test-code"][change],
        errors="coerce",
    ).dropna()
    if main_change.empty or test_change.empty:
        return None

    mwu_u1, mwu_p, mwu_d, mwu_size = man_utest(main_change, test_change)
    mwu_u2 = len(main_change) * len(test_change) - mwu_u1
    marker_values = {column: "" for column in SIZE_MARKER_COLUMNS.values()}
    marker_column = SIZE_MARKER_COLUMNS.get(mwu_size)
    if marker_column is not None:
        marker_values[marker_column] = "x"

    return {
        "project": project,
        "tool": tool,
        "change": change.replace("ch_", ""),
        "size": len(project_df),
        "main_size": len(main_change),
        "test_size": len(test_change),
        "mwu_u1": round(mwu_u1, 2),
        "mwu_u2": round(mwu_u2, 2),
        "mwu_p": round(mwu_p, 2),
        "mwu_d": round(mwu_d, 2),
        "mwu_size": mwu_size,
        **marker_values,
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    stats_rows = []

    selected_tools, selected_projects, _ = resolve_experiment_filters(
        use_filters=args.use_filters,
        tools=args.tools,
        projects=args.projects,
    )
    method_history_dir = experiment_directory / "method-history"
    if not method_history_dir.exists():
        warnings.warn(f"Directory not found, skipping: {method_history_dir}")
        return

    tools = select_named_items(
        util.sorted_directory_names(method_history_dir),
        selected_tools,
        item_label="tool",
    )
    for tool in tools:
        csv_files = list_csv_files(method_history_dir / tool, selected_projects, strict=False)
        history_repository_dfs = [
            pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False, low_memory=False)
            for repository_history_file in csv_files
        ]
        history_repository_dfs = [df for df in history_repository_dfs if not df.empty]
        if not history_repository_dfs:
            continue

        df = pd.concat(history_repository_dfs, ignore_index=True)
        df["method_kind"] = df["artifact"].map(classify_method_kind)
        df = df[df["method_kind"].isin(METHOD_KINDS)].copy()
        if df.empty:
            continue

        change_cols = order_change_columns([c for c in df.columns if c.startswith("ch_")])
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
                    "Skipping revision MWU statistics for "
                    f"project={project}, tool={tool}: "
                    f"size {project_size} is below minimum threshold {MIN_METHOD_PAIRS_FOR_MWU}."
                )
                continue

            for change in change_cols:
                stat_row = build_stat_row(project, tool, change, project_df)
                if stat_row is not None:
                    stats_rows.append(stat_row)

    stats_output_file = experiment_directory / "aggregate" / "revision_mwu.csv"
    os.makedirs(stats_output_file.parent, exist_ok=True)
    stats_df = pd.DataFrame(stats_rows, columns=STAT_COLUMNS)
    if not stats_df.empty:
        stats_df = stats_df.sort_values(["project", "tool", "change"]).reset_index(drop=True)
    stats_df.to_csv(stats_output_file, index=False)


if __name__ == "__main__":
    main()
