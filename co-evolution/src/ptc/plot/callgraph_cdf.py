import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from mhc.config import WORKSPACE_DIRECTORY
from mhc.artifacts import artifact_group
from ptc.constants import ALL_REPOSITORY
from ptc.plot_util import (
    GRAPH_STYLES,
    GRAPH_WIDTHS,
    build_experiment_plot_parser,
    ecdf,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
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
        use_filters=args.use_filters,
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

    df["artifact"] = df["artifact"].map(artifact_group)

    projects = select_named_items(
        sorted(df["project"].unique(), key=str.lower),
        selected_projects,
        item_label="project",
        strict=False,
    )
    projects.append(ALL_REPOSITORY)

    in_out_types = ["fan_in", "fan_out"]
    fig, axes = plt.subplots(
        len(projects),
        len(in_out_types),
        figsize=(4 * len(in_out_types), 3.2 * len(projects)),
        sharey=True,
        squeeze=False,
    )

    for repository_index, project in enumerate(projects):
        project_df = df if project == ALL_REPOSITORY else df[df["project"] == project]

        for change_index, change in enumerate(in_out_types):
            ax = axes[repository_index][change_index]

            for artifact, artifact_df in project_df.groupby("artifact"):
                x, y = ecdf(artifact_df[change])
                ax.plot(
                    x,
                    y,
                    linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                    ls=GRAPH_STYLES[change_index % len(GRAPH_STYLES)],
                    label=artifact,
                )

            ax.set_xscale("log")
            ax.set_xlabel(change.replace("_", " ").capitalize(), fontsize=24)
            if change_index == 0:
                ax.legend(loc="lower right", fontsize=20)
                ax.set_ylabel(project, fontsize=24)
            ax.grid(True, alpha=0.25)

    fig.tight_layout()
    fig_file = f"{WORKSPACE_DIRECTORY}/figure/call-graph-cdf.pdf"
    os.makedirs(os.path.dirname(fig_file), exist_ok=True)
    fig.savefig(fig_file, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
