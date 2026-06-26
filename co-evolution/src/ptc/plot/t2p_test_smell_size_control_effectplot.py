from __future__ import annotations

import math
import os
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator
import pandas as pd

from mhc.command_util import (
    load_test_smell_names,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_revision_types,
    resolve_smell_detector,
    select_revision_columns,
)
from ptc.generator.t2p_test_smell_size_control_association import (
    COMBINED_ROBUST_SMELLS,
    CONTROL_SIZE_GROUPS,
    OUTPUT_FILE_NAME,
)
from ptc.generator.t2p_test_smell_association import selected_revision_group_pairs
from ptc.generator.t2p_test_smell_revision import CHANGE_COLUMNS
from ptc.plot.method_history_runtime_table import resolve_path
from ptc.plot.t2p_test_smell_barchart import (
    EFFECT_LEGEND_FONTSIZE,
    EFFECT_X_AXIS_LABEL,
    EFFECT_XTICK_FONTSIZE,
    EFFECT_YTICK_FONTSIZE,
    comparison_label,
    comparison_pair,
    comparison_pairs,
    comparison_style,
    draw_horizontal_ci,
)
from ptc.plot_util import build_experiment_plot_parser

OUTPUT_FILE_PREFIX = "t2p-test-smell-size-control-effectplot"
SIZE_CONTROL_XTICK_FONTSIZE = EFFECT_XTICK_FONTSIZE + 2
SIZE_CONTROL_AXIS_LABEL_FONTSIZE = EFFECT_XTICK_FONTSIZE + 1
SIZE_CONTROL_CI_LINEWIDTH = 2.6
SIZE_CONTROL_CI_CAP_LINEWIDTH = 2.0
SIZE_CONTROL_CI_CAP_HALF_HEIGHT = 0.07
SIZE_CONTROL_MARKER_SIZE = 58
METHOD_SIZE_LABEL = "Method Size"
SIZE_CONTROL_SERIES_STEP = 0.16
SIZE_CONTROL_ROW_HEIGHT = 0.72
SIZE_CONTROL_MIN_FIGURE_HEIGHT = 3.4


def build_parser():
    parser = build_experiment_plot_parser(
        "Render the LOC-controlled RQ4 top-smell effect plot.",
        include_projects=False,
        include_revision_types=True,
        include_smell_detector=True,
        include_project_directory=True,
        include_output_directory=True,
    )
    parser.add_argument(
        "--revision-group-pair",
        default="HTR,NTR",
        help=(
            "Focal,baseline revision-group pair(s) to render. "
            "Use semicolons for multiple pairs, for example HTR,NTR;MTR,NTR;ATR,NTR. "
            "Defaults to HTR,NTR."
        ),
    )
    return parser


def selected_revision_group_pair(value: str) -> tuple[str, str]:
    pairs = selected_revision_group_pair_list(value)
    if len(pairs) != 1:
        raise ValueError("--revision-group-pair must contain exactly one focal,baseline pair.")
    return pairs[0]


def selected_revision_group_pair_list(value: str) -> list[tuple[str, str]]:
    pairs = selected_revision_group_pairs(value)
    if not pairs:
        raise ValueError("--revision-group-pair must include at least one focal,baseline pair.")
    return pairs


def pair_suffix(focal_group: str, baseline_group: str) -> str:
    if (focal_group, baseline_group) == ("HTR", "NTR"):
        return ""
    return f"--{focal_group}-{baseline_group}"


def pairs_suffix(pairs: list[tuple[str, str]]) -> str:
    if pairs == [("HTR", "NTR")]:
        return ""
    return "--" + "-".join(f"{focal}-{baseline}" for focal, baseline in pairs)


def control_group_order(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    available = set(frame["control_group"].dropna().astype(str))
    return [group for group in CONTROL_SIZE_GROUPS if group in available]


def axis_limits(frame: pd.DataFrame) -> tuple[int, int]:
    values = pd.to_numeric(
        pd.concat([frame["difference_ci_low"], frame["difference_ci_high"]], ignore_index=True),
        errors="coerce",
    ).dropna()
    if values.empty:
        return -2, 18
    low = min(-2, int(math.floor(values.min() / 2.0) * 2))
    high = max(18, int(math.ceil(values.max() / 2.0) * 2))
    return low, high


def smell_order(frame: pd.DataFrame) -> list[str]:
    if frame.empty:
        return []
    ordered = frame[["smell", "smell_rank"]].drop_duplicates().copy()
    ordered["smell_rank"] = pd.to_numeric(ordered["smell_rank"], errors="coerce")
    return ordered.sort_values(["smell_rank", "smell"])["smell"].astype(str).tolist()


def series_order(frame: pd.DataFrame) -> list[tuple[str, tuple[str, str]]]:
    pairs = legend_pairs(frame)
    return [(control_group, pair) for control_group in CONTROL_SIZE_GROUPS for pair in pairs]


def series_label(series: tuple[str, tuple[str, str]]) -> str:
    _, pair = series
    return comparison_label(pair)


def series_style(series: tuple[str, tuple[str, str]]) -> dict[str, str]:
    _, pair = series
    return comparison_style(pair).copy()


def legend_pairs(frame: pd.DataFrame) -> list[tuple[str, str]]:
    pairs = comparison_pairs(frame)
    requested = frame.attrs.get("revision_group_pairs")
    if requested:
        requested = [pair for pair in requested if pair in pairs]
        remaining = [pair for pair in pairs if pair not in requested]
        return [*requested, *remaining]
    return pairs


def plot_combined_axis(
    ax,
    plot_df: pd.DataFrame,
    *,
    control_groups: list[str],
    x_limits: tuple[int, int],
) -> None:
    if plot_df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        return

    series = series_order(plot_df)
    pairs = comparison_pairs(plot_df)
    pair_offsets = {pair: 0.0 for pair in pairs}
    if len(pairs) > 1:
        pair_offsets = {
            pair: (index - (len(pairs) - 1) / 2) * SIZE_CONTROL_SERIES_STEP
            for index, pair in enumerate(pairs)
        }

    plot_df = plot_df.copy()
    plot_df["_pair"] = plot_df.apply(comparison_pair, axis=1)
    y_by_control_group = {control_group: index for index, control_group in enumerate(control_groups)}
    for series_item in series:
        control_group, pair = series_item
        style = series_style(series_item)
        series_df = plot_df[(plot_df["_pair"] == pair) & (plot_df["control_group"] == control_group)].set_index("smell")
        if COMBINED_ROBUST_SMELLS not in series_df.index or control_group not in y_by_control_group:
            continue
        row = series_df.loc[COMBINED_ROBUST_SMELLS]
        y_position = y_by_control_group[control_group] + pair_offsets[pair]
        difference = float(row["difference_pp"])
        draw_horizontal_ci(
            ax,
            y_position,
            float(row["difference_ci_low"]),
            float(row["difference_ci_high"]),
            color=str(style["color"]),
            linestyle=str(style["linestyle"]),
            linewidth=SIZE_CONTROL_CI_LINEWIDTH,
            cap_linewidth=SIZE_CONTROL_CI_CAP_LINEWIDTH,
            cap_half_height=SIZE_CONTROL_CI_CAP_HALF_HEIGHT,
        )
        ax.scatter(
            [difference],
            [y_position],
            marker=str(style["marker"]),
            facecolor=str(style["color"]) if str(row["significant"]) == "x" else "white",
            edgecolor="black",
            linewidth=1.0,
            s=SIZE_CONTROL_MARKER_SIZE,
            zorder=2,
        )

    ax.axvline(0, color="black", linewidth=0.9, linestyle="--")
    ax.set_yticks(list(range(len(control_groups))))
    ax.set_yticklabels(control_groups, fontsize=EFFECT_YTICK_FONTSIZE)
    ax.set_ylabel(METHOD_SIZE_LABEL, fontsize=SIZE_CONTROL_AXIS_LABEL_FONTSIZE)
    ax.invert_yaxis()
    ax.set_ylim(len(control_groups) - 0.5, -0.5)
    ax.set_xlim(*x_limits)
    ax.set_xticks(list(range(x_limits[0], x_limits[1] + 1, 2)))
    ax.xaxis.set_minor_locator(MultipleLocator(1))
    ax.tick_params(axis="x", labelsize=SIZE_CONTROL_XTICK_FONTSIZE)
    ax.grid(True, axis="x", which="major", alpha=0.3)
    ax.grid(True, axis="x", which="minor", alpha=0.18)


def plot_size_control_effect(
    frame: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    change: str,
    smell_names: dict[str, str],
    revision_group_pairs: list[tuple[str, str]] | None = None,
    output_file: Path,
) -> None:
    revision_group_pairs = revision_group_pairs or [("HTR", "NTR")]
    pair_set = set(revision_group_pairs)
    plot_df = frame[
        (frame["strategy"] == strategy)
        & (frame["tool"] == tool)
        & (frame["smell_detector"] == smell_detector)
        & (frame["change"] == change)
        & (frame["smell"] == COMBINED_ROBUST_SMELLS)
    ].copy()
    if not plot_df.empty:
        plot_df["_pair"] = plot_df.apply(comparison_pair, axis=1)
        plot_df = plot_df[plot_df["_pair"].isin(pair_set)].drop(columns=["_pair"])
        plot_df.attrs["revision_group_pairs"] = revision_group_pairs
    if plot_df.empty:
        return

    control_groups = control_group_order(plot_df)
    x_limits = axis_limits(plot_df)
    fig, ax = plt.subplots(
        figsize=(10.5, max(SIZE_CONTROL_MIN_FIGURE_HEIGHT, len(control_groups) * SIZE_CONTROL_ROW_HEIGHT))
    )
    plot_combined_axis(ax, plot_df, control_groups=control_groups, x_limits=x_limits)

    pairs = legend_pairs(plot_df)
    handles = [
        Line2D(
            [0],
            [0],
            marker=str(comparison_style(pair)["marker"]),
            markerfacecolor=str(comparison_style(pair)["color"]),
            markeredgecolor="black",
            color=str(comparison_style(pair)["color"]),
            linestyle=str(comparison_style(pair)["linestyle"]),
            label=comparison_label(pair),
        )
        for pair in pairs
    ]
    fig.legend(handles=handles, frameon=False, fontsize=EFFECT_LEGEND_FONTSIZE, loc="upper center", ncol=2)
    fig.supxlabel(EFFECT_X_AXIS_LABEL, fontsize=SIZE_CONTROL_AXIS_LABEL_FONTSIZE)
    fig.tight_layout(rect=(0, 0, 1, 0.88))
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
    output_directory = (
        resolve_path(project_directory, args.output_directory, Path())
        if args.output_directory is not None
        else experiment_directory / "figure"
    )
    input_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    if not input_file.exists():
        warnings.warn(f"File not found, skipping: {input_file}")
        return

    selected_tools, _, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_types = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )
    smell_names = load_test_smell_names(smell_detector)
    revision_group_pairs = selected_revision_group_pair_list(args.revision_group_pair)
    frame = pd.read_csv(input_file, keep_default_na=False, na_filter=False)
    if frame.empty:
        print("No size-control test smell effect plots generated.")
        return

    frame = frame[frame["smell_detector"] == smell_detector].copy()
    if selected_tools is not None:
        frame = frame[frame["tool"].isin(selected_tools)]
    if selected_strategies is not None:
        frame = frame[frame["strategy"].isin(selected_strategies)]
    if revision_types:
        frame = frame[frame["change"].isin(revision_types)]

    plotted_any = False
    combinations = frame[["strategy", "tool", "smell_detector", "change"]].drop_duplicates()
    for row in combinations.itertuples(index=False):
        output_file = (
            output_directory
            / (
                f"{OUTPUT_FILE_PREFIX}--{row.tool}--{row.strategy}--{row.smell_detector}--{row.change}"
                f"{pairs_suffix(revision_group_pairs)}.pdf"
            )
        )
        plot_size_control_effect(
            frame,
            strategy=row.strategy,
            tool=row.tool,
            smell_detector=row.smell_detector,
            change=row.change,
            smell_names=smell_names,
            revision_group_pairs=revision_group_pairs,
            output_file=output_file,
        )
        if output_file.exists():
            plotted_any = True
            print(f"Wrote {output_file}")

    if not plotted_any:
        print("No size-control test smell effect plots generated.")


if __name__ == "__main__":
    main()
