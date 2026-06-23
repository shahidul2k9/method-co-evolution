import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

import mhc.util as util
from ptc.constants import ALL_REPOSITORY, MethodChangeType
from ptc.plot_util import (
    GRAPH_STYLES,
    GRAPH_WIDTHS,
    build_experiment_plot_parser,
    ecdf,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_revision_columns,
    select_named_items,
)
from ptc.util.helper import (
    REVISION_METHOD_KINDS,
    classify_revision_method_kind,
    join_filtered_artifacts,
)

METHOD_KINDS = REVISION_METHOD_KINDS
METHOD_KIND_LABELS = {
    "test-case-method": "Test Method",
    "main-code": "Production Method",
}
METHOD_KIND_COLORS = {
    "test-case-method": "tab:blue",
    "main-code": "tab:orange",
}
METHOD_KIND_MARKERS = {
    "test-case-method": "D",
    "main-code": "^",
}
PAPER_CHANGE_AXIS_WIDTH = 4.6
DEFAULT_CHANGE_AXIS_WIDTH = 5.5
ROW_INFO_AXIS_WIDTH = 1.8
PAPER_FIGURE_HEIGHT = 3.1
DEFAULT_ROW_HEIGHT = 3.2
PAPER_TICK_FONT_SIZE = 12
DEFAULT_TICK_FONT_SIZE = 13
PAPER_AXIS_LABEL_FONT_SIZE = 14
PAPER_MARK_EVERY = 2
PAPER_MARKER_SIZE = 4.2
PAPER_MAX_REVISION_TICK = 50
PAPER_LEGEND_ANCHOR = (0.58, 0.30)
CHANGE_COLUMN_LABELS = {
    "ch_diff": "ch_diff",
    "ch_all": "All revisions",
}
CHANGE_COLUMNS = [
    "ch_all",
    "ch_diff",
    *[f"ch_{change_type.name.lower()}" for change_type in MethodChangeType],
]


def classify_method_kind(artifact: str | None) -> str | None:
    return classify_revision_method_kind(artifact)


def order_change_columns(columns: list[str], selected_revision_types: str | list[str] | None = None) -> list[str]:
    return select_revision_columns(
        columns,
        selected_revision_types,
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )


def change_column_label(change: str) -> str:
    return CHANGE_COLUMN_LABELS.get(change, f"{change.replace('ch_', '')}".capitalize())


def format_percent(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def format_count(value: int) -> str:
    return f"{value:,}"


def build_project_stats(project_df: pd.DataFrame) -> dict[str, int]:
    total = len(project_df)
    test_count = int((project_df["method_kind"] == "test-case-method").sum())
    production_count = int((project_df["method_kind"] == "main-code").sum())
    return {
        "total": total,
        "test": test_count,
        "production": production_count,
    }


def method_kind_legend_handles() -> list[Line2D]:
    return [
        Line2D(
            [0],
            [0],
            color=METHOD_KIND_COLORS[method_kind],
            linewidth=GRAPH_WIDTHS[0],
            linestyle=GRAPH_STYLES[index % len(GRAPH_STYLES)],
            label=METHOD_KIND_LABELS[method_kind],
        )
        for index, method_kind in enumerate(METHOD_KINDS)
    ]


def draw_row_info_axis(ax, project: str, project_df: pd.DataFrame) -> None:
    stats = build_project_stats(project_df)
    total = stats["total"]
    ax.axis("off")
    ax.text(
        0.0,
        0.92,
        project,
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=16,
        fontweight="bold",
    )
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
        handles=method_kind_legend_handles(),
        loc="lower left",
        frameon=False,
        fontsize=12,
        borderaxespad=0,
        handlelength=2.6,
    )


def build_parser():
    parser = build_experiment_plot_parser(
        "Plot method revision CDFs.",
        include_strategies=False,
        include_revision_types=True,
        include_project_directory=True,
        include_output_directory=True,
    )
    parser.add_argument(
        "--all-projects-only",
        action="store_true",
        help="Generate only the pooled all-projects plot.",
    )
    return parser


def resolve_output_directory(
        project_directory: Path,
        experiment_directory: Path,
        output_directory: str | None,
) -> Path:
    if output_directory is None:
        return experiment_directory / "figure"
    output_path = Path(output_directory)
    return output_path if output_path.is_absolute() else project_directory / output_path


def load_history_repository_dfs(
        experiment_directory: Path,
        tool: str,
        selected_projects: list[str] | None,
) -> list[pd.DataFrame]:
    csv_files = list_csv_files(
        experiment_directory / "method-history" / tool,
        selected_projects,
        strict=False,
    )
    history_repository_dfs = [
        pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False, low_memory=False)
        for repository_history_file in csv_files
    ]
    return [df for df in history_repository_dfs if not df.empty]


def subsequent_revision_series(series: pd.Series) -> pd.Series:
    return (series - 1).clip(lower=0)


def revision_axis_upper_bound(ticks_or_max_revision_count) -> float:
    tick_count = (
        len(ticks_or_max_revision_count)
        if isinstance(ticks_or_max_revision_count, list)
        else len(revision_tick_values(ticks_or_max_revision_count))
    )
    if tick_count <= 1:
        return 1
    return tick_count - 1


def revision_tick_values(max_revision_count: float) -> list[int]:
    if max_revision_count <= 0:
        return [0]

    ticks = [0, 1, 2, 5]
    magnitude = 10
    while ticks[-1] < max_revision_count:
        for multiplier in (1, 2, 5):
            tick = multiplier * magnitude
            if tick not in ticks:
                ticks.append(tick)
            if tick >= max_revision_count:
                return sorted(ticks)
        magnitude *= 10
    return sorted(ticks)


def revision_display_positions(values, ticks: list[int]) -> np.ndarray:
    if len(ticks) <= 1:
        return np.zeros(len(values))
    return np.interp(values, ticks, range(len(ticks)))


def paper_revision_tick_values(max_revision_count: float) -> list[int]:
    return [tick for tick in revision_tick_values(max_revision_count) if tick <= PAPER_MAX_REVISION_TICK]


def displayed_revision_values(values, ticks: list[int], *, paper_mode: bool):
    if paper_mode and ticks:
        return np.minimum(values, ticks[-1])
    return values


def paper_marker_indices(display_x_values) -> list[int]:
    unique_indices = []
    seen_positions = set()
    for index, value in enumerate(display_x_values):
        position = round(float(value), 6)
        if position not in seen_positions:
            unique_indices.append(index)
            seen_positions.add(position)

    if not unique_indices:
        return []

    marker_indices = unique_indices[::PAPER_MARK_EVERY]
    if unique_indices[-1] not in marker_indices:
        marker_indices.append(unique_indices[-1])
    return marker_indices


def plot_change_axis(
        ax,
        project_df: pd.DataFrame,
        change: str,
        change_index: int,
        *,
        paper_mode: bool,
) -> None:
    if paper_mode:
        ax.set_title("")
    else:
        ax.set_title(change_column_label(change), fontsize=24)

    max_revision_count = 0
    revision_lines = []
    for method_kind_index, current_method_kind in enumerate(METHOD_KINDS):
        change_series = pd.to_numeric(
            project_df[project_df["method_kind"] == current_method_kind][change],
            errors="coerce",
        ).dropna()
        if change_series.empty:
            continue

        revisions = subsequent_revision_series(change_series)
        if not revisions.empty:
            max_revision_count = max(max_revision_count, revisions.max())
        revision_lines.append((method_kind_index, current_method_kind, revisions))

    ticks = paper_revision_tick_values(max_revision_count) if paper_mode else revision_tick_values(max_revision_count)
    for method_kind_index, current_method_kind, revisions in revision_lines:
        x, y = ecdf(revisions)
        display_x = revision_display_positions(
            displayed_revision_values(x, ticks, paper_mode=paper_mode),
            ticks,
        )
        ax.plot(
            display_x,
            y,
            linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
            color=METHOD_KIND_COLORS[current_method_kind],
            ls=GRAPH_STYLES[method_kind_index % len(GRAPH_STYLES)],
            marker=METHOD_KIND_MARKERS[current_method_kind] if paper_mode else None,
            markevery=paper_marker_indices(display_x) if paper_mode else None,
            markersize=PAPER_MARKER_SIZE if paper_mode else None,
            label=METHOD_KIND_LABELS[current_method_kind],
        )

    ax.set_xlim(0, revision_axis_upper_bound(ticks))
    ax.set_xticks(range(len(ticks)))
    ax.set_xticklabels([str(tick) for tick in ticks])
    ax.set_xlabel(
        "# Method Revisions",
        fontsize=PAPER_AXIS_LABEL_FONT_SIZE if paper_mode else None,
    )
    ax.set_ylabel(
        "CDF",
        fontsize=PAPER_AXIS_LABEL_FONT_SIZE if paper_mode else None,
    )
    ax.tick_params(
        axis="both",
        labelsize=PAPER_TICK_FONT_SIZE if paper_mode else DEFAULT_TICK_FONT_SIZE,
    )
    if paper_mode:
        ax.set_yticks(np.arange(0, 1.01, 0.1))
        ax.legend(
            handles=method_kind_legend_handles(),
            loc="center",
            bbox_to_anchor=PAPER_LEGEND_ANCHOR,
            frameon=True,
            fontsize=10,
            borderaxespad=0.4,
            handlelength=2.4,
        )

    ax.grid(True, alpha=0.25)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    project_directory = Path(args.project_directory)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    output_directory = resolve_output_directory(
        project_directory,
        experiment_directory,
        args.output_directory,
    )
    selected_tools, selected_projects, _ = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
    )

    method_history_directory = experiment_directory / "method-history"
    tools = select_named_items(
        util.sorted_directory_names(method_history_directory),
        selected_tools,
        item_label="tool",
    )
    if not tools:
        print("No method-history tools found.")
        return

    plotted_any_tool = False
    for tool in tools:
        history_repository_dfs = load_history_repository_dfs(experiment_directory, tool, selected_projects)
        if not history_repository_dfs:
            print(f"No method-history CSV files found for {tool}.")
            continue

        df = pd.concat(history_repository_dfs, ignore_index=True)
        if df.empty:
            print(f"No method-history data available to plot for {tool}.")
            continue

        df = join_filtered_artifacts(df, experiment_directory)
        if df.empty:
            print(f"No test-case or main-code method-history data available to plot for {tool}.")
            continue

        change_cols = order_change_columns(
            [c for c in df.columns if c.startswith("ch_")],
            args.revision_types,
        )
        if not change_cols:
            print(f"No ch_* revision columns found for {tool}.")
            continue

        print(tool)
        plotted_any_tool = True
        projects = select_named_items(
            list(dict.fromkeys(df["project"].dropna())),
            selected_projects,
            item_label="project",
            strict=False,
        )
        projects = [ALL_REPOSITORY] if args.all_projects_only else [*projects, ALL_REPOSITORY]

        if args.all_projects_only:
            fig, axes = plt.subplots(
                1,
                len(change_cols),
                figsize=(PAPER_CHANGE_AXIS_WIDTH * len(change_cols), PAPER_FIGURE_HEIGHT),
                squeeze=False,
            )
        else:
            fig, axes = plt.subplots(
                len(projects),
                len(change_cols) + 1,
                figsize=(ROW_INFO_AXIS_WIDTH + DEFAULT_CHANGE_AXIS_WIDTH * len(change_cols), DEFAULT_ROW_HEIGHT * len(projects)),
                gridspec_kw={"width_ratios": [1.4, *([DEFAULT_CHANGE_AXIS_WIDTH] * len(change_cols))]},
                squeeze=False,
            )

        for repository_index, project in enumerate(projects):
            project_df = df if project == ALL_REPOSITORY else df[df["project"] == project]
            if not args.all_projects_only:
                draw_row_info_axis(axes[repository_index][0], project, project_df)

            for change_index, change in enumerate(change_cols):
                ax = axes[repository_index][change_index if args.all_projects_only else change_index + 1]
                plot_change_axis(
                    ax,
                    project_df,
                    change,
                    change_index,
                    paper_mode=args.all_projects_only,
                )

        fig.tight_layout()
        fig_file = output_directory / f"artifact-revision-cdf--{tool}.pdf"
        os.makedirs(os.path.dirname(fig_file), exist_ok=True)
        fig.savefig(fig_file, bbox_inches="tight")
        plt.close(fig)

    if not plotted_any_tool:
        print("No revision CDFs generated.")


if __name__ == "__main__":
    main()
