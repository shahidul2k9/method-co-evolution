import os

import matplotlib.pyplot as plt
import pandas as pd

import mhc.util as util
from mhc.config import WORKSPACE_DIRECTORY
from ptc.constants import ALL_REPOSITORY
from ptc.plot_util import (
    GRAPH_GAPS,
    GRAPH_MARKER_SIZES,
    GRAPH_MARKS,
    GRAPH_STYLES,
    GRAPH_WIDTHS,
    build_experiment_plot_parser,
    ecdf,
    resolve_experiment_filters,
    select_named_items,
)

STATS_FILE = f"{WORKSPACE_DIRECTORY}/data/aggregate/t2p-mwu.csv"
SIZE_ORDER = ["negligible", "small", "medium", "large"]


def build_parser():
    return build_experiment_plot_parser("Plot MWU aggregate CDFs and effect-size bars.")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        use_filters=args.use_filters,
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )

    if not os.path.exists(STATS_FILE):
        print(f"Stats file not found: {STATS_FILE}")
        return

    df = pd.read_csv(STATS_FILE, keep_default_na=False, na_values=[""])
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

        fig, axes = plt.subplots(len(strategies), 3, figsize=(18, 5 * len(strategies)), squeeze=False)
        legend_handles = None
        legend_labels = None

        for strategy_index, strategy in enumerate(strategies):
            strategy_df = tool_df[tool_df["strategy"] == strategy].copy()
            change_names = sorted(strategy_df["change"].dropna().unique(), key=str.lower)

            corr_ax = axes[strategy_index][0]
            p_ax = axes[strategy_index][1]
            size_ax = axes[strategy_index][2]

            for line_index, change in enumerate(change_names):
                change_df = strategy_df[strategy_df["change"] == change]

                corr_values = change_df["corr"].dropna()
                if not corr_values.empty:
                    x, y = ecdf(corr_values)
                    corr_ax.step(
                        x,
                        y,
                        linewidth=GRAPH_WIDTHS[line_index % len(GRAPH_WIDTHS)],
                        linestyle=GRAPH_STYLES[line_index % len(GRAPH_STYLES)],
                        where="post",
                        label=change,
                    )
                    corr_ax.plot(
                        x,
                        y,
                        linestyle="None",
                        marker=GRAPH_MARKS[line_index % len(GRAPH_MARKS)],
                        markevery=max(1, GRAPH_GAPS[line_index % len(GRAPH_GAPS)]),
                        markersize=GRAPH_MARKER_SIZES[line_index % len(GRAPH_MARKER_SIZES)],
                    )

                p_values = change_df["mwu_p"].dropna()
                if not p_values.empty:
                    x, y = ecdf(p_values)
                    p_ax.step(
                        x,
                        y,
                        linewidth=GRAPH_WIDTHS[line_index % len(GRAPH_WIDTHS)],
                        linestyle=GRAPH_STYLES[line_index % len(GRAPH_STYLES)],
                        where="post",
                        label=change,
                    )
                    p_ax.plot(
                        x,
                        y,
                        linestyle="None",
                        marker=GRAPH_MARKS[line_index % len(GRAPH_MARKS)],
                        markevery=max(1, GRAPH_GAPS[line_index % len(GRAPH_GAPS)]),
                        markersize=GRAPH_MARKER_SIZES[line_index % len(GRAPH_MARKER_SIZES)],
                    )

            if strategy_index == 0:
                legend_handles, legend_labels = corr_ax.get_legend_handles_labels()

            size_counts = (
                strategy_df.dropna(subset=["mwu_size"])
                .groupby(["change", "mwu_size"])
                .size()
                .unstack(fill_value=0)
                .reindex(columns=SIZE_ORDER, fill_value=0)
                .sort_index()
            )
            if not size_counts.empty:
                size_counts.plot(kind="bar", stacked=True, ax=size_ax, width=0.8, legend=False)

            corr_ax.set_title("Correlation CDF", fontsize=18)
            corr_ax.set_xlabel("corr", fontsize=14)
            corr_ax.set_ylabel("ECDF", fontsize=14)
            corr_ax.set_xlim(-1.05, 1.05)
            corr_ax.grid(True, alpha=0.25)
            corr_ax.text(
                -0.42,
                0.5,
                strategy,
                transform=corr_ax.transAxes,
                rotation=90,
                va="center",
                ha="center",
                fontsize=18,
            )

            p_ax.set_title("P-value CDF", fontsize=18)
            p_ax.set_xlabel("mwu_p", fontsize=14)
            p_ax.set_ylabel("ECDF", fontsize=14)
            p_ax.set_xlim(-0.02, 1.02)
            p_ax.axvspan(0, 0.05, color="tomato", alpha=0.08)
            p_ax.axvline(0.05, color="tomato", linestyle="--", linewidth=2)
            p_ax.text(
                0.05,
                0.98,
                "p=0.05",
                transform=p_ax.get_xaxis_transform(),
                ha="left",
                va="top",
                fontsize=10,
                color="tomato",
            )
            p_ax.grid(True, alpha=0.25)

            size_ax.set_title("MWU Effect Size", fontsize=18)
            size_ax.set_xlabel("change", fontsize=14)
            size_ax.set_ylabel("count", fontsize=14)
            size_ax.tick_params(axis="x", labelrotation=45)
            size_ax.grid(True, axis="y", alpha=0.25)
            if strategy_index == 0 and not size_counts.empty:
                size_ax.legend(fontsize=10)

        if legend_handles:
            fig.legend(
                legend_handles,
                legend_labels,
                loc="upper center",
                ncol=min(4, len(legend_labels)),
                fontsize=10,
            )

        fig.tight_layout(rect=(0, 0, 1, 0.97))
        fig_file = f"{WORKSPACE_DIRECTORY}/figure/t2p-mwu-cdf/t2p-mwu-cdf--{tool}.pdf"
        os.makedirs(os.path.dirname(fig_file), exist_ok=True)
        fig.savefig(fig_file, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    main()
