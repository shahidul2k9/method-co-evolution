from __future__ import annotations

import os
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
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
from ptc.generator.t2p_test_smell import (
    CHANGE_COLUMNS,
    OUTPUT_DIRECTORY_NAME,
    REVISION_GROUP_LABELS,
    REVISION_GROUP_ORDER,
    output_directory,
)
from ptc.plot_util import build_experiment_plot_parser

ALL_GROUPS = "All groups"
ALL_SMELLS = "All smells"
GROUP_STYLE_COLORS = {
    ALL_GROUPS: "white",
    "RP": "tab:orange",
    "RT": "tab:gray",
    "RRT": "tab:blue",
}
GROUP_STYLE_MARKERS = {
    ALL_GROUPS: "o",
    "RP": "s",
    "RT": "^",
    "RRT": "D",
}


def build_parser():
    parser = build_experiment_plot_parser(
        "Plot generated test smell revision groups.",
        include_revision_types=True,
        include_smell_detector=True,
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


def smell_composition(
    frame: pd.DataFrame,
    revision_type: str,
    revision_groups: list[str],
    smell_names: dict[str, str],
) -> pd.DataFrame:
    group_column = f"revision_group_{revision_type}"
    smell_types = smell_type_order(frame, smell_names)
    rows = []
    for group in revision_groups:
        group_df = frame[frame[group_column] == group]
        total_rows = len(group_df)
        smell_occurrences = [
            smell
            for value in group_df.get("smells", pd.Series(dtype=str))
            for smell in split_smells(value)
        ]
        occurrence_total = len(smell_occurrences)
        smelly_rows = int(group_df["smells"].astype(bool).sum()) if "smells" in group_df else 0
        rows.append(
            {
                "group": group,
                "smell": ALL_SMELLS,
                "smell_name": ALL_SMELLS,
                "percent": (smelly_rows / total_rows * 100) if total_rows else 0.0,
            }
        )
        for smell in smell_types:
            count = smell_occurrences.count(smell)
            rows.append(
                {
                    "group": group,
                    "smell": smell,
                    "smell_name": display_smell(smell, smell_names),
                    "percent": (count / occurrence_total * 100) if occurrence_total else 0.0,
                }
            )
    return pd.DataFrame(rows, columns=["group", "smell", "smell_name", "percent"])


def boxplot_values(
    frame: pd.DataFrame,
    revision_type: str,
    revision_groups: list[str],
    smell_names: dict[str, str],
) -> list[dict]:
    group_column = f"revision_group_{revision_type}"
    from_column = f"from_{revision_type}"
    smell_types = smell_type_order(frame, smell_names)
    rows = []
    for smell in smell_types:
        smell_mask = frame["smells"].map(lambda value: smell in split_smells(value))
        smell_df = frame[smell_mask].copy()
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


def plot_composition_axis(
    ax,
    composition_df: pd.DataFrame,
    revision_groups: list[str],
) -> None:
    if composition_df.empty:
        ax.text(0.5, 0.5, "No smell data", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return

    smell_names = list(dict.fromkeys(composition_df["smell_name"].tolist()))
    x = list(range(len(smell_names)))
    width = 0.8 / max(1, len(revision_groups))
    offsets = [
        (index - (len(revision_groups) - 1) / 2) * width
        for index in range(len(revision_groups))
    ]
    for index, group in enumerate(revision_groups):
        group_df = composition_df[composition_df["group"] == group].set_index("smell_name")
        values = [group_df["percent"].get(smell_name, 0.0) for smell_name in smell_names]
        positions = [value + offsets[index] for value in x]
        bars = ax.bar(
            positions,
            values,
            width=width,
            label=REVISION_GROUP_LABELS.get(group, group),
            color=GROUP_STYLE_COLORS.get(group, None),
            edgecolor="black",
        )
        for bar, percent in zip(bars, values):
            if percent <= 0:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{percent:.1f}%",
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=90,
            )

    ax.set_title("Smell composition by revision group")
    ax.set_ylabel("Percent")
    ax.set_xticks(x)
    ax.set_xticklabels(smell_names, rotation=45, ha="right")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(True, axis="y", alpha=0.25)


def _group_keys(revision_groups: list[str]) -> list[str]:
    return [ALL_GROUPS, *revision_groups]


def plot_boxplot_axis(ax, box_rows: list[dict], revision_groups: list[str]) -> None:
    plotted_rows = [row for row in box_rows if row["values"]]
    if not plotted_rows:
        ax.text(0.5, 0.5, "No revision values", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return

    smell_names = list(dict.fromkeys(row["smell_name"] for row in box_rows))
    group_keys = _group_keys(revision_groups)
    row_lookup = {
        (row["smell_name"], row["group"]): row["values"]
        for row in box_rows
        if row["values"]
    }
    positions = []
    values = []
    box_groups = []
    box_width = 0.12 if len(group_keys) > 3 else 0.16
    group_offsets = [
        (index - (len(group_keys) - 1) / 2) * (box_width * 1.35)
        for index in range(len(group_keys))
    ]
    for smell_index, smell_name in enumerate(smell_names, start=1):
        for group_index, group in enumerate(group_keys):
            group_values = row_lookup.get((smell_name, group))
            if not group_values:
                continue
            positions.append(smell_index + group_offsets[group_index])
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
        patch.set_facecolor(GROUP_STYLE_COLORS.get(group, "white"))
        patch.set_edgecolor("black")
    for median in boxplot["medians"]:
        median.set_color("black")

    ax.set_title("Test revisions by smell type")
    ax.set_ylabel("Test revisions")
    ax.set_xticks(range(1, len(smell_names) + 1))
    ax.set_xticklabels(smell_names, rotation=35, ha="right")
    legend_handles = [
        Line2D(
            [0],
            [0],
            marker=GROUP_STYLE_MARKERS.get(group, "o"),
            color="black",
            markerfacecolor=GROUP_STYLE_COLORS.get(group, "white"),
            linestyle="None",
            markersize=8,
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
) -> None:
    group_column = f"revision_group_{revision_type}"
    if group_column not in frame.columns or f"from_{revision_type}" not in frame.columns:
        warnings.warn(f"Skipping revision type {revision_type}: missing generated columns.")
        return

    plot_df = frame[frame[group_column].isin(revision_groups)].copy()
    if plot_df.empty:
        warnings.warn(f"Skipping revision type {revision_type}: no rows for selected revision groups.")
        return

    composition_df = smell_composition(plot_df, revision_type, revision_groups, smell_names)
    box_rows = boxplot_values(plot_df, revision_type, revision_groups, smell_names)
    fig, axes = plt.subplots(2, 1, figsize=(max(12, len(smell_type_order(plot_df, smell_names)) * 1.25), 10))
    plot_composition_axis(axes[0], composition_df, revision_groups)
    plot_boxplot_axis(axes[1], box_rows, revision_groups)
    fig.suptitle(f"Test smells with {revision_type} revision groups", fontsize=14)
    fig.tight_layout()
    os.makedirs(output_file.parent, exist_ok=True)
    fig.savefig(output_file, bbox_inches="tight")
    plt.close(fig)


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
                    experiment_directory
                    / "figure"
                    / f"t2p-test-smell--{tool}--{strategy}--{smell_detector}--{revision_type}.pdf"
                )
                plot_revision_type(frame, revision_type, revision_groups, smell_names, output_file)
                if output_file.exists():
                    plotted_any = True
                    print(f"Wrote {output_file}")

    if not plotted_any:
        print("No test smell revision plots generated.")


if __name__ == "__main__":
    main()
