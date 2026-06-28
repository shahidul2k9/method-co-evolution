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
    OUTPUT_FILE_NAME,
)
from ptc.generator.t2p_test_smell_revision import CHANGE_COLUMNS
from ptc.plot.method_history_runtime_table import resolve_path
from ptc.plot.t2p_test_smell_size_control_effectplot import (
    SIZE_CONTROL_AXIS_LABEL_FONTSIZE,
    SIZE_CONTROL_CI_CAP_HALF_HEIGHT,
    SIZE_CONTROL_CI_CAP_LINEWIDTH,
    SIZE_CONTROL_CI_LINEWIDTH,
    SIZE_CONTROL_LEGEND_FONTSIZE,
    SIZE_CONTROL_LEGEND_MARKER_SCALE,
    SIZE_CONTROL_MARKER_EDGE_WIDTH,
    SIZE_CONTROL_MARKER_SIZE,
    SIZE_CONTROL_MIN_FIGURE_HEIGHT,
    SIZE_CONTROL_ROW_HEIGHT,
    SIZE_CONTROL_SERIES_STEP,
    SIZE_CONTROL_XTICK_FONTSIZE,
    SIZE_CONTROL_YTICK_FONTSIZE,
    SIZE_CONTROL_ODDS_RATIO_X_AXIS_LABEL,
    METHOD_SIZE_LABEL,
    SIZE_CONTROL_LEGEND_ANCHOR_X,
    SIZE_CONTROL_XLABEL_Y,
    add_method_group_separators,
    control_group_order,
    legend_pairs,
    pairs_suffix,
    selected_revision_group_pair_list,
    series_order,
    series_style,
)
from ptc.plot.t2p_test_smell_barchart import comparison_label, comparison_pair, comparison_style
from ptc.plot_util import build_experiment_plot_parser

OUTPUT_FILE_PREFIX = "t2p-test-smell-size-control-odds-ratio-effectplot"


def build_parser():
    parser = build_experiment_plot_parser(
        "Render the LOC-controlled RQ4 test-smell odds-ratio effect plot.",
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
    parser.add_argument(
        "--output-type",
        choices=("pdf", "tex"),
        default="pdf",
        help="Output format. 'pdf' writes the plot PDF; 'tex' writes a standalone LaTeX wrapper around a build PDF.",
    )
    return parser


def render_standalone_latex_plot(relative_pdf_path: str) -> str:
    return rf"""\documentclass{{article}}
\usepackage[margin=0.5in]{{geometry}}
\usepackage{{graphicx}}

\begin{{document}}
\pagestyle{{empty}}

\begin{{center}}
\includegraphics[width=\textwidth]{{\detokenize{{{relative_pdf_path}}}}}
\end{{center}}

\end{{document}}
"""


def write_latex_plot_wrapper(tex_file: Path, pdf_file: Path) -> None:
    os.makedirs(tex_file.parent, exist_ok=True)
    relative_pdf_path = os.path.relpath(pdf_file, tex_file.parent).replace(os.sep, "/")
    tex_file.write_text(render_standalone_latex_plot(relative_pdf_path), encoding="utf-8")


def finite_values(frame: pd.DataFrame, columns: list[str]) -> pd.Series:
    values = pd.to_numeric(pd.concat([frame[column] for column in columns], ignore_index=True), errors="coerce")
    return values[values.map(math.isfinite)]


def odds_ratio_axis_limits(frame: pd.DataFrame) -> tuple[float, float]:
    values = finite_values(frame, ["odds_ratio_ci_low", "odds_ratio_ci_high", "odds_ratio"])
    if values.empty:
        return 0.5, 2.0
    low = min(values.min(), 1.0)
    high = max(values.max(), 1.0)
    padded_low = math.floor((low - 0.25) / 0.5) * 0.5
    padded_high = math.ceil((high + 0.25) / 0.5) * 0.5
    return max(0.0, padded_low), max(padded_high, 1.5)


def numeric_cell(row: pd.Series, column: str) -> float:
    return float(pd.to_numeric(pd.Series([row[column]]), errors="coerce").iloc[0])


def clip_for_axis(value: float, x_limits: tuple[float, float]) -> float:
    if not math.isfinite(value):
        return math.nan
    return min(max(value, x_limits[0]), x_limits[1])


def draw_horizontal_odds_ci(
    ax,
    y: float,
    low: float,
    high: float,
    *,
    color: str,
    linestyle: str,
) -> None:
    ax.hlines(y, low, high, colors=color, linestyles=linestyle, linewidth=SIZE_CONTROL_CI_LINEWIDTH, zorder=1)
    ax.vlines(
        [low, high],
        y - SIZE_CONTROL_CI_CAP_HALF_HEIGHT,
        y + SIZE_CONTROL_CI_CAP_HALF_HEIGHT,
        colors=color,
        linewidth=SIZE_CONTROL_CI_CAP_LINEWIDTH,
        zorder=1,
    )


def plot_odds_ratio_axis(
    ax,
    plot_df: pd.DataFrame,
    *,
    control_groups: list[str],
    x_limits: tuple[float, float],
) -> None:
    if plot_df.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes)
        ax.set_axis_off()
        return

    series = series_order(plot_df)
    pairs = legend_pairs(plot_df)
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
        ratio = numeric_cell(row, "odds_ratio")
        low = numeric_cell(row, "odds_ratio_ci_low")
        high = numeric_cell(row, "odds_ratio_ci_high")
        if not all(math.isfinite(value) for value in [ratio, low, high]):
            continue
        ratio = clip_for_axis(ratio, x_limits)
        low = clip_for_axis(low, x_limits)
        high = clip_for_axis(high, x_limits)
        if not all(math.isfinite(value) for value in [ratio, low, high]):
            continue
        y_position = y_by_control_group[control_group] + pair_offsets[pair]
        draw_horizontal_odds_ci(
            ax,
            y_position,
            low,
            high,
            color=str(style["color"]),
            linestyle=str(style["linestyle"]),
        )
        ax.scatter(
            [ratio],
            [y_position],
            marker=str(style["marker"]),
            facecolor=str(style["color"]) if str(row["significant"]) == "x" else "white",
            edgecolor="black",
            linewidth=SIZE_CONTROL_MARKER_EDGE_WIDTH,
            s=SIZE_CONTROL_MARKER_SIZE,
            zorder=2,
        )

    ax.axvline(1, color="black", linewidth=1.4, linestyle="--")
    ax.set_xscale("linear")
    ax.set_xlim(*x_limits)
    ax.xaxis.set_major_locator(MultipleLocator(0.5))
    ax.tick_params(axis="x", labelsize=SIZE_CONTROL_XTICK_FONTSIZE)
    ax.set_xlabel(SIZE_CONTROL_ODDS_RATIO_X_AXIS_LABEL, fontsize=SIZE_CONTROL_AXIS_LABEL_FONTSIZE)
    ax.xaxis.set_label_coords(0.5, SIZE_CONTROL_XLABEL_Y)
    ax.set_yticks(list(range(len(control_groups))))
    ax.set_yticklabels(control_groups, fontsize=SIZE_CONTROL_YTICK_FONTSIZE)
    ax.set_ylabel(METHOD_SIZE_LABEL, fontsize=SIZE_CONTROL_AXIS_LABEL_FONTSIZE)
    add_method_group_separators(ax, control_groups)
    ax.invert_yaxis()
    ax.set_ylim(len(control_groups) - 0.5, -0.5)
    ax.grid(True, axis="x", which="major", alpha=0.42, linewidth=1.1)


def plot_size_control_odds_ratio_effect(
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
    x_limits = odds_ratio_axis_limits(plot_df)
    fig, ax = plt.subplots(
        figsize=(10.5, max(SIZE_CONTROL_MIN_FIGURE_HEIGHT, len(control_groups) * SIZE_CONTROL_ROW_HEIGHT))
    )
    plot_odds_ratio_axis(ax, plot_df, control_groups=control_groups, x_limits=x_limits)

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
            linewidth=SIZE_CONTROL_CI_LINEWIDTH,
            label=comparison_label(pair),
        )
        for pair in pairs
    ]
    fig.legend(
        handles=handles,
        frameon=False,
        fontsize=SIZE_CONTROL_LEGEND_FONTSIZE,
        loc="upper center",
        bbox_to_anchor=(SIZE_CONTROL_LEGEND_ANCHOR_X, 0.99),
        ncol=2,
        markerscale=SIZE_CONTROL_LEGEND_MARKER_SCALE,
        handlelength=2.2,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.82))
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
        print("No size-control test smell odds-ratio plots generated.")
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
        output_stem = (
            f"{OUTPUT_FILE_PREFIX}--{row.tool}--{row.strategy}--{row.smell_detector}--{row.change}"
            f"{pairs_suffix(revision_group_pairs)}"
        )
        output_file = output_directory / f"{output_stem}.{args.output_type}"
        plot_output_file = output_file
        if args.output_type == "tex":
            plot_output_file = output_directory / "build" / output_stem / f"{output_stem}.pdf"
        plot_size_control_odds_ratio_effect(
            frame,
            strategy=row.strategy,
            tool=row.tool,
            smell_detector=row.smell_detector,
            change=row.change,
            smell_names=smell_names,
            revision_group_pairs=revision_group_pairs,
            output_file=plot_output_file,
        )
        if plot_output_file.exists():
            if args.output_type == "tex":
                write_latex_plot_wrapper(output_file, plot_output_file)
            plotted_any = True
            print(f"Wrote {output_file}")

    if not plotted_any:
        print("No size-control test smell odds-ratio plots generated.")


if __name__ == "__main__":
    main()
