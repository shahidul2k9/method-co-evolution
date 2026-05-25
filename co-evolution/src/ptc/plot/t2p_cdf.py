import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
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
    select_revision_columns,
    select_named_items,
)

SERIES_LABELS = {
    "test": "test",
    "production": "production",
}
SERIES_COLORS = {
    "test": "tab:blue",
    "production": "tab:orange",
}

code_shovel_unsupported_change_set = {
    f"ch_{change_type.name.lower()}" for change_type in CODE_SHOVEL_UNSUPPORTED_CHANGES
}


def build_parser():
    return build_experiment_plot_parser("Plot test-to-production CDFs.")


def format_count(value: int) -> str:
    return f"{value:,}"


def format_percent(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def build_project_stats(project_df: pd.DataFrame) -> dict[str, int]:
    total = len(project_df)
    test_count = int(project_df["from_artifact"].astype(str).str.startswith("test").sum())
    production_count = int((project_df["to_artifact"] == "main-code").sum())
    return {"total": total, "test": test_count, "production": production_count}


def draw_row_info_axis(ax, project: str, project_df: pd.DataFrame) -> None:
    stats = build_project_stats(project_df)
    total = stats["total"]
    ax.axis("off")
    ax.text(0.5, 0.92, project, transform=ax.transAxes, va="top", ha="center", fontsize=16, fontweight="bold")
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
    handles = [
        Line2D([0], [0], color=SERIES_COLORS[key], linewidth=GRAPH_WIDTHS[0], linestyle=GRAPH_STYLES[index], label=label)
        for index, (key, label) in enumerate(SERIES_LABELS.items())
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False, fontsize=12, borderaxespad=0, handlelength=2.6)


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

            change_cols = select_revision_columns(
                [c[len("from_"):] for c in df.columns if c.startswith("from_ch_")]
            )
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

            for repository_index, project in enumerate(projects):
                project_df = df if project == ALL_REPOSITORY else df[df["project"] == project]
                draw_row_info_axis(axes[repository_index][0], project, project_df)

                for change_index, change in enumerate(change_cols):
                    ax = axes[repository_index][change_index + 1]
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
                                color=SERIES_COLORS["production"],
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
                                color=SERIES_COLORS["test"],
                                ls=GRAPH_STYLES[1],
                                label="test",
                            )

                        if max_x > 50:
                            ax.set_xscale("log")
                    ax.grid(True, alpha=0.25)

            fig.tight_layout()
            fig_file = experiment_directory / "figure" / f"t2p-cdf--{tool}--{link_strategy}.pdf"
            os.makedirs(os.path.dirname(fig_file), exist_ok=True)
            fig.savefig(fig_file, bbox_inches="tight")
            plt.close(fig)


if __name__ == "__main__":
    main()
