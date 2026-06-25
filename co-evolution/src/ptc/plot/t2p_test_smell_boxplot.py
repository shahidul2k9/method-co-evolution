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
    normalize_revision_group,
    output_directory,
)
from ptc.generator.t2p_test_smell_loc_group import SIZE_GROUPS
from ptc.generator.t2p_test_smell_prevalence import (
    load_smell_frames,
    loc_group_frame,
    unique_method_frame,
)
from ptc.plot.method_history_runtime_table import resolve_path
from ptc.plot_util import build_experiment_plot_parser

ALL_GROUPS = "All groups"
GROUP_STYLE_COLORS = {
    ALL_GROUPS: "white",
    "NTR": "tab:orange",
    "ATR": "tab:gray",
    "HTR": "tab:blue",
}
GROUP_STYLE_HATCHES = {
    ALL_GROUPS: "",
    "NTR": "....",
    "ATR": "...",
    "HTR": "xx",
}
LOC_GROUP_HATCH = "\\\\\\\\"
LOC_GROUP_LABEL = "LOC group"
REVISION_GROUP_LABEL = "Revision group"


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
        help="Comma-separated revision groups to plot. Defaults to NTR,ATR,HTR.",
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
    selected = [normalize_revision_group(group) for group in (parse_name_list(value) or list(REVISION_GROUP_ORDER))]
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


def split_smells(value: str) -> list[str]:
    return [smell for smell in str(value).split() if smell]


def unique_smell_count(value: str) -> int:
    return len(set(split_smells(value)))


def extreme_point_count(values: list[int | float]) -> int:
    numeric = pd.to_numeric(pd.Series(values), errors="coerce").dropna()
    if numeric.empty:
        return 0
    q1 = numeric.quantile(0.25)
    q3 = numeric.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return int(((numeric < lower) | (numeric > upper)).sum())


def count_annotation(method_count: int, extreme_count: int) -> str:
    return f"n={method_count:,}\next={extreme_count:,}"


def revision_boxplot_values(
    frame: pd.DataFrame,
    revision_type: str,
    revision_groups: list[str],
) -> list[dict]:
    group_column = f"rg_{revision_type}"
    if group_column not in frame.columns or "from_url" not in frame.columns:
        return []

    frame = frame.copy()
    frame["unique_smell_count"] = frame["smells"].map(unique_smell_count)
    rows = []
    for group in revision_groups:
        group_df = frame[frame[group_column] == group]
        rows.append(
            {
                "category": group,
                "family": "revision",
                "style_key": group,
                "values": pd.to_numeric(group_df["unique_smell_count"], errors="coerce").dropna().tolist(),
            }
        )
    return rows


def unique_smell_count_frame(smell_frames: list[pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for smell_df in smell_frames:
        if not {"url", "smell"}.issubset(smell_df.columns):
            continue
        rows.append(smell_df[["url", "smell"]].copy())
    if not rows:
        return pd.DataFrame(columns=["from_url", "smells", "unique_smell_count"])

    frame = pd.concat(rows, ignore_index=True)
    frame["url"] = frame["url"].astype(str)
    frame = frame[frame["url"].astype(bool)].copy()
    if frame.empty:
        return pd.DataFrame(columns=["from_url", "smells", "unique_smell_count"])

    def combined_smells(values: pd.Series) -> str:
        return " ".join(sorted({str(smell) for smell in values if str(smell)}))

    output = frame.groupby("url", as_index=False, sort=False)["smell"].agg(combined_smells)
    output = output.rename(columns={"url": "from_url", "smell": "smells"})
    output["unique_smell_count"] = output["smells"].map(unique_smell_count)
    return output[["from_url", "smells", "unique_smell_count"]]


def loc_boxplot_values(smell_frames: list[pd.DataFrame]) -> list[dict]:
    loc_groups = loc_group_frame(smell_frames)
    smell_counts = unique_smell_count_frame(smell_frames)
    if loc_groups.empty or smell_counts.empty:
        return []

    plot_df = smell_counts.merge(loc_groups[["from_url", "loc_group"]], on="from_url", how="inner")
    plot_df = plot_df[plot_df["loc_group"].isin(SIZE_GROUPS)].copy()
    rows = []
    for loc_group in SIZE_GROUPS:
        group_df = plot_df[plot_df["loc_group"] == loc_group]
        rows.append(
            {
                "category": loc_group,
                "family": "loc",
                "style_key": "loc",
                "values": pd.to_numeric(group_df["unique_smell_count"], errors="coerce").dropna().tolist(),
            }
        )
    return rows


def boxplot_values(
    frame: pd.DataFrame,
    revision_type: str,
    revision_groups: list[str],
    *,
    smell_frames: list[pd.DataFrame],
) -> list[dict]:
    return [
        *revision_boxplot_values(frame, revision_type, revision_groups),
        *loc_boxplot_values(smell_frames),
    ]


def plot_boxplot_axis(
    ax,
    box_rows: list[dict],
    revision_groups: list[str],
) -> None:
    plotted_rows = [row for row in box_rows if row["values"]]
    if not plotted_rows:
        ax.text(0.5, 0.5, "No smell-count values", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return

    categories = [*revision_groups, *SIZE_GROUPS]
    positions_by_category = {
        category: index + 1 if index < len(revision_groups) else index + 2
        for index, category in enumerate(categories)
    }
    row_lookup = {row["category"]: row for row in box_rows if row["values"]}
    positions = []
    values = []
    style_keys = []
    for category in categories:
        row = row_lookup.get(category)
        if not row:
            continue
        positions.append(positions_by_category[category])
        values.append(row["values"])
        style_keys.append(row["style_key"])

    boxplot = ax.boxplot(
        values,
        positions=positions,
        widths=0.36,
        patch_artist=True,
        showfliers=False,
        boxprops={"linewidth": 1.15},
        whiskerprops={"linewidth": 1.05, "color": "black"},
        capprops={"linewidth": 1.05, "color": "black"},
        medianprops={"linewidth": 1.25, "color": "black"},
    )
    for patch, style_key in zip(boxplot["boxes"], style_keys):
        patch.set_facecolor("white")
        patch.set_edgecolor("black")
        patch.set_hatch(LOC_GROUP_HATCH if style_key == "loc" else GROUP_STYLE_HATCHES.get(style_key, ""))
    for median in boxplot["medians"]:
        median.set_color("black")

    annotation_y = 9.35
    for position, row in zip(positions, [row_lookup[category] for category in categories if category in row_lookup]):
        values_for_row = row["values"]
        ax.text(
            position,
            annotation_y,
            count_annotation(len(values_for_row), extreme_point_count(values_for_row)),
            ha="center",
            va="top",
            fontsize=8.5,
            linespacing=0.9,
        )

    ax.set_ylabel("# Unique Test Smells")
    ax.set_xticks([positions_by_category[category] for category in categories])
    ax.set_xticklabels(categories)
    ax.set_xlim(0.45, max(positions_by_category.values()) + 0.55)
    ax.set_ylim(bottom=-0.1, top=10)
    ax.set_yticks(range(0, 11))
    separator = (positions_by_category[revision_groups[-1]] + positions_by_category[SIZE_GROUPS[0]]) / 2
    ax.axvline(separator, color="black", linewidth=0.6, alpha=0.35)
    ax.grid(True, axis="y", alpha=0.25)


def plot_revision_type(
    frame: pd.DataFrame,
    revision_type: str,
    revision_groups: list[str],
    output_file: Path,
    *,
    smell_frames: list[pd.DataFrame],
    include_all_groups: bool = False,
) -> None:
    group_column = f"rg_{revision_type}"
    if group_column not in frame.columns:
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
        smell_frames=smell_frames,
    )
    if not any(row["values"] for row in box_rows):
        warnings.warn(f"Skipping revision type {revision_type}: no smell-count rows.")
        return

    fig, ax = plt.subplots(figsize=(6.6, 4.2))
    plot_boxplot_axis(
        ax,
        box_rows,
        revision_groups,
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
        smell_frames = load_smell_frames(
            experiment_directory,
            smell_detector,
            strategy,
            selected_projects,
        )
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
                    output_file,
                    smell_frames=smell_frames,
                    include_all_groups=args.include_all_groups,
                )
                if output_file.exists():
                    plotted_any = True
                    print(f"Wrote {output_file}")

    if not plotted_any:
        print("No test smell revision plots generated.")


if __name__ == "__main__":
    main()
