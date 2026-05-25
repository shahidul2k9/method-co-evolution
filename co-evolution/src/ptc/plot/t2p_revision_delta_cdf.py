import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator
import pandas as pd

import mhc.util as util
from mhc.artifacts import is_main_code, is_test_case_method, is_test_code
from ptc.constants import ALL_REPOSITORY, CODE_SHOVEL_UNSUPPORTED_CHANGES, MethodChangeType
from ptc.plot_util import (
    GRAPH_MARKER_SIZES,
    GRAPH_MARKS,
    GRAPH_STYLES,
    GRAPH_WIDTHS,
    build_experiment_plot_parser,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_revision_columns,
    select_named_items,
)

CHANGE_COLUMNS = [
    "ch_all",
    "ch_diff",
    *[f"ch_{change_type.name.lower()}" for change_type in MethodChangeType],
]
CODE_SHOVEL_UNSUPPORTED_CHANGE_SET = {
    f"ch_{change_type.name.lower()}" for change_type in CODE_SHOVEL_UNSUPPORTED_CHANGES
}
SERIES_COLOR = "tab:blue"


def build_parser():
    return build_experiment_plot_parser("Plot production-minus-test revision delta CDFs.")


def format_count(value: int) -> str:
    return f"{value:,}"


def format_percent(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def build_project_stats(project_df: pd.DataFrame) -> dict[str, int]:
    total = len(project_df)
    test_count = 0
    production_count = 0
    if "from_artifact" in project_df:
        test_count = int(
            project_df["from_artifact"]
            .map(lambda artifact: is_test_code(artifact) or is_test_case_method(artifact))
            .sum()
        )
    if "to_artifact" in project_df:
        production_count = int(project_df["to_artifact"].map(is_main_code).sum())
    return {"total": total, "test": test_count, "production": production_count}


def draw_row_info_axis(ax, project: str, project_df: pd.DataFrame) -> None:
    stats = build_project_stats(project_df)
    total = stats["total"]
    ax.axis("off")
    ax.text(0, 0.92, project, transform=ax.transAxes, va="top", ha="left", fontsize=16, fontweight="bold")
    ax.text(
        0.0,
        0.82,
        "\n".join(
            [
                f"total={format_count(total)}",
                f"test={format_count(stats['test'])} ({format_percent(stats['test'], total)})",
                f"production={format_count(stats['production'])} ({format_percent(stats['production'], total)})",
            ]
        ),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=13,
        linespacing=1.2,
    )
    ax.legend(
        handles=[Line2D([0], [0], color=SERIES_COLOR, linewidth=GRAPH_WIDTHS[0], linestyle=GRAPH_STYLES[0], label="delta CDF")],
        loc="lower left",
        frameon=False,
        fontsize=12,
        borderaxespad=0,
        handlelength=2.6,
    )


def load_t2p_change_dfs(
    experiment_directory: Path,
    tool: str,
    strategy: str,
    selected_projects: list[str] | None,
) -> list[pd.DataFrame]:
    csv_files = list_csv_files(
        experiment_directory / "t2p-change" / tool / strategy,
        selected_projects,
        strict=False,
    )
    t2p_change_dfs = [
        pd.read_csv(t2p_change_file, keep_default_na=False, na_filter=False)
        for t2p_change_file in csv_files
    ]
    return [df for df in t2p_change_dfs if not df.empty]


def order_change_columns(columns: list[str]) -> list[str]:
    return select_revision_columns(columns, preferred_order=CHANGE_COLUMNS, include_extra=False)


def format_change_name(change: str) -> str:
    return change.removeprefix("ch_").replace("_", " ").title()


def delta_cdf(df: pd.DataFrame, change: str) -> pd.Series:
    pair_df = (
        df[[f"to_{change}", f"from_{change}"]]
        .apply(pd.to_numeric, errors="coerce")
        .dropna()
    )

    if pair_df.empty:
        return pd.Series(dtype="int64")

    delta = (pair_df[f"to_{change}"] - pair_df[f"from_{change}"]).astype("int64")
    # delta = delta[delta >= 0]

    if delta.empty:
        return pd.Series(dtype="float64")

    frequencies = delta.value_counts().sort_index()
    frequencies = frequencies.reindex(
        range(int(frequencies.index.min()), int(frequencies.index.max()) + 1),
        fill_value=0,
    )
    return frequencies.cumsum() / frequencies.sum()


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

    t2p_change_directory = experiment_directory / "t2p-change"
    tools = select_named_items(
        util.sorted_directory_names(t2p_change_directory),
        selected_tools,
        item_label="tool",
    )

    plotted_any = False
    for tool in tools:
        strategies = select_named_items(
            util.sorted_directory_names(t2p_change_directory / tool),
            selected_strategies,
            item_label="strategy",
        )
        for strategy in strategies:
            t2p_change_dfs = load_t2p_change_dfs(
                experiment_directory,
                tool,
                strategy,
                selected_projects,
            )
            if not t2p_change_dfs:
                continue

            df = pd.concat(t2p_change_dfs, ignore_index=True)
            change_cols = order_change_columns(
                [column[len("from_"):] for column in df.columns if column.startswith("from_ch_")]
            )
            if not change_cols:
                print(f"No from_ch_* columns found for {tool} {strategy}.")
                continue

            print(tool, strategy)
            plotted_any = True
            projects = select_named_items(
                list(dict.fromkeys(df["project"].dropna())),
                selected_projects,
                item_label="project",
                strict=False,
            )
            projects.append(ALL_REPOSITORY)

            fig, axes = plt.subplots(
                len(projects),
                len(change_cols) + 1,
                figsize=(1.8 + 4 * len(change_cols), 3.2 * len(projects)),
                gridspec_kw={"width_ratios": [1.4, *([4] * len(change_cols))]},
                squeeze=False,
            )
            fig.supxlabel("production - test revisions", fontsize=20)
            fig.supylabel("CDF", fontsize=20)

            for project_index, project in enumerate(projects):
                project_df = df if project == ALL_REPOSITORY else df[df["project"] == project]
                draw_row_info_axis(axes[project_index][0], project, project_df)

                for change_index, change in enumerate(change_cols):
                    ax = axes[project_index][change_index + 1]
                    ax.set_title(format_change_name(change), fontsize=18)
                    ax.set_ylim(-0.02, 1.02)
                    ax.xaxis.set_major_locator(MaxNLocator(integer=True))

                    unsupported = tool == "codeShovel" and change in CODE_SHOVEL_UNSUPPORTED_CHANGE_SET
                    if unsupported:
                        ax.text(
                            0.5,
                            0.5,
                            "NA",
                            ha="center",
                            va="center",
                            fontsize=26,
                            transform=ax.transAxes,
                        )
                    else:
                        cdf = delta_cdf(project_df, change)
                        if cdf.empty:
                            ax.text(
                                0.5,
                                0.5,
                                "No data",
                                ha="center",
                                va="center",
                                fontsize=14,
                                transform=ax.transAxes,
                            )
                        else:
                            ax.step(
                                cdf.index,
                                cdf.values,
                                linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                                color=SERIES_COLOR,
                                linestyle=GRAPH_STYLES[0],
                                where="post",
                            )
                            ax.plot(
                                cdf.index,
                                cdf.values,
                                linestyle="None",
                                color=SERIES_COLOR,
                                marker=GRAPH_MARKS[change_index % len(GRAPH_MARKS)],
                                markersize=GRAPH_MARKER_SIZES[
                                    change_index % len(GRAPH_MARKER_SIZES)
                                ],
                            )
                            ax.axvline(0, color="black", linewidth=1, alpha=0.35)

                    ax.grid(True, alpha=0.25)

            fig.tight_layout(rect=(0.03, 0.03, 1, 1))
            fig_file = experiment_directory / "figure" / f"t2p-revision-delta-cdf--{tool}--{strategy}.pdf"
            os.makedirs(fig_file.parent, exist_ok=True)
            fig.savefig(fig_file, bbox_inches="tight")
            plt.close(fig)

    if not plotted_any:
        print("No T2P revision delta CDF plots generated.")


if __name__ == "__main__":
    main()
