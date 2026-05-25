import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

from mhc.artifacts import artifact_group
from ptc.constants import ALL_REPOSITORY
from ptc.plot_util import (
    GRAPH_STYLES,
    GRAPH_WIDTHS,
    build_experiment_plot_parser,
    ecdf,
    filter_artifact_dataframe,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)


def format_count(value: int) -> str:
    return f"{value:,}"


def format_percent(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def artifact_color_map(artifacts: list[str]) -> dict[str, str]:
    colors = plt.rcParams["axes.prop_cycle"].by_key()["color"]
    return {artifact: colors[index % len(colors)] for index, artifact in enumerate(artifacts)}


def draw_row_info_axis(ax, project: str, project_df: pd.DataFrame, artifacts: list[str], colors: dict[str, str]) -> None:
    total = len(project_df)
    ax.axis("off")
    ax.text(
        0.5,
        0.92,
        project,
        transform=ax.transAxes,
        va="top",
        ha="center",
        fontsize=16,
        fontweight="bold",
    )
    stat_lines = [f"total={format_count(total)}"]
    for artifact in artifacts:
        count = int((project_df["artifact"] == artifact).sum())
        stat_lines.append(f"{artifact}={format_count(count)} ({format_percent(count, total)})")
    ax.text(
        0.0,
        0.82,
        "\n".join(stat_lines),
        transform=ax.transAxes,
        va="top",
        ha="left",
        fontsize=12,
        linespacing=1.2,
    )
    legend_handles = [
        Line2D([0], [0], color=colors[artifact], linewidth=GRAPH_WIDTHS[0], linestyle=GRAPH_STYLES[0], label=artifact)
        for artifact in artifacts
    ]
    ax.legend(
        handles=legend_handles,
        loc="lower left",
        frameon=False,
        fontsize=11,
        borderaxespad=0,
        handlelength=2.6,
    )


def build_parser():
    return build_experiment_plot_parser(
        "Plot call graph CDFs.",
        include_tools=False,
        include_strategies=False,
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    _, selected_projects, _ = resolve_experiment_filters(
        projects=args.projects,
    )

    csv_files = list_csv_files(
        experiment_directory / "callgraph-degree",
        selected_projects,
        strict=False,
    )
    if not csv_files:
        print("No call graph CSV files found.")
        return

    df = pd.concat(
        [pd.read_csv(file, keep_default_na=False, na_filter=False) for file in csv_files],
        ignore_index=True,
    )
    if df.empty:
        print("No call graph data available to plot.")
        return

    df = filter_artifact_dataframe(df)
    df["artifact"] = df["artifact"].map(artifact_group)

    projects = select_named_items(
        list(dict.fromkeys(df["project"].dropna())),
        selected_projects,
        item_label="project",
        strict=False,
    )
    projects.append(ALL_REPOSITORY)
    artifacts = sorted(df["artifact"].dropna().unique(), key=str.lower)
    artifact_colors = artifact_color_map(artifacts)

    in_out_types = ["fan_in", "fan_out"]
    fig, axes = plt.subplots(
        len(projects),
        len(in_out_types) + 1,
        figsize=(1.8 + 4 * len(in_out_types), 3.2 * len(projects)),
        gridspec_kw={"width_ratios": [1.4, *([4] * len(in_out_types))]},
        sharey=True,
        squeeze=False,
    )

    for repository_index, project in enumerate(projects):
        project_df = df if project == ALL_REPOSITORY else df[df["project"] == project]
        draw_row_info_axis(axes[repository_index][0], project, project_df, artifacts, artifact_colors)

        for change_index, change in enumerate(in_out_types):
            ax = axes[repository_index][change_index + 1]

            for artifact, artifact_df in project_df.groupby("artifact"):
                x, y = ecdf(artifact_df[change])
                ax.plot(
                    x,
                    y,
                    linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                    color=artifact_colors[artifact],
                    ls=GRAPH_STYLES[change_index % len(GRAPH_STYLES)],
                    label=artifact,
                )

            ax.set_xscale("log")
            ax.set_xlabel(change.replace("_", " ").capitalize(), fontsize=24)
            ax.grid(True, alpha=0.25)

    fig.tight_layout()
    fig_file = experiment_directory / "figure" / "artifact-callgraph-cdf.pdf"
    os.makedirs(os.path.dirname(fig_file), exist_ok=True)
    fig.savefig(fig_file, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
