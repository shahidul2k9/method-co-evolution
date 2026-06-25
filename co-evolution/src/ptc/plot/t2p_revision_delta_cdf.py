import os
from pathlib import Path
import warnings
from dataclasses import dataclass

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter, MultipleLocator, NullFormatter
import pandas as pd

import mhc.util as util
from mhc.artifacts import is_main_code, is_test_case_method, is_test_code
from mhc.command_util import non_negative_int, resolve_min_t2p_links
from ptc.constants import ALL_REPOSITORY, CODE_SHOVEL_UNSUPPORTED_CHANGES, MethodChangeType
from ptc.plot_util import (
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
SYMLIN_THRESHOLD = 10
SYMLIN_TICKS = [-100, -50, -10, -5, -1, 1, 5, 10, 50, 100]
PAPER_MIN_DELTA = -10
PAPER_MAX_DELTA = 5
PAPER_MAX_DISPLAY_DELTA = 10
PAPER_SERIES_COLOR = "#1f77b4"
PAPER_THRESHOLD_COLOR = "#d62728"
PAPER_LABEL_SIZE = 16
PAPER_TICK_LABEL_SIZE = 14

REVISION_DELTA_GROUPS = [
    ("NTR", "<=0", lambda delta: delta <= 0),
    ("ATR", "1-4", lambda delta: (delta >= 1) & (delta < PAPER_MAX_DELTA)),
    ("HTR", "5+", lambda delta: delta >= PAPER_MAX_DELTA),
]


@dataclass(frozen=True)
class DeltaThreshold:
    x: int
    covered_pct: float
    tail_pct: float


def build_parser():
    parser = build_experiment_plot_parser(
        "Plot test-minus-production revision delta CDFs.",
        include_revision_types=True,
        include_project_directory=True,
        include_output_directory=True,
    )
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum linked test-production pairs required before revision delta CDFs are plotted. Defaults to ME_MIN_T2P_LINKS.",
    )
    parser.add_argument(
        "--all-projects-only",
        action="store_true",
        help="Generate only the paper-ready all-projects revision delta CDF.",
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
            ]
        ),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=13,
        linespacing=1.2,
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


def resolve_output_directory(
    project_directory: Path,
    experiment_directory: Path,
    output_directory: str | None,
) -> Path:
    if output_directory is None:
        return experiment_directory / "figure"
    output_path = Path(output_directory)
    return output_path if output_path.is_absolute() else project_directory / output_path


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


def clipped_delta_cdf(delta: pd.Series) -> pd.Series:
    if delta.empty:
        return pd.Series(dtype="float64")

    clipped_delta = delta.clip(lower=PAPER_MIN_DELTA, upper=PAPER_MAX_DISPLAY_DELTA)
    frequencies = clipped_delta.value_counts().sort_index()
    frequencies = frequencies.reindex(range(PAPER_MIN_DELTA, PAPER_MAX_DISPLAY_DELTA + 1), fill_value=0)
    return frequencies.cumsum() / frequencies.sum()


def revision_delta_group_counts(delta: pd.Series) -> list[tuple[str, str, int, float]]:
    total = len(delta)
    groups = []
    for code, label, mask_fn in REVISION_DELTA_GROUPS:
        count = int(mask_fn(delta).sum()) if total else 0
        percent = (count / total) * 100 if total else 0.0
        groups.append((code, label, count, percent))
    return groups


def format_paper_delta_tick(value: float, _: int) -> str:
    if abs(value - round(value)) > 1e-9:
        return ""
    tick = int(round(value))
    if tick == PAPER_MIN_DELTA:
        return f"{PAPER_MIN_DELTA}"
    if tick == PAPER_MAX_DISPLAY_DELTA:
        return f"{PAPER_MAX_DISPLAY_DELTA}"
    return str(tick)


def draw_revision_group_summary(ax, delta: pd.Series) -> None:
    summary_lines = [
        f"{code} ({label}): {format_count(count)} ({percent:.1f}%)"
        for code, label, count, percent in revision_delta_group_counts(delta)
    ]
    ax.text(
        0.03,
        0.97,
        "\n".join(summary_lines),
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=10,
        bbox={"facecolor": "white", "edgecolor": "0.75", "alpha": 0.85, "pad": 3},
    )


def plot_paper_delta_axis(ax, df: pd.DataFrame, change: str, *, show_group_summary: bool = True) -> None:
    delta = delta_series(df, change)
    if delta.empty:
        ax.text(0.5, 0.5, "No data", ha="center", va="center", fontsize=14, transform=ax.transAxes)
        return

    cdf = clipped_delta_cdf(delta)
    ax.step(
        cdf.index,
        cdf.values,
        linewidth=1.8,
        color=PAPER_SERIES_COLOR,
        linestyle="-",
        where="post",
    )
    ax.axvline(0, color="0.2", linewidth=1.0, alpha=0.45)
    ax.axvline(PAPER_MAX_DELTA, color=PAPER_THRESHOLD_COLOR, linewidth=1.2, linestyle=":", alpha=0.65)
    if show_group_summary:
        draw_revision_group_summary(ax, delta)

    ax.set_xlabel("# Test - Production Revisions", fontsize=PAPER_LABEL_SIZE)
    ax.set_ylabel("CDF", fontsize=PAPER_LABEL_SIZE)
    ax.set_xlim(PAPER_MIN_DELTA, PAPER_MAX_DISPLAY_DELTA)
    ax.set_ylim(0.0, 1.02)
    ax.xaxis.set_major_locator(MultipleLocator(2))
    ax.xaxis.set_major_formatter(FuncFormatter(format_paper_delta_tick))
    ax.yaxis.set_major_locator(FixedLocator(np.arange(0.1, 1.1, 0.1)))
    ax.tick_params(axis="both", labelsize=PAPER_TICK_LABEL_SIZE)
    ax.grid(True, alpha=0.25)


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
    experiment_paths = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    )
    experiment_directory = experiment_paths.experiment_directory
    project_directory = Path(args.project_directory)
    output_directory = resolve_output_directory(
        project_directory,
        experiment_directory,
        args.output_directory,
    )
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
            if args.all_projects_only:
                change_cols = select_revision_columns(change_cols, args.revision_types)
            if not change_cols:
                print(f"No from_ch_* columns found for {tool} {strategy}.")
                continue

            print(tool, strategy)
            if args.all_projects_only:
                all_size = len(df)
                if all_size < min_t2p_links:
                    warnings.warn(
                        f"Skipping T2P revision delta CDF for project={ALL_REPOSITORY}, tool={tool}, strategy={strategy}: "
                        f"t2p_links={all_size} is below min_t2p_links={min_t2p_links}."
                    )
                    continue

                plotted_any = True
                fig, axes = plt.subplots(
                    1,
                    len(change_cols),
                    figsize=(5.8 * len(change_cols), 4.2),
                    squeeze=False,
                )
                for change_index, change in enumerate(change_cols):
                    ax = axes[0][change_index]
                    if len(change_cols) > 1:
                        ax.set_title(format_change_name(change), fontsize=14)
                    plot_paper_delta_axis(ax, df, change)

                fig.tight_layout()
                fig_file = output_directory / f"t2p-revision-delta-cdf--{tool}--{strategy}.pdf"
                os.makedirs(fig_file.parent, exist_ok=True)
                fig.savefig(fig_file, bbox_inches="tight")
                plt.close(fig)
                continue

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
                figsize=(2.2 + 5.4 * len(change_cols), 3.2 * len(projects_to_plot)),
                gridspec_kw={"width_ratios": [1.8, *([5.4] * len(change_cols))]},
                squeeze=False,
            )
            fig.supxlabel("# Test - Production Revisions", fontsize=20)
            fig.supylabel("CDF", fontsize=20)

            for project_index, project in enumerate(projects_to_plot):
                project_df = df if project == ALL_REPOSITORY else df[df["project"] == project]
                draw_row_info_axis(axes[project_index][0], project_df=project_df, project=project)

                for change_index, change in enumerate(change_cols):
                    ax = axes[project_index][change_index + 1]
                    ax.set_title(format_change_name(change), fontsize=18)
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
                            plot_paper_delta_axis(ax, project_df, change, show_group_summary=True)

            fig.tight_layout(rect=(0.03, 0.03, 1, 1))
            fig_file = output_directory / f"t2p-revision-delta-cdf--{tool}--{strategy}.pdf"
            os.makedirs(fig_file.parent, exist_ok=True)
            fig.savefig(fig_file, bbox_inches="tight")
            plt.close(fig)

    if not plotted_any:
        print("No T2P revision delta CDF plots generated.")


if __name__ == "__main__":
    main()
