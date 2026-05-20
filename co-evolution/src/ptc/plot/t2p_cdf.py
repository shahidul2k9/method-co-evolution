import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

import mhc.util as util
from mhc.artifacts import artifact_group
from ptc.constants import ALL_REPOSITORY, CODE_SHOVEL_UNSUPPORTED_CHANGES
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

code_shovel_unsupported_change_set = {
    f"ch_{change_type.name.lower()}" for change_type in CODE_SHOVEL_UNSUPPORTED_CHANGES
}


def build_parser():
    return build_experiment_plot_parser("Plot test-to-production CDFs.")


def load_history_repository_dfs(
        experiment_directory: Path,
        tool: str,
        link_strategy: str,
        selected_projects: list[str] | None,
) -> list[pd.DataFrame]:
    csv_files = list_csv_files(
        experiment_directory / "t2p-change" / tool / link_strategy,
        selected_projects,
        strict=False,
    )
    history_repository_dfs = [
        pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False)
        for repository_history_file in csv_files
    ]
    return [df for df in history_repository_dfs if not df.empty]


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        use_filters=args.use_filters,
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )

    tools = select_named_items(
        util.sorted_directory_names(experiment_directory / "t2p-change"),
        selected_tools,
        item_label="tool",
    )

    for tool in tools:
        strategies = select_named_items(
            util.sorted_directory_names(experiment_directory / "t2p-change" / tool),
            selected_strategies,
            item_label="strategy",
        )
        for link_strategy in strategies:
            history_repository_dfs = load_history_repository_dfs(experiment_directory, tool, link_strategy,
                                                                 selected_projects)
            if not history_repository_dfs:
                continue

            df = pd.concat(history_repository_dfs, ignore_index=True)
            print(tool, link_strategy)

            for prefix in ["from_", "to_"]:
                df[f"{prefix}artifact"] = df[f"{prefix}artifact"].map(artifact_group)

            change_cols = [c[len("from_"):] for c in df.columns if c.startswith("from_ch_")]
            projects = select_named_items(
                sorted(df["project"].unique(), key=str.lower),
                selected_projects,
                item_label="project",
                strict=False,
            )
            projects.append(ALL_REPOSITORY)

            fig, axes = plt.subplots(
                len(projects),
                len(change_cols),
                figsize=(4 * len(change_cols), 3.2 * len(projects)),
                squeeze=False,
            )

            for repository_index, project in enumerate(projects):
                project_df = df if project == ALL_REPOSITORY else df[df["project"] == project]

                for change_index, change in enumerate(change_cols):
                    ax = axes[repository_index][change_index]
                    ax.set_title(f"{change.replace('ch_', '')}".capitalize(), fontsize=24)

                    unsupported = tool == "codeShovel" and change in code_shovel_unsupported_change_set
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
                        pair_df = (
                            project_df[[f"to_{change}", f"from_{change}"]]
                            .apply(pd.to_numeric, errors="coerce")
                            .dropna()
                        )
                        production = pair_df[f"to_{change}"]
                        test = pair_df[f"from_{change}"]

                        max_x = 0
                        if not production.empty:
                            x, y = ecdf(production)
                            max_x = max(max_x, max(x))
                            ax.plot(
                                x,
                                y,
                                linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                                ls=GRAPH_STYLES[0],
                                label="production",
                            )

                        if not test.empty:
                            x, y = ecdf(test)
                            max_x = max(max_x, max(x))
                            ax.plot(
                                x,
                                y,
                                linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                                ls=GRAPH_STYLES[1],
                                label="test",
                            )

                        if max_x > 50:
                            ax.set_xscale("log")

                        if change_index == 0:
                            ax.legend(loc="lower right", fontsize=20)

                    if change_index == 0:
                        ax.text(
                            -0.5,
                            0.5,
                            project,
                            transform=ax.transAxes,
                            rotation=90,
                            va="center",
                            ha="center",
                            fontsize=24,
                        )
                    ax.grid(True, alpha=0.25)

            fig.tight_layout()
            fig_file = experiment_directory / "figure" / f"t2p-cdf--{tool}--{link_strategy}.pdf"
            os.makedirs(os.path.dirname(fig_file), exist_ok=True)
            fig.savefig(fig_file, bbox_inches="tight")
            plt.close(fig)


if __name__ == "__main__":
    main()
