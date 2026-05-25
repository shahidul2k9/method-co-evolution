import os
from pathlib import Path
import warnings
from dataclasses import dataclass

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator, NullFormatter
import pandas as pd

import mhc.util as util
from mhc.artifacts import is_main_code, is_test_case_method, is_test_code
from mhc.command_util import non_negative_int, resolve_min_t2p_links
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
SYMLIN_THRESHOLD = 10
SYMLIN_TICKS = [-100, -50, -10, -5, -1, 1, 5, 10, 50, 100]


@dataclass(frozen=True)
class DeltaThreshold:
    x: int
    covered_pct: float
    tail_pct: float


def build_parser():
    parser = build_experiment_plot_parser("Plot test-minus-production revision delta CDFs.")
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum linked test-production pairs required before revision delta CDFs are plotted. Defaults to ME_MIN_T2P_LINKS.",
    )
    return parser


def format_count(value: int) -> str:
    return f"{value:,}"


def format_percent(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def format_revision_tick(value: float, _: int) -> str:
    if abs(value - round(value)) > 1e-9:
        return ""
    return format_count(int(round(value)))


def revision_axis_ticks(min_x: int, max_x: int) -> list[int]:
    return [tick for tick in SYMLIN_TICKS if min_x <= tick <= max_x]


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
        handles=[
            Line2D(
                [0],
                [0],
                color=SERIES_COLOR,
                linewidth=GRAPH_WIDTHS[0],
                linestyle=GRAPH_STYLES[0],
                label="test - production CDF",
            )
        ],
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


def delta_series(df: pd.DataFrame, change: str) -> pd.Series:
    pair_df = (
        df[[f"to_{change}", f"from_{change}"]]
        .apply(pd.to_numeric, errors="coerce")
        .dropna()
    )

    if pair_df.empty:
        return pd.Series(dtype="int64")

    return (pair_df[f"from_{change}"] - pair_df[f"to_{change}"]).astype("int64")


def delta_cdf(df: pd.DataFrame, change: str) -> pd.Series:
    delta = delta_series(df, change)

    if delta.empty:
        return pd.Series(dtype="float64")

    frequencies = delta.value_counts().sort_index()
    frequencies = frequencies.reindex(
        range(int(frequencies.index.min()), int(frequencies.index.max()) + 1),
        fill_value=0,
    )
    return frequencies.cumsum() / frequencies.sum()


def delta_threshold(df: pd.DataFrame, change: str, coverage: float = 0.8) -> DeltaThreshold | None:
    delta = delta_series(df, change)
    if delta.empty:
        return None

    frequencies = delta.value_counts().sort_index()
    cumulative = frequencies.cumsum() / frequencies.sum()
    threshold_x = int(cumulative[cumulative >= coverage].index[0])
    covered_pct = float((delta <= threshold_x).mean() * 100)
    tail_pct = float((delta >= threshold_x).mean() * 100)
    return DeltaThreshold(threshold_x, covered_pct, tail_pct)


def style_delta_axis(ax, cdf: pd.Series) -> None:
    min_x = int(cdf.index.min())
    max_x = int(cdf.index.max())
    if min_x < -SYMLIN_THRESHOLD or max_x > SYMLIN_THRESHOLD:
        ax.set_xscale("symlog", linthresh=SYMLIN_THRESHOLD)
        ticks = revision_axis_ticks(min_x, max_x)
        if ticks:
            ax.set_xticks(ticks)
        ax.set_xticks([], minor=True)
        ax.xaxis.set_major_formatter(FuncFormatter(format_revision_tick))
        ax.xaxis.set_minor_formatter(NullFormatter())
        ax.axvline(-SYMLIN_THRESHOLD, color="gray", linewidth=1, linestyle="--", alpha=0.3)
        ax.axvline(SYMLIN_THRESHOLD, color="gray", linewidth=1, linestyle="--", alpha=0.3)

    ax.axvline(0, color="black", linewidth=1.2, alpha=0.45)


def draw_delta_threshold(ax, threshold: DeltaThreshold) -> None:
    if threshold.x != 0:
        ax.axvline(threshold.x, color="purple", linewidth=1.2, linestyle=":", alpha=0.55)
    ax.text(
        0.98,
        0.08,
        f"{threshold.covered_pct:.1f}% <= {threshold.x}\n{threshold.tail_pct:.1f}% >= {threshold.x}",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8,
        color="purple",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 1.5},
    )


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
    min_t2p_links = args.min_t2p_links

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
            projects = select_named_items(
                list(dict.fromkeys(df["project"].dropna())),
                selected_projects,
                item_label="project",
                strict=False,
            )
            projects_to_plot = []
            for project in projects:
                project_size = len(df[df["project"] == project])
                if project_size < min_t2p_links:
                    warnings.warn(
                        f"Skipping T2P revision delta CDF for project={project}, tool={tool}, strategy={strategy}: "
                        f"t2p_links={project_size} is below min_t2p_links={min_t2p_links}."
                    )
                    continue
                projects_to_plot.append(project)

            all_size = len(df)
            if all_size >= min_t2p_links:
                projects_to_plot.append(ALL_REPOSITORY)
            else:
                warnings.warn(
                    f"Skipping T2P revision delta CDF for project={ALL_REPOSITORY}, tool={tool}, strategy={strategy}: "
                    f"t2p_links={all_size} is below min_t2p_links={min_t2p_links}."
                )

            if not projects_to_plot:
                continue

            plotted_any = True

            fig, axes = plt.subplots(
                len(projects_to_plot),
                len(change_cols) + 1,
                figsize=(1.8 + 4 * len(change_cols), 3.2 * len(projects_to_plot)),
                gridspec_kw={"width_ratios": [1.4, *([4] * len(change_cols))]},
                squeeze=False,
            )
            fig.supxlabel("test - production revisions (linear -10..10, log outside)", fontsize=20)
            fig.supylabel("CDF", fontsize=20)

            for project_index, project in enumerate(projects_to_plot):
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
                            if len(change_cols) > 1:
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
                            style_delta_axis(ax, cdf)
                            threshold = delta_threshold(project_df, change)
                            if threshold is not None:
                                draw_delta_threshold(ax, threshold)

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
