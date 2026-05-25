import warnings
import sys
from pathlib import Path

import pandas as pd

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    list_csv_files,
    non_negative_int,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_min_t2p_links,
    resolve_revision_types,
    select_named_items,
)


REVIEW_COLUMNS = [
    "project",
    "tool",
    "from_name",
    "to_name",
    "from_url",
    "to_url",
    "label",
    "tags",
    "notes",
]
DUPLICATE_KEY_COLUMNS = ["from_url", "to_url"]
DEFAULT_MIN_T2P_REVISION = 10


def normalize_argv(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None

    normalized_args: list[str] = []
    for arg in argv:
        if arg.startswith("-") or "=" not in arg:
            normalized_args.append(arg)
            continue

        for part in arg.split(","):
            if not part:
                continue
            if "=" not in part:
                normalized_args.append(part)
                continue
            key, value = part.split("=", 1)
            normalized_args.extend([f"--{key.strip()}", value.strip()])
    return normalized_args


def build_parser():
    parser = build_experiment_parser(
        "Sample linked test-production rows for revision review.",
        include_revision_types=True,
        projects_help="Comma-separated project names to process. Defaults to ME_PROJECTS.",
        revision_types_help="Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
    )
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum linked test-production pairs required before review CSVs are generated. Defaults to ME_MIN_T2P_LINKS.",
    )
    parser.add_argument(
        "--min-t2p-revision",
        dest="min_t2p_revision",
        type=non_negative_int,
        default=DEFAULT_MIN_T2P_REVISION,
        help=f"Minimum from/to revision delta required for review rows. Defaults to {DEFAULT_MIN_T2P_REVISION}.",
    )
    return parser


def _format_percent(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def _review_frame(frame: pd.DataFrame, project: str, tool: str = "") -> pd.DataFrame:
    review_df = frame.copy()
    if "project" not in review_df:
        review_df["project"] = project
    if "tool" not in review_df:
        review_df["tool"] = tool
    for column in REVIEW_COLUMNS:
        if column not in review_df:
            review_df[column] = ""
    review_df["label"] = ""
    review_df["tags"] = ""
    review_df["notes"] = ""
    return review_df[REVIEW_COLUMNS].copy()


def _existing_keys(output_file: Path) -> set[tuple[str, str]]:
    if not output_file.exists():
        return set()

    existing_df = pd.read_csv(output_file, keep_default_na=False, na_filter=False)
    if any(column not in existing_df for column in DUPLICATE_KEY_COLUMNS):
        warnings.warn(f"Existing review CSV is missing duplicate key columns, treating as empty: {output_file}")
        return set()

    return {
        (str(row.from_url), str(row.to_url))
        for row in existing_df[DUPLICATE_KEY_COLUMNS].itertuples(index=False)
    }


def _append_review_rows(output_file: Path, rows_to_add: pd.DataFrame) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        existing_df = pd.read_csv(output_file, keep_default_na=False, na_filter=False)
        for column in REVIEW_COLUMNS:
            if column not in existing_df:
                existing_df[column] = ""
        output_df = pd.concat([existing_df[REVIEW_COLUMNS], rows_to_add[REVIEW_COLUMNS]], ignore_index=True)
    else:
        output_df = rows_to_add[REVIEW_COLUMNS].copy()
    output_df.to_csv(output_file, index=False)


def qualifying_rows(
    project_df: pd.DataFrame,
    revision_types: list[str],
    *,
    min_t2p_revision: int,
    project: str,
    tool: str,
    strategy: str,
) -> pd.DataFrame:
    masks = []
    for revision_type in revision_types:
        from_column = f"from_{revision_type}"
        to_column = f"to_{revision_type}"
        if from_column not in project_df.columns or to_column not in project_df.columns:
            warnings.warn(
                "Skipping "
                f"project={project}, tool={tool}, strategy={strategy}, revision_type={revision_type}: "
                f"missing required columns {from_column!r} and/or {to_column!r}."
            )
            continue

        pair_df = project_df[[from_column, to_column]].apply(pd.to_numeric, errors="coerce")
        valid_mask = pair_df[from_column].notna() & pair_df[to_column].notna()
        if not valid_mask.any():
            warnings.warn(
                "Skipping "
                f"project={project}, tool={tool}, strategy={strategy}, revision_type={revision_type}: "
                "no valid numeric revision pairs."
            )
            continue

        masks.append(valid_mask & ((pair_df[from_column] - pair_df[to_column]) >= min_t2p_revision))

    if not masks:
        return project_df.iloc[0:0].copy()

    combined_mask = masks[0].copy()
    for mask in masks[1:]:
        combined_mask = combined_mask | mask
    return project_df.loc[combined_mask].copy()


def process_project_file(
    project_file: Path,
    *,
    output_directory: Path,
    revision_types: list[str],
    min_t2p_links: int,
    min_t2p_revision: int,
    tool: str,
    strategy: str,
) -> None:
    project = project_file.stem
    project_df = pd.read_csv(project_file, keep_default_na=False, na_filter=False)
    source_count = len(project_df)
    if source_count < min_t2p_links:
        warnings.warn(
            "Skipping "
            f"project={project}, tool={tool}, strategy={strategy}: "
            f"t2p_links={source_count} is below min_t2p_links={min_t2p_links}."
        )
        return

    matched_df = qualifying_rows(
        project_df,
        revision_types,
        min_t2p_revision=min_t2p_revision,
        project=project,
        tool=tool,
        strategy=strategy,
    )
    qualifying_count = len(matched_df)
    if qualifying_count == 0:
        return

    review_df = _review_frame(matched_df, project, tool=tool)
    output_file = output_directory / f"{project}.csv"
    existing_keys = _existing_keys(output_file)
    duplicate_mask = review_df[DUPLICATE_KEY_COLUMNS].apply(
        lambda row: (str(row["from_url"]), str(row["to_url"])) in existing_keys,
        axis=1,
    )
    new_rows = review_df.loc[~duplicate_mask].drop_duplicates(subset=DUPLICATE_KEY_COLUMNS, keep="first").copy()
    duplicate_count = qualifying_count - len(new_rows)

    if not new_rows.empty:
        _append_review_rows(output_file, new_rows)

    print(
        f"project={project}, tool={tool}, strategy={strategy}: "
        f"source={source_count}, qualifying={qualifying_count} ({_format_percent(qualifying_count, source_count)}), "
        f"added={len(new_rows)} ({_format_percent(len(new_rows), qualifying_count)} of qualifying), "
        f"skipped_duplicates={duplicate_count}"
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(normalize_argv(sys.argv[1:] if argv is None else argv))
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    revision_types = resolve_revision_types(args.revision_types) or []
    if not revision_types:
        warnings.warn("No revision types selected; nothing to sample.")
        return

    t2p_change_dir = experiment_directory / "t2p-change"
    if not t2p_change_dir.exists():
        warnings.warn(f"Directory not found, skipping: {t2p_change_dir}")
        return

    tools = select_named_items(util.sorted_directory_names(t2p_change_dir), selected_tools, item_label="tool")
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
            input_directory = t2p_change_dir / tool / strategy
            output_directory = experiment_directory / "t2p-revision-review" / tool / strategy
            project_files = list_csv_files(input_directory, selected_projects, strict=False)
            if not project_files:
                warnings.warn(f"No csv files found, skipping: {input_directory}")
                continue

            for project_file in project_files:
                process_project_file(
                    project_file,
                    output_directory=output_directory,
                    revision_types=revision_types,
                    min_t2p_links=args.min_t2p_links,
                    min_t2p_revision=args.min_t2p_revision,
                    tool=tool,
                    strategy=strategy,
                )


if __name__ == "__main__":
    main()
