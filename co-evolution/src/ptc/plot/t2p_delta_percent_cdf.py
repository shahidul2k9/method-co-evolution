import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ptc.constants import ALL_REPOSITORY
from ptc.plot_util import (
    GRAPH_MARKER_SIZES,
    GRAPH_MARKS,
    GRAPH_STYLES,
    GRAPH_WIDTHS,
    build_experiment_plot_parser,
    ecdf,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)


def build_parser():
    return build_experiment_plot_parser("Plot CDFs of per-project positive delta percentages by change type.")


def format_change_name(change: str) -> str:
    return change.removeprefix("ch_").replace("_", " ").title()


def sparse_marker_indices(size: int, marker_count: int = 5) -> list[int]:
    if size <= marker_count:
        return list(range(size))

    return sorted({round(index * (size - 1) / (marker_count - 1)) for index in range(marker_count)})


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    stats_file = experiment_directory / "aggregate" / "t2p-delta.csv"
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        use_filters=args.use_filters,
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )

    if not os.path.exists(stats_file):
        print(f"Stats file not found: {stats_file}")
        return

    df = pd.read_csv(stats_file, keep_default_na=False, na_values=[""])
    change_columns = [column for column in df.columns if column.startswith("ch_")]
    tools = select_named_items(
        sorted(df["tool"].dropna().unique(), key=str.lower),
        selected_tools,
        item_label="tool",
    )

    for tool in tools:
        tool_df = df[df["tool"] == tool].copy()
        tool_df = tool_df[tool_df["project"] != ALL_REPOSITORY].copy()

        projects = select_named_items(
            sorted(tool_df["project"].dropna().unique(), key=str.lower),
            selected_projects,
            item_label="project",
            strict=False,
        )
        if selected_projects is not None:
            tool_df = tool_df[tool_df["project"].isin(projects)].copy()
        if tool_df.empty:
            continue

        strategies = select_named_items(
            sorted(tool_df["strategy"].dropna().unique(), key=str.lower),
            selected_strategies,
            item_label="strategy",
        )
        if not strategies:
            continue

        fig, axes = plt.subplots(
            len(strategies),
            len(change_columns),
            figsize=(3.0 * len(change_columns), 2.8 * len(strategies)),
            squeeze=False,
        )

        for strategy_index, strategy in enumerate(strategies):
            strategy_df = tool_df[tool_df["strategy"] == strategy]

            for change_index, change in enumerate(change_columns):
                ax = axes[strategy_index][change_index]
                percent_df = (
                    strategy_df[["methods", change]]
                    .apply(pd.to_numeric, errors="coerce")
                    .dropna()
                )
                percent_df = percent_df[percent_df["methods"] > 0]
                plotted = False
                if not percent_df.empty:
                    percent_values = (percent_df[change] / percent_df["methods"]) * 100
                    if not percent_values.empty:
                        x, y = ecdf(percent_values)
                        ax.step(
                            x,
                            y,
                            linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                            linestyle=GRAPH_STYLES[0],
                            where="post",
                        )
                        ax.plot(
                            x,
                            y,
                            linestyle="None",
                            marker=GRAPH_MARKS[change_index % len(GRAPH_MARKS)],
                            markevery=sparse_marker_indices(len(x)),
                            markersize=GRAPH_MARKER_SIZES[change_index % len(GRAPH_MARKER_SIZES)],
                        )
                        target_y = 0.8
                        target_index = np.searchsorted(y, target_y, side="left")
                        if target_index < len(x):
                            target_x = x[target_index]
                            ax.scatter(target_x, target_y, color="black", s=30, zorder=3)
                            ax.annotate(
                                f"x={target_x:.1f}%",
                                xy=(target_x, target_y),
                                xytext=(8, 8),
                                textcoords="offset points",
                                fontsize=10,
                            )
                        plotted = True

                if strategy_index == 0:
                    ax.set_title(format_change_name(change), fontsize=14)

                ax.set_xlim(-1, 101)
                ax.set_ylim(-0.02, 1.02)
                ax.set_xticks([0, 25, 50, 75, 100])
                ax.grid(True, alpha=0.25)

                if not plotted:
                    ax.text(
                        0.5,
                        0.5,
                        "No data",
                        ha="center",
                        va="center",
                        fontsize=12,
                        transform=ax.transAxes,
                    )

                if change_index == 0:
                    ax.set_ylabel("ECDF", fontsize=12)
                    ax.text(
                        -0.42,
                        0.5,
                        strategy,
                        transform=ax.transAxes,
                        rotation=90,
                        va="center",
                        ha="center",
                        fontsize=14,
                    )

                if strategy_index == len(strategies) - 1:
                    ax.set_xlabel("% methods", fontsize=11)

        fig.suptitle(
            f"{tool}: percent of methods where test changed more than production",
            fontsize=18,
        )
        fig.tight_layout(rect=(0.02, 0.02, 1, 0.96))
        fig_file = f"{WORKSPACE_DIRECTORY}/figure/t2p-delta-percent-cdf/t2p-delta-percent-cdf--{tool}.pdf"
        os.makedirs(os.path.dirname(fig_file), exist_ok=True)
        fig.savefig(fig_file, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    main()
