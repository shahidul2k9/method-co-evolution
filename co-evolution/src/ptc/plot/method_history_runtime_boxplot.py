from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from mhc.command_util import build_experiment_parser, resolve_experiment_paths
from ptc.plot.method_history_runtime_table import (
    DEFAULT_INPUT,
    EXCLUDED_RUNTIME_TOOLS,
    RUNTIME_SUFFIX,
    display_tool_name,
    resolve_output_file,
    resolve_path,
)


DEFAULT_OUTPUT = Path("figure") / "method-history-runtime-boxplot.pdf"
Y_AXIS_MAX_SECONDS = 12
BOX_WIDTH = 0.32
BOX_GAP = 0.72
AXIS_LABEL_FONT_SIZE = 18
TICK_LABEL_FONT_SIZE = 16
BOUNDARY_COUNT_FONT_SIZE = 16
BOX_COLORS = ["#E8E8E8", "#D8D8D8", "#C8C8C8", "#B8B8B8", "#A8A8A8"]
BOX_HATCHES = ["///", "\\\\\\", "xx", "..", "++"]


def build_parser():
    parser = build_experiment_parser(
        "Generate a boxplot of method-history tool runtimes.",
        include_tools=False,
        include_projects=False,
        include_strategies=False,
        include_project_directory=True,
        include_output_directory=True,
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="Runtime metric CSV. Defaults to <project-directory>/data/rqs/rq1/method-level-revision-history-metric.csv.",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help=(
            "Generated boxplot file. Relative paths resolve from the experiment directory. "
            "Defaults to <workspace-directory>/experiment/<experiment-name>/figure/"
            "method-history-runtime-boxplot.pdf."
        ),
    )
    return parser


def load_runtime_series(df: pd.DataFrame) -> list[dict]:
    runtime_columns = [column for column in df.columns if column.endswith(RUNTIME_SUFFIX)]
    if not runtime_columns:
        raise ValueError(f"No columns ending with {RUNTIME_SUFFIX!r} were found.")

    series = []
    for column in runtime_columns:
        tool = column[: -len(RUNTIME_SUFFIX)]
        if tool in EXCLUDED_RUNTIME_TOOLS:
            continue

        values = pd.to_numeric(df[column], errors="coerce").dropna() / 1000
        values = values[values > 0]
        if values.empty:
            continue
        series.append(
            {
                "tool": tool,
                "label": display_tool_name(tool),
                "values": values,
            }
        )

    if not series:
        raise ValueError("No positive runtime values were found for non-IntelliJ tools.")
    return series


def count_values_above_limit(runtime_series: list[dict], limit: float) -> list[int]:
    return [int((item["values"] > limit).sum()) for item in runtime_series]


def draw_runtime_boxplot(ax, runtime_series: list[dict]) -> None:
    labels = [item["label"] for item in runtime_series]
    values = [item["values"] for item in runtime_series]
    positions = [1 + index * BOX_GAP for index in range(len(runtime_series))]

    boxplot = ax.boxplot(
        values,
        positions=positions,
        patch_artist=True,
        widths=BOX_WIDTH,
        showfliers=True,
        medianprops={"color": "black", "linewidth": 1.5},
        whiskerprops={"color": "black", "linewidth": 0.9},
        capprops={"color": "black", "linewidth": 0.9},
        flierprops={
            "marker": "o",
            "markerfacecolor": "none",
            "markeredgecolor": "#666666",
            "markeredgewidth": 0.7,
            "markersize": 3,
            "alpha": 0.7,
        },
    )

    for index, patch in enumerate(boxplot["boxes"]):
        patch.set_facecolor(BOX_COLORS[index % len(BOX_COLORS)])
        patch.set_edgecolor("black")
        patch.set_linewidth(0.9)
        patch.set_hatch(BOX_HATCHES[index % len(BOX_HATCHES)])

    ax.set_ylim(0, Y_AXIS_MAX_SECONDS)
    ax.set_xlim(positions[0] - 0.38, positions[-1] + 0.38)
    ax.set_ylabel("Runtime (second)", fontsize=AXIS_LABEL_FONT_SIZE)
    ax.set_yticks(range(Y_AXIS_MAX_SECONDS + 1))
    ax.set_xticks(positions)
    ax.set_xticklabels(labels, rotation=30, ha="right", rotation_mode="anchor")
    ax.tick_params(axis="x", labelsize=TICK_LABEL_FONT_SIZE)
    ax.tick_params(axis="y", labelsize=TICK_LABEL_FONT_SIZE)
    ax.grid(True, axis="y", linestyle="--", linewidth=0.5, color="#C8C8C8")
    ax.set_axisbelow(True)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_linewidth(0.8)
    ax.spines["bottom"].set_linewidth(0.8)

    clipped_counts = count_values_above_limit(runtime_series, Y_AXIS_MAX_SECONDS)
    for position, clipped_count in zip(positions, clipped_counts):
        if clipped_count == 0:
            continue
        marker_y = Y_AXIS_MAX_SECONDS - 1.05
        ax.scatter(
            position,
            marker_y,
            marker="^",
            s=28,
            facecolor="white",
            edgecolor="black",
            linewidth=0.8,
            zorder=5,
        )
        ax.annotate(
            f"{clipped_count}",
            xy=(position, marker_y),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=BOUNDARY_COUNT_FONT_SIZE,
        )


def plot_runtime_boxplot(runtime_series: list[dict], output_file: Path) -> None:
    fig, ax = plt.subplots(figsize=(7.2, 4.8))
    draw_runtime_boxplot(ax, runtime_series)
    fig.tight_layout()
    output_file.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_file, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> Path:
    args = build_parser().parse_args(argv)
    project_directory = Path(args.project_directory)
    experiment_directory = resolve_experiment_paths(
        args.workspace_directory,
        args.experiment_name,
    ).experiment_directory
    input_file = resolve_path(project_directory, args.input_file, DEFAULT_INPUT)
    output_file = resolve_output_file(
        project_directory,
        experiment_directory,
        args.output_directory,
        args.output_file,
        DEFAULT_OUTPUT,
    )

    if not input_file.exists():
        raise FileNotFoundError(f"Runtime metric CSV not found: {input_file}")

    metric_df = pd.read_csv(input_file)
    runtime_series = load_runtime_series(metric_df)
    plot_runtime_boxplot(runtime_series, output_file)
    print(f"Wrote runtime boxplot: {output_file}")
    return output_file


if __name__ == "__main__":
    main()
