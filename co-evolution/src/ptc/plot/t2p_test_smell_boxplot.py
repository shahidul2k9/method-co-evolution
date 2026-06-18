from __future__ import annotations

import os
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import pandas as pd

import mhc.util as util
from mhc.command_util import (
    list_csv_files,
    load_test_smell_names,
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
    REVISION_GROUP_LABELS,
    REVISION_GROUP_ORDER,
    output_directory,
)
from ptc.generator.t2p_test_smell_prevalence import unique_method_frame
from ptc.plot.method_history_runtime_table import resolve_path
from ptc.plot_util import build_experiment_plot_parser

ALL_GROUPS = "All groups"
GROUP_STYLE_COLORS = {
    ALL_GROUPS: "white",
    "RP": "tab:orange",
    "RT": "tab:gray",
    "RRT": "tab:blue",
}
GROUP_STYLE_HATCHES = {
    ALL_GROUPS: "",
    "RP": "....",
    "RT": "...",
    "RRT": "xx",
}


def build_parser():
    parser = build_experiment_plot_parser(
        "Plot generated test smell revision groups.",
        include_revision_types=True,
        include_smell_detector=True,
        include_project_directory=True,
        include_output_directory=True,
    )
    parser.add_argument(
        "--revision-groups",
        dest="revision_groups",
        type=str,
        default=",".join(REVISION_GROUP_ORDER),
        help="Comma-separated revision groups to plot. Defaults to RP,RT,RRT.",
    )
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum generated linked test-production rows required before plots include a project. Defaults to ME_MIN_T2P_LINKS.",
    )
    parser.add_argument(
        "--include-all-groups",
        dest="include_all_groups",
        action="store_true",
        help="Include an additional box summarizing all selected revision groups for each smell.",
    )
    return parser


def selected_revision_groups(value: str | list[str] | None) -> list[str]:
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


def display_smell(acronym: str, smell_names: dict[str, str]) -> str:
    return smell_names.get(acronym, acronym)


def split_smells(value: str) -> list[str]:
    return [smell for smell in str(value).split() if smell]


def smell_type_order(frame: pd.DataFrame, smell_names: dict[str, str]) -> list[str]:
    counts: dict[str, int] = {}
    for value in frame.get("smells", pd.Series(dtype=str)):
        for smell in split_smells(value):
            counts[smell] = counts.get(smell, 0) + 1
    return sorted(counts, key=lambda smell: (-counts[smell], display_smell(smell, smell_names)))


def boxplot_values(
    frame: pd.DataFrame,
    revision_type: str,
    revision_groups: list[str],
    smell_names: dict[str, str],
    *,
    include_all_groups: bool = False,
) -> list[dict]:
    group_column = f"rg_{revision_type}"
    from_column = f"from_{revision_type}"
    smell_types = smell_type_order(frame, smell_names)
    rows = []
    for smell in smell_types:
        smell_mask = frame["smells"].map(lambda value: smell in split_smells(value))
        smell_df = frame[smell_mask].copy()
        if include_all_groups:
            rows.append(
                {
                    "smell": smell,
                    "smell_name": display_smell(smell, smell_names),
                    "group": ALL_GROUPS,
                    "values": pd.to_numeric(smell_df[from_column], errors="coerce").dropna().tolist(),
                }
            )
        for group in revision_groups:
            group_df = smell_df[smell_df[group_column] == group]
            rows.append(
                {
                    "smell": smell,
                    "smell_name": display_smell(smell, smell_names),
                    "group": group,
                    "values": pd.to_numeric(group_df[from_column], errors="coerce").dropna().tolist(),
                }
            )
    return rows


def _group_keys(revision_groups: list[str], *, include_all_groups: bool = False) -> list[str]:
    return [ALL_GROUPS, *revision_groups] if include_all_groups else list(revision_groups)


def plot_boxplot_axis(
    ax,
    box_rows: list[dict],
    revision_groups: list[str],
    *,
    include_all_groups: bool = False,
) -> None:
    plotted_rows = [row for row in box_rows if row["values"]]
    if not plotted_rows:
        ax.text(0.5, 0.5, "No revision values", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return

    smell_names = list(dict.fromkeys(row["smell_name"] for row in box_rows))
    group_keys = _group_keys(revision_groups, include_all_groups=include_all_groups)
    row_lookup = {
        (row["smell_name"], row["group"]): row["values"]
        for row in box_rows
        if row["values"]
    }
    positions = []
    values = []
    box_groups = []
    box_width = 0.18 if len(group_keys) > 3 else 0.26
    smell_spacing = 0.78
    group_offsets = [
        (index - (len(group_keys) - 1) / 2) * (box_width * 1.15)
        for index in range(len(group_keys))
    ]
    for smell_index, smell_name in enumerate(smell_names, start=1):
        smell_position = smell_index * smell_spacing
        for group_index, group in enumerate(group_keys):
            group_values = row_lookup.get((smell_name, group))
            if not group_values:
                continue
            positions.append(smell_position + group_offsets[group_index])
            values.append(group_values)
            box_groups.append(group)

    boxplot = ax.boxplot(
        values,
        positions=positions,
        widths=box_width,
        patch_artist=True,
        showfliers=False,
    )
    for patch, group in zip(boxplot["boxes"], box_groups):
        patch.set_facecolor("white")
        patch.set_edgecolor("black")
        patch.set_hatch(GROUP_STYLE_HATCHES.get(group, ""))
    for median in boxplot["medians"]:
        median.set_color("black")

    ax.set_ylabel("# Test Method Revisions")
    ax.set_xticks([index * smell_spacing for index in range(1, len(smell_names) + 1)])
    ax.set_xticklabels(smell_names, rotation=40, ha="right", fontsize=8)
    ax.set_xlim(smell_spacing * 0.35, smell_spacing * (len(smell_names) + 0.65))
    legend_handles = [
        Patch(
            facecolor="white",
            edgecolor="black",
            hatch=GROUP_STYLE_HATCHES.get(group, ""),
            label=REVISION_GROUP_LABELS.get(group, group),
        )
        for group in group_keys
    ]
    ax.legend(handles=legend_handles, frameon=False, fontsize=9)
    ax.grid(True, axis="y", alpha=0.25)


def plot_revision_type(
    frame: pd.DataFrame,
    revision_type: str,
    revision_groups: list[str],
    smell_names: dict[str, str],
    output_file: Path,
    *,
    include_all_groups: bool = False,
) -> None:
    group_column = f"rg_{revision_type}"
    if group_column not in frame.columns or f"from_{revision_type}" not in frame.columns:
        warnings.warn(f"Skipping revision type {revision_type}: missing generated columns.")
        return

    plot_df = unique_method_frame(frame, revision_type, revision_groups)
    if plot_df.empty:
        warnings.warn(f"Skipping revision type {revision_type}: no rows for selected revision groups.")
        return

    box_rows = boxplot_values(
        plot_df,
        revision_type,
        revision_groups,
        smell_names,
        include_all_groups=include_all_groups,
    )
    fig, ax = plt.subplots(figsize=(max(10, len(smell_type_order(plot_df, smell_names)) * 0.72), 4.8))
    plot_boxplot_axis(
        ax,
        box_rows,
        revision_groups,
        include_all_groups=include_all_groups,
    )
    fig.tight_layout()
    os.makedirs(output_file.parent, exist_ok=True)
    fig.savefig(output_file, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    project_directory = Path(args.project_directory)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    figure_directory = (
        resolve_path(project_directory, args.output_directory, Path())
        if args.output_directory is not None
        else experiment_directory / "figure"
    )
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_groups = selected_revision_groups(args.revision_groups)
    revision_types = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )
    smell_names = load_test_smell_names(smell_detector)

    generated_dir = experiment_directory / OUTPUT_DIRECTORY_NAME
    if not generated_dir.exists():
        warnings.warn(f"Directory not found, skipping: {generated_dir}")
        return

    strategies = select_named_items(
        util.sorted_directory_names(generated_dir),
        selected_strategies,
        item_label="strategy",
    )
    plotted_any = False
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
                output_file = (
                    figure_directory
                    / f"t2p-test-smell-boxplot--{tool}--{strategy}--{smell_detector}--{revision_type}.pdf"
                )
                plot_revision_type(
                    frame,
                    revision_type,
                    revision_groups,
                    smell_names,
                    output_file,
                    include_all_groups=args.include_all_groups,
                )
                if output_file.exists():
                    plotted_any = True
                    print(f"Wrote {output_file}")

    if not plotted_any:
        print("No test smell revision plots generated.")


if __name__ == "__main__":
    main()
