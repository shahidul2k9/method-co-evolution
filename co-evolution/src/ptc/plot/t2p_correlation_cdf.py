import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

import mhc.util as util
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
    resolve_experiment_paths,
    select_revision_columns,
    select_named_items,
)

SIZE_ORDER = ["negligible", "small", "medium", "large"]


def format_count(value: int) -> str:
    return f"{value:,}"


def change_color_map(changes: list[str]) -> dict[str, str]:
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    return {change: colors[index % len(colors)] for index, change in enumerate(changes)}


def draw_row_info_axis(ax, strategy: str, strategy_df: pd.DataFrame, changes: list[str], colors: dict[str, str]) -> None:
    ax.axis("off")
    ax.text(0.5, 0.92, strategy, transform=ax.transAxes, va="top", ha="center", fontsize=16, fontweight="bold")
    ax.text(
        0.0,
        0.82,
        "\n".join(
            [
                f"total={format_count(len(strategy_df))}",
                f"projects={format_count(strategy_df['project'].nunique())}",
                f"changes={format_count(len(changes))}",
            ]
        ),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=13,
        linespacing=1.2,
    )
    handles = [
        Line2D(
            [0],
            [0],
            color=colors[change],
            linewidth=GRAPH_WIDTHS[index % len(GRAPH_WIDTHS)],
            linestyle=GRAPH_STYLES[index % len(GRAPH_STYLES)],
            label=change,
        )
        for index, change in enumerate(changes)
    ]
    if handles:
        ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=11, borderaxespad=0, handlelength=2.6)


def build_parser():
    return build_experiment_plot_parser("Plot MWU aggregate CDFs and effect-size bars.")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    stats_file = experiment_directory / "aggregate" / "t2p-correlation.csv"
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )

    if not os.path.exists(stats_file):
        print(f"Stats file not found: {stats_file}")
        return

    df = pd.read_csv(stats_file, keep_default_na=False, na_values=[""])
    tools = select_named_items(
        sorted(df["tool"].dropna().unique(), key=str.lower),
        selected_tools,
        item_label="tool",
    )

    for tool in tools:
        tool_df = df[df["tool"] == tool].copy()
        tool_df = tool_df[tool_df["project"] != ALL_REPOSITORY].copy()

        projects = select_named_items(
            list(dict.fromkeys(tool_df["project"].dropna())),
            selected_projects,
            item_label="project",
            strict=False,
        )
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
            4,
            figsize=(19.8, 5 * len(strategies)),
            gridspec_kw={"width_ratios": [1.4, 4, 4, 4]},
            squeeze=False,
        )

        for strategy_index, strategy in enumerate(strategies):
            strategy_df = tool_df[tool_df["strategy"] == strategy].copy()
            available_changes = sorted(strategy_df["change"].dropna().unique(), key=str.lower)
            change_names = [
                change.removeprefix("ch_")
                for change in select_revision_columns(
                    [change if str(change).startswith("ch_") else f"ch_{change}" for change in available_changes]
                )
            ]
            change_colors = change_color_map(change_names)
            draw_row_info_axis(axes[strategy_index][0], strategy, strategy_df, change_names, change_colors)

            corr_ax = axes[strategy_index][1]
            p_ax = axes[strategy_index][2]
            size_ax = axes[strategy_index][3]

            for line_index, change in enumerate(change_names):
                change_df = strategy_df[strategy_df["change"] == change]

                corr_values = change_df["corr"].dropna()
                if not corr_values.empty:
                    x, y = ecdf(corr_values)
                    corr_ax.step(
                        x,
                        y,
                        linewidth=GRAPH_WIDTHS[line_index % len(GRAPH_WIDTHS)],
                        color=change_colors[change],
                        linestyle=GRAPH_STYLES[line_index % len(GRAPH_STYLES)],
                        where="post",
                        label=change,
                    )
                    corr_ax.plot(
                        x,
                        y,
                        color=change_colors[change],
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
                        color=change_colors[change],
                        linestyle=GRAPH_STYLES[line_index % len(GRAPH_STYLES)],
                        where="post",
                        label=change,
                    )
                    p_ax.plot(
                        x,
                        y,
                        color=change_colors[change],
                        linestyle="None",
                        marker=GRAPH_MARKS[line_index % len(GRAPH_MARKS)],
                        markevery=max(1, GRAPH_GAPS[line_index % len(GRAPH_GAPS)]),
                        markersize=GRAPH_MARKER_SIZES[line_index % len(GRAPH_MARKER_SIZES)],
                    )

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

            p_ax.set_title("P-value CDF", fontsize=18)
            p_ax.set_xlabel("mwu_p", fontsize=14)
            p_ax.set_ylabel("ECDF", fontsize=14)
            p_ax.set_xlim(-0.02, 1.02)
            p_ax.axvspan(0, 0.05, color="tomato", alpha=0.08)
            p_ax.axvline(0.05, color="tomato", linestyle="--", linewidth=2)
            p_ax.text(
                0.0,
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

        fig.tight_layout()
        fig_file = experiment_directory / "figure" / f"t2p-correlation-cdf--{tool}.pdf"
        os.makedirs(os.path.dirname(fig_file), exist_ok=True)
        fig.savefig(fig_file, bbox_inches="tight")
        plt.close(fig)


if __name__ == "__main__":
    main()
