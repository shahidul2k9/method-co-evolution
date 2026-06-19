import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

import mhc.util as util
from mhc.artifacts import is_main_code, is_test_code
from ptc.constants import ALL_REPOSITORY, MethodChangeType
from ptc.plot_util import (
    GRAPH_STYLES,
    GRAPH_WIDTHS,
    build_experiment_plot_parser,
    ecdf,
    filter_artifact_dataframe,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_revision_columns,
    select_named_items,
)
from ptc.util.helper import filter_concrete_methods

METHOD_KINDS = ["test-code", "main-code"]
METHOD_KIND_LABELS = {
    "test-code": "Test Method",
    "main-code": "Production Method",
}
METHOD_KIND_COLORS = {
    "test-code": "tab:blue",
    "main-code": "tab:orange",
}
PAPER_REVISION_CLIP_MAX = 10
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
    if is_test_code(artifact):
        return "test-code"
    if is_main_code(artifact):
        return "main-code"
    return None


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
    test_count = int((project_df["method_kind"] == "test-code").sum())
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


def clipped_ecdf(series: pd.Series, max_revision_count: int) -> tuple[pd.Series, pd.Series]:
    return ecdf(series.clip(upper=max_revision_count))


def subsequent_revision_series(series: pd.Series) -> pd.Series:
    return (series - 1).clip(lower=0)


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

    for method_kind_index, current_method_kind in enumerate(METHOD_KINDS):
        change_series = pd.to_numeric(
            project_df[project_df["method_kind"] == current_method_kind][change],
            errors="coerce",
        ).dropna()
        if change_series.empty:
            continue

        x, y = clipped_ecdf(subsequent_revision_series(change_series), PAPER_REVISION_CLIP_MAX)
        ax.plot(
            x,
            y,
            linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
            color=METHOD_KIND_COLORS[current_method_kind],
            ls=GRAPH_STYLES[method_kind_index % len(GRAPH_STYLES)],
            label=METHOD_KIND_LABELS[current_method_kind],
        )

    ax.set_xlim(0, PAPER_REVISION_CLIP_MAX)
    ax.set_xticks(range(0, PAPER_REVISION_CLIP_MAX + 1))
    ax.set_xticklabels(
        [
            f"{PAPER_REVISION_CLIP_MAX}+"
            if tick == PAPER_REVISION_CLIP_MAX
            else str(tick)
            for tick in range(0, PAPER_REVISION_CLIP_MAX + 1)
        ]
    )
    ax.set_xlabel("# Method Revisions")
    ax.set_ylabel("CDF")
    if paper_mode:
        ax.legend(
            handles=method_kind_legend_handles(),
            loc="center",
            bbox_to_anchor=(0.38, 0.30),
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

        df = filter_artifact_dataframe(df)
        df = filter_concrete_methods(df)
        df["method_kind"] = df["artifact"].map(classify_method_kind)
        df = df[df["method_kind"].isin(METHOD_KINDS)]
        if df.empty:
            print(f"No test-code or main-code method-history data available to plot for {tool}.")
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
                figsize=(4.8 * len(change_cols), 3.1),
                squeeze=False,
            )
        else:
            fig, axes = plt.subplots(
                len(projects),
                len(change_cols) + 1,
                figsize=(1.8 + 4 * len(change_cols), 3.2 * len(projects)),
                gridspec_kw={"width_ratios": [1.4, *([4] * len(change_cols))]},
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
