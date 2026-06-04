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
    output_directory,
)

ALL_SMELLS = "all"
OUTPUT_FILE_NAME = "t2p-test-smell-prevalence.csv"
PREVALENCE_COLUMNS = [
    "strategy",
    "tool",
    "smell_detector",
    "change",
    "revision_group",
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


def selected_revision_groups(value: str | list[str] | None = None) -> list[str]:
    selected = parse_name_list(value) or list(REVISION_GROUP_ORDER)
    known_groups = set(REVISION_GROUP_ORDER)
    unknown = [group for group in selected if group not in known_groups]
    if unknown:
        raise ValueError(f"Unknown revision group(s): {', '.join(unknown)}")
    return selected


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
) -> list[dict]:
    revision_groups = revision_groups or list(REVISION_GROUP_ORDER)
    group_column = f"rg_{revision_type}"
    if group_column not in frame.columns:
        warnings.warn(f"Skipping revision type {revision_type}: missing generated column {group_column}.")
        return []

    smell_types = smell_type_order(frame)
    rows = []
    for revision_group in revision_groups:
        group_df = frame[frame[group_column] == revision_group].copy()
        smell_total = len(group_df)
        smelly_mask = group_df.get("smells", pd.Series(dtype=str)).astype(bool)
        smelly_count = int(smelly_mask.sum())
        rows.append(
            {
                "strategy": strategy,
                "tool": tool,
                "smell_detector": smell_detector,
                "change": revision_type,
                "revision_group": revision_group,
                "smell": ALL_SMELLS,
                "percent": (smelly_count / smell_total * 100) if smell_total else 0.0,
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
                    "revision_group": revision_group,
                    "smell": smell,
                    "percent": (smell_n / smell_total * 100) if smell_total else 0.0,
                    "smell_total": smell_total,
                    "smell_n": smell_n,
                }
            )
    return rows


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
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_types = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )

    generated_dir = experiment_directory / OUTPUT_DIRECTORY_NAME
    if not generated_dir.exists():
        warnings.warn(f"Directory not found, skipping: {generated_dir}")
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
            for revision_type in revision_types:
                rows.extend(
                    prevalence_rows(
                        frame,
                        strategy=strategy,
                        tool=tool,
                        smell_detector=smell_detector,
                        revision_type=revision_type,
                    )
                )

    output_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    os.makedirs(output_file.parent, exist_ok=True)
    output_df = pd.DataFrame(rows, columns=PREVALENCE_COLUMNS)
    if not output_df.empty:
        output_df = output_df.sort_values(
            ["strategy", "tool", "smell_detector", "change", "revision_group", "smell"]
        ).reset_index(drop=True)
    output_df.to_csv(output_file, index=False)
    print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
