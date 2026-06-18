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
    parse_name_list,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_min_t2p_links,
    resolve_revision_types,
    resolve_smell_detector,
    select_named_items,
    select_revision_columns,
)
from ptc.generator.t2p_test_smell_revision import (
    CHANGE_COLUMNS,
    OUTPUT_DIRECTORY_NAME,
    REVISION_GROUP_ORDER,
    normalize_revision_group,
    output_directory,
)
from ptc.generator.t2p_test_smell_loc_group import SIZE_GROUPS, loc_group, percentile_thresholds, valid_loc
from ptc.generator.run_stats import GenerationStats, should_generate, unlink_stale_output

ALL_SMELLS = "all"
ALL_LOC_GROUP = "ALL"
OUTPUT_FILE_NAME = "t2p-test-smell-prevalence.csv"
PREVALENCE_COLUMNS = [
    "strategy",
    "tool",
    "smell_detector",
    "change",
    "rg_group",
    "loc_group",
    "methods",
    "smell",
    "percent",
    "smell_total",
    "smell_n",
]


def build_parser():
    parser = build_experiment_parser(
        "Aggregate test-smell prevalence by linked revision group.",
        include_revision_types=True,
        include_smell_detector=True,
        include_replace=True,
        projects_help="Comma-separated project names to include. Defaults to ME_PROJECTS.",
        strategies_help="Comma-separated strategy names to include. Defaults to ME_STRATEGIES.",
        revision_types_help="Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
    )
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum generated linked test-production rows required before including a project. Defaults to ME_MIN_T2P_LINKS.",
    )
    return parser


def split_smells(value: str) -> list[str]:
    return [smell for smell in str(value).split() if smell]


def smell_type_order(frame: pd.DataFrame) -> list[str]:
    counts: dict[str, int] = {}
    for value in frame.get("smells", pd.Series(dtype=str)):
        for smell in split_smells(value):
            counts[smell] = counts.get(smell, 0) + 1
    return sorted(counts, key=lambda smell: (-counts[smell], smell))


def unique_method_frame(
    frame: pd.DataFrame,
    revision_type: str,
    revision_groups: list[str],
) -> pd.DataFrame:
    group_column = f"rg_{revision_type}"
    required_columns = {"from_url", "smells", group_column}
    if not required_columns.issubset(frame.columns):
        return pd.DataFrame(columns=[*frame.columns])

    selected = frame[frame[group_column].isin(revision_groups)].copy()
    if selected.empty:
        return selected

    group_counts = selected.groupby("from_url")[group_column].nunique()
    conflicting_urls = set(group_counts[group_counts > 1].index)
    selected = selected[~selected["from_url"].isin(conflicting_urls)].copy()
    if selected.empty:
        return selected

    def combined_smells(values: pd.Series) -> str:
        return " ".join(sorted({smell for value in values for smell in split_smells(value)}))

    aggregations = {
        column: "first"
        for column in selected.columns
        if column not in {"from_url", "smells"}
    }
    aggregations["smells"] = combined_smells
    return selected.groupby("from_url", as_index=False, sort=False).agg(aggregations)


def selected_revision_groups(value: str | list[str] | None = None) -> list[str]:
    selected = [normalize_revision_group(group) for group in (parse_name_list(value) or list(REVISION_GROUP_ORDER))]
    known_groups = set(REVISION_GROUP_ORDER)
    unknown = [group for group in selected if group not in known_groups]
    if unknown:
        raise ValueError(f"Unknown revision group(s): {', '.join(unknown)}")
    return selected


def percentage(count: int, total: int) -> float:
    return round(count / total * 100, 2) if total else 0.0


def rg_group_order(group: str) -> int:
    try:
        return REVISION_GROUP_ORDER.index(group)
    except ValueError:
        return len(REVISION_GROUP_ORDER)


def loc_group_order(group: str) -> int:
    all_groups = [ALL_LOC_GROUP, *SIZE_GROUPS]
    try:
        return all_groups.index(group)
    except ValueError:
        return len(all_groups)


def load_generated_frames(
    experiment_directory: Path,
    tool: str,
    strategy: str,
    smell_detector: str,
    selected_projects: list[str] | None,
    *,
    min_t2p_links: int,
) -> pd.DataFrame:
    input_dir = output_directory(experiment_directory, strategy, tool, smell_detector)
    csv_files = list_csv_files(input_dir, selected_projects, strict=False)
    frames = []
    for csv_file in csv_files:
        print(f"Processing: {csv_file.stem} [{tool}/{strategy}/{smell_detector}]")
        frame = pd.read_csv(csv_file, keep_default_na=False, na_filter=False)
        if len(frame) < min_t2p_links:
            warnings.warn(
                f"Skipping project={csv_file.stem}, tool={tool}, strategy={strategy}, "
                f"smell_detector={smell_detector}: "
                f"t2p_links={len(frame)} is below min_t2p_links={min_t2p_links}."
            )
            continue
        frames.append(frame)
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def prevalence_rows(
    frame: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    revision_type: str,
    revision_groups: list[str] | None = None,
    loc_groups: pd.DataFrame | None = None,
) -> list[dict]:
    revision_groups = revision_groups or list(REVISION_GROUP_ORDER)
    group_column = f"rg_{revision_type}"
    if group_column not in frame.columns:
        warnings.warn(f"Skipping revision type {revision_type}: missing generated column {group_column}.")
        return []
    if "from_url" not in frame.columns:
        warnings.warn(f"Skipping revision type {revision_type}: missing generated column from_url.")
        return []

    frame = unique_method_frame(frame, revision_type, revision_groups)
    if loc_groups is not None and not loc_groups.empty:
        frame = frame.merge(loc_groups[["from_url", "loc_group"]], on="from_url", how="left")
    elif "loc_group" not in frame.columns:
        frame["loc_group"] = ""
    smell_types = smell_type_order(frame)
    rows = []
    for revision_group in revision_groups:
        revision_df = frame[frame[group_column] == revision_group].copy()
        rows.extend(
            _prevalence_rows_for_group(
                revision_df,
                smell_types,
                strategy=strategy,
                tool=tool,
                smell_detector=smell_detector,
                revision_type=revision_type,
                revision_group=revision_group,
                loc_group=ALL_LOC_GROUP,
            )
        )
        for loc_group_value in SIZE_GROUPS:
            loc_df = revision_df[revision_df["loc_group"] == loc_group_value].copy()
            rows.extend(
                _prevalence_rows_for_group(
                    loc_df,
                    smell_types,
                    strategy=strategy,
                    tool=tool,
                    smell_detector=smell_detector,
                    revision_type=revision_type,
                    revision_group=revision_group,
                    loc_group=loc_group_value,
                )
            )
    return rows


def _prevalence_rows_for_group(
    group_df: pd.DataFrame,
    smell_types: list[str],
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    revision_type: str,
    revision_group: str,
    loc_group: str,
) -> list[dict]:
    rows = []
    methods = len(group_df)
    smell_total = len(group_df)
    smelly_mask = group_df.get("smells", pd.Series(dtype=str)).astype(bool)
    smelly_count = int(smelly_mask.sum())
    rows.append(
        {
            "strategy": strategy,
            "tool": tool,
            "smell_detector": smell_detector,
            "change": revision_type,
            "rg_group": revision_group,
            "loc_group": loc_group,
            "methods": methods,
            "smell": ALL_SMELLS,
            "percent": percentage(smelly_count, smell_total),
            "smell_total": smell_total,
            "smell_n": smelly_count,
        }
    )
    for smell in smell_types:
        smell_n = int(group_df.get("smells", pd.Series(dtype=str)).map(lambda value: smell in split_smells(value)).sum())
        rows.append(
            {
                "strategy": strategy,
                "tool": tool,
                "smell_detector": smell_detector,
                "change": revision_type,
                "rg_group": revision_group,
                "loc_group": loc_group,
                "methods": methods,
                "smell": smell,
                "percent": percentage(smell_n, smell_total),
                "smell_total": smell_total,
                "smell_n": smell_n,
            }
        )
    return rows


def loc_group_frame(smell_frames: list[pd.DataFrame]) -> pd.DataFrame:
    loc_by_url: dict[str, int] = {}
    for smell_df in smell_frames:
        if not {"url", "loc"}.issubset(smell_df.columns):
            continue
        for row in smell_df[["url", "loc"]].itertuples(index=False):
            url = str(row.url or "")
            if not url or url in loc_by_url:
                continue
            loc = valid_loc(row.loc)
            if loc is None:
                continue
            loc_by_url[url] = loc

    frame = pd.DataFrame(
        [{"from_url": url, "loc": loc} for url, loc in loc_by_url.items()],
        columns=["from_url", "loc"],
    )
    if frame.empty:
        return pd.DataFrame(columns=["from_url", "loc_group"])
    thresholds = percentile_thresholds(frame["loc"])
    frame["loc_group"] = frame["loc"].map(lambda loc: loc_group(int(loc), thresholds))
    return frame[["from_url", "loc_group"]]


def load_smell_frames(
    experiment_directory: Path,
    smell_detector: str,
    strategy: str,
    selected_projects: list[str] | None,
) -> list[pd.DataFrame]:
    input_dir = experiment_directory / "test-smell" / smell_detector / strategy
    csv_files = list_csv_files(input_dir, selected_projects, strict=False)
    frames = []
    for csv_file in csv_files:
        frame = pd.read_csv(csv_file, keep_default_na=False, na_filter=False)
        if not {"url", "loc"}.issubset(frame.columns):
            warnings.warn(f"Skipping {csv_file}: missing required column(s): url, loc.")
            continue
        frames.append(frame)
    return frames


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("t2p_test_smell_prevalence")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    output_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_types = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )

    generated_dir = experiment_directory / OUTPUT_DIRECTORY_NAME
    if not generated_dir.exists():
        unlink_stale_output(
            output_file,
            reason=f"Directory not found, skipping: {generated_dir}",
            stats=stats,
        )
        stats.print_summary()
        return
    if not should_generate(output_file, replace=args.replace, label=OUTPUT_FILE_NAME, stats=stats):
        stats.print_summary()
        return

    rows = []
    strategies = select_named_items(
        util.sorted_directory_names(generated_dir),
        selected_strategies,
        item_label="strategy",
    )
    for strategy in strategies:
        strategy_dir = generated_dir / strategy
        tools = select_named_items(util.sorted_directory_names(strategy_dir), selected_tools, item_label="tool")
        for tool in tools:
            detector_dir = strategy_dir / tool / smell_detector
            if not detector_dir.exists():
                warnings.warn(f"Directory not found, skipping: {detector_dir}")
                continue
            frame = load_generated_frames(
                experiment_directory,
                tool,
                strategy,
                smell_detector,
                selected_projects,
                min_t2p_links=args.min_t2p_links,
            )
            if frame.empty:
                continue
            loc_groups = loc_group_frame(
                load_smell_frames(experiment_directory, smell_detector, strategy, selected_projects)
            )
            for revision_type in revision_types:
                rows.extend(
                    prevalence_rows(
                        frame,
                        strategy=strategy,
                        tool=tool,
                        smell_detector=smell_detector,
                        revision_type=revision_type,
                        loc_groups=loc_groups,
                    )
                )

    os.makedirs(output_file.parent, exist_ok=True)
    output_df = pd.DataFrame(rows, columns=PREVALENCE_COLUMNS)
    if not output_df.empty:
        output_df["_rg_group_order"] = output_df["rg_group"].map(rg_group_order)
        output_df["_loc_group_order"] = output_df["loc_group"].map(loc_group_order)
        output_df = output_df.sort_values(
            ["strategy", "tool", "smell_detector", "change", "_rg_group_order", "_loc_group_order", "smell"]
        ).drop(columns=["_rg_group_order", "_loc_group_order"]).reset_index(drop=True)
    output_df.to_csv(output_file, index=False)
    if output_df.empty:
        stats.record_empty_output()
    stats.record_write(len(output_df))
    print(f"Wrote {output_file}")
    stats.print_summary()


if __name__ == "__main__":
    main()
