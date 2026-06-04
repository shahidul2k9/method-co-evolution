from __future__ import annotations

import os
import warnings
from pathlib import Path

import pandas as pd

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    list_csv_files,
    non_negative_int,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_revision_types,
    resolve_smell_detector,
    select_named_items,
    select_revision_columns,
)
from ptc.constants import MethodChangeType

CHANGE_COLUMNS = [
    "ch_all",
    "ch_diff",
    *[f"ch_{change_type.name.lower()}" for change_type in MethodChangeType],
]

DEFAULT_MIN_T2P_REVISION = 10
OUTPUT_DIRECTORY_NAME = "t2p-test-smell-with-revision"

REVISION_GROUP_1 = "RP"
REVISION_GROUP_2 = "RT"
REVISION_GROUP_3 = "RRT"
REVISION_GROUP_ORDER = [REVISION_GROUP_1, REVISION_GROUP_2, REVISION_GROUP_3]
REVISION_GROUP_LABELS = {
    REVISION_GROUP_1: "Revision-Prone Production (RP)",
    REVISION_GROUP_2: "Revision-Prone Test (RT)",
    REVISION_GROUP_3: "Recurrent Revision-Prone Test (RRT)",
}


def build_parser():
    parser = build_experiment_parser(
        "Generate linked test smell rows with test-production revision groups.",
        include_revision_types=True,
        include_smell_detector=True,
        projects_help="Comma-separated project names to process. Defaults to ME_PROJECTS.",
        strategies_help="Comma-separated strategy names to process. Defaults to ME_STRATEGIES.",
        revision_types_help="Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
    )
    parser.add_argument(
        "--min-t2p-revision",
        dest="min_t2p_revision",
        type=non_negative_int,
        default=DEFAULT_MIN_T2P_REVISION,
        help=f"Minimum test-production revision delta for {REVISION_GROUP_3}. Defaults to {DEFAULT_MIN_T2P_REVISION}.",
    )
    return parser


def assign_revision_group(
    test_revision: int | float,
    production_revision: int | float,
    *,
    min_t2p_revision: int = DEFAULT_MIN_T2P_REVISION,
) -> str:
    revision_delta = test_revision - production_revision
    if test_revision < production_revision:
        return REVISION_GROUP_1
    if revision_delta >= min_t2p_revision:
        return REVISION_GROUP_3
    return REVISION_GROUP_2


def smell_summary(smell_df: pd.DataFrame) -> pd.DataFrame:
    if smell_df.empty:
        return pd.DataFrame(columns=["from_url", "smells"])

    if "url" not in smell_df.columns or "smell" not in smell_df.columns:
        raise ValueError("Test smell CSV must include 'url' and 'smell' columns.")

    rows = []
    for url, group in smell_df.groupby("url", sort=False):
        smells = sorted({str(smell) for smell in group["smell"].dropna() if str(smell)})
        rows.append({"from_url": url, "smells": " ".join(smells)})
    return pd.DataFrame(rows, columns=["from_url", "smells"])


def read_smell_file(experiment_directory: Path, smell_detector: str, project: str) -> pd.DataFrame:
    smell_file = experiment_directory / "test-smell" / smell_detector / f"{project}.csv"
    if not smell_file.exists():
        raise FileNotFoundError(f"Test smell CSV not found: {smell_file}")
    return pd.read_csv(smell_file, keep_default_na=False, na_filter=False)


def selected_complete_revision_types(project_df: pd.DataFrame, revision_types: list[str]) -> list[str]:
    return [
        revision_type
        for revision_type in revision_types
        if f"from_{revision_type}" in project_df.columns and f"to_{revision_type}" in project_df.columns
    ]


def build_project_frame(
    project_df: pd.DataFrame,
    smell_df: pd.DataFrame,
    revision_types: list[str],
    *,
    project: str,
    min_t2p_revision: int,
) -> pd.DataFrame:
    complete_revision_types = selected_complete_revision_types(project_df, revision_types)
    output_columns = [
        "project",
        "from_url",
        "to_url",
        *[
            prefixed_column
            for revision_type in complete_revision_types
            for prefixed_column in (f"from_{revision_type}", f"to_{revision_type}")
        ],
        "smells",
        *[f"rg_{revision_type}" for revision_type in complete_revision_types],
    ]
    if not complete_revision_types:
        return pd.DataFrame(columns=output_columns)

    missing_base_columns = [column for column in ["from_url", "to_url"] if column not in project_df.columns]
    if missing_base_columns:
        raise ValueError(f"Missing required column(s): {', '.join(missing_base_columns)}")

    output_df = project_df.copy()
    output_df["project"] = project
    output_df = output_df.merge(smell_summary(smell_df), on="from_url", how="left")
    output_df["smells"] = output_df["smells"].fillna("")

    for revision_type in complete_revision_types:
        from_column = f"from_{revision_type}"
        to_column = f"to_{revision_type}"
        group_column = f"rg_{revision_type}"
        pair_df = output_df[[from_column, to_column]].apply(pd.to_numeric, errors="coerce")
        valid_mask = pair_df[from_column].notna() & pair_df[to_column].notna()
        output_df[group_column] = ""
        output_df.loc[valid_mask, group_column] = [
            assign_revision_group(
                test_revision,
                production_revision,
                min_t2p_revision=min_t2p_revision,
            )
            for test_revision, production_revision in zip(
                pair_df.loc[valid_mask, from_column],
                pair_df.loc[valid_mask, to_column],
            )
        ]

    return output_df[output_columns].copy()


def output_directory(experiment_directory: Path, strategy: str, tool: str, smell_detector: str) -> Path:
    return experiment_directory / OUTPUT_DIRECTORY_NAME / strategy / tool / smell_detector


def unlink_stale_output(output_file: Path, reason: str) -> None:
    if output_file.exists():
        output_file.unlink()
        warnings.warn(f"{reason}; deleted stale output: {output_file}")
    else:
        warnings.warn(f"{reason}; no stale output found: {output_file}")


def process_strategy(
    project_files: list[Path],
    *,
    experiment_directory: Path,
    output_dir: Path,
    tool: str,
    strategy: str,
    smell_detector: str,
    revision_types: list[str],
    min_t2p_revision: int,
) -> None:
    for project_file in project_files:
        project = project_file.stem
        output_file = output_dir / f"{project}.csv"
        project_df = pd.read_csv(project_file, keep_default_na=False, na_filter=False)
        try:
            smell_df = read_smell_file(experiment_directory, smell_detector, project)
        except FileNotFoundError as exc:
            unlink_stale_output(
                output_file,
                f"Skipping project={project}, tool={tool}, strategy={strategy}, "
                f"smell_detector={smell_detector}: {exc}",
            )
            continue

        missing_base_columns = [column for column in ["from_url", "to_url"] if column not in project_df.columns]
        if missing_base_columns:
            unlink_stale_output(
                output_file,
                f"Skipping project={project}, tool={tool}, strategy={strategy}: "
                f"missing required column(s): {', '.join(missing_base_columns)}",
            )
            continue

        missing_revision_types = [
            revision_type
            for revision_type in revision_types
            if f"from_{revision_type}" not in project_df.columns or f"to_{revision_type}" not in project_df.columns
        ]
        if missing_revision_types:
            warnings.warn(
                f"Skipping missing revision type(s) for project={project}, tool={tool}, strategy={strategy}: "
                f"{', '.join(missing_revision_types)}."
            )
        complete_revision_types = selected_complete_revision_types(project_df, revision_types)
        if not complete_revision_types:
            unlink_stale_output(
                output_file,
                f"Skipping project={project}, tool={tool}, strategy={strategy}: "
                "no selected revision types have both from/to columns",
            )
            continue

        try:
            output_df = build_project_frame(
                project_df,
                smell_df,
                complete_revision_types,
                project=project,
                min_t2p_revision=min_t2p_revision,
            )
        except ValueError as exc:
            unlink_stale_output(
                output_file,
                f"Skipping project={project}, tool={tool}, strategy={strategy}: {exc}",
            )
            continue
        if output_df.empty:
            unlink_stale_output(
                output_file,
                f"Skipping project={project}, tool={tool}, strategy={strategy}: generated frame is empty",
            )
            continue

        os.makedirs(output_file.parent, exist_ok=True)
        output_df.to_csv(output_file, index=False)
        print(
            f"project={project}, tool={tool}, strategy={strategy}, smell_detector={smell_detector}: "
            f"rows={len(output_df)}, revisions={','.join(complete_revision_types)}"
        )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    selected_revision_types = resolve_revision_types(args.revision_types) or []
    selected_revision_types = select_revision_columns(
        CHANGE_COLUMNS,
        selected_revision_types,
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )
    if not selected_revision_types:
        warnings.warn("No revision types selected; nothing to generate.")
        return

    smell_detector = resolve_smell_detector(args.smell_detector)
    t2p_change_dir = experiment_directory / "t2p-change"
    if not t2p_change_dir.exists():
        warnings.warn(f"Directory not found, skipping: {t2p_change_dir}")
        return

    tools = select_named_items(util.sorted_directory_names(t2p_change_dir), selected_tools, item_label="tool")
    for tool in tools:
        tool_dir = t2p_change_dir / tool
        strategies = select_named_items(
            util.sorted_directory_names(tool_dir),
            selected_strategies,
            item_label="strategy",
        )
        for strategy in strategies:
            input_dir = tool_dir / strategy
            project_files = list_csv_files(input_dir, selected_projects, strict=False)
            if not project_files:
                warnings.warn(f"No csv files found, skipping: {input_dir}")
                continue
            process_strategy(
                project_files,
                experiment_directory=experiment_directory,
                output_dir=output_directory(experiment_directory, strategy, tool, smell_detector),
                tool=tool,
                strategy=strategy,
                smell_detector=smell_detector,
                revision_types=selected_revision_types,
                min_t2p_revision=args.min_t2p_revision,
            )


if __name__ == "__main__":
    main()
