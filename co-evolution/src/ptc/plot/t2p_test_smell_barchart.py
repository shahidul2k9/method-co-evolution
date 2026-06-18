from __future__ import annotations

import os
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import pandas as pd

from mhc.command_util import (
    load_test_smell_names,
    parse_name_list,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_revision_types,
    resolve_smell_detector,
    select_revision_columns,
)
from ptc.generator.t2p_test_smell_association import OUTPUT_FILE_NAME as ASSOCIATION_OUTPUT_FILE_NAME
from ptc.generator.t2p_test_smell_prevalence import ALL_SMELLS, OUTPUT_FILE_NAME
from ptc.generator.t2p_test_smell_revision import (
    CHANGE_COLUMNS,
    REVISION_GROUP_LABELS,
    REVISION_GROUP_ORDER,
    normalize_revision_group,
)
from ptc.plot.method_history_runtime_table import resolve_path
from ptc.plot.t2p_test_smell_boxplot import GROUP_STYLE_COLORS
from ptc.plot_util import build_experiment_plot_parser


def build_parser():
    parser = build_experiment_plot_parser(
        "Plot aggregate test-smell prevalence by linked revision group.",
        include_projects=False,
        include_revision_types=True,
        include_smell_detector=True,
        include_project_directory=True,
        include_output_directory=True,
    )
    parser.add_argument(
        "--revision-groups",
        dest="revision_groups",
        type=str,
        default=",".join(REVISION_GROUP_ORDER),
        help="Comma-separated revision groups to plot. Defaults to RP,RT,RRT.",
    )
    return parser


def selected_revision_groups(value: str | list[str] | None) -> list[str]:
    selected = [normalize_revision_group(group) for group in (parse_name_list(value) or list(REVISION_GROUP_ORDER))]
    known_groups = set(REVISION_GROUP_ORDER)
    unknown = [group for group in selected if group not in known_groups]
    if unknown:
        raise ValueError(f"Unknown revision group(s): {', '.join(unknown)}")
    return selected


def display_smell(acronym: str, smell_names: dict[str, str]) -> str:
    if acronym == ALL_SMELLS:
        return "All"
    return smell_names.get(acronym, acronym)


def smell_order(frame: pd.DataFrame) -> list[str]:
    counts = (
        frame.groupby("smell", sort=False)["smell_n"].sum().sort_values(ascending=False)
        if not frame.empty
        else pd.Series(dtype=int)
    )
    smells = [smell for smell in counts.index.tolist() if smell != ALL_SMELLS]
    return [ALL_SMELLS, *smells] if ALL_SMELLS in counts.index else smells


def plot_prevalence_axis(
    ax,
    prevalence_df: pd.DataFrame,
    revision_groups: list[str],
    smell_names: dict[str, str],
) -> None:
    if prevalence_df.empty:
        ax.text(0.5, 0.5, "No prevalence data", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return

    smells = smell_order(prevalence_df)
    x = list(range(len(smells)))
    width = 0.8 / max(1, len(revision_groups))
    offsets = [
        (index - (len(revision_groups) - 1) / 2) * width
        for index in range(len(revision_groups))
    ]
    group_column = "rg_group" if "rg_group" in prevalence_df.columns else (
        "group" if "group" in prevalence_df.columns else "revision_group"
    )
    for index, group in enumerate(revision_groups):
        group_df = prevalence_df[prevalence_df[group_column] == group].set_index("smell")
        values = [float(group_df["percent"].get(smell, 0.0)) for smell in smells]
        positions = [value + offsets[index] for value in x]
        bars = ax.bar(
            positions,
            values,
            width=width,
            label=REVISION_GROUP_LABELS.get(group, group),
            color=GROUP_STYLE_COLORS.get(group, None),
            edgecolor="black",
        )
        for bar, percent in zip(bars, values):
            if percent <= 0:
                continue
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height(),
                f"{percent:.1f}%",
                ha="center",
                va="bottom",
                fontsize=8,
                rotation=90,
            )

    ax.set_title("Test-smell prevalence by revision group")
    ax.set_ylabel("Percent")
    ax.set_xticks(x)
    ax.set_xticklabels([display_smell(smell, smell_names) for smell in smells], rotation=45, ha="right")
    ax.legend(frameon=False, fontsize=9)
    ax.grid(True, axis="y", alpha=0.25)


def plot_prevalence(
    prevalence_df: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    change: str,
    revision_groups: list[str],
    smell_names: dict[str, str],
    output_file: Path,
) -> None:
    group_column = "rg_group" if "rg_group" in prevalence_df.columns else (
        "group" if "group" in prevalence_df.columns else "revision_group"
    )
    plot_df = prevalence_df[
        (prevalence_df["strategy"] == strategy)
        & (prevalence_df["tool"] == tool)
        & (prevalence_df["smell_detector"] == smell_detector)
        & (prevalence_df["change"] == change)
        & (prevalence_df[group_column].isin(revision_groups))
    ].copy()
    if "loc_group" in plot_df.columns:
        plot_df = plot_df[plot_df["loc_group"] == "ALL"].copy()
    if plot_df.empty:
        warnings.warn(
            f"Skipping prevalence plot for strategy={strategy}, tool={tool}, "
            f"smell_detector={smell_detector}, change={change}: no rows."
        )
        return

    fig, ax = plt.subplots(figsize=(max(12, len(smell_order(plot_df)) * 1.25), 5))
    plot_prevalence_axis(ax, plot_df, revision_groups, smell_names)
    fig.suptitle(f"Test-smell prevalence for {change}", fontsize=14)
    fig.tight_layout()
    os.makedirs(output_file.parent, exist_ok=True)
    fig.savefig(output_file, bbox_inches="tight")
    plt.close(fig)


def effect_order(frame: pd.DataFrame) -> list[str]:
    return (
        frame[frame["smell"] != ALL_SMELLS]
        .sort_values("difference_pp", ascending=True)["smell"]
        .tolist()
    )


def plot_effect_axis(ax, association_df: pd.DataFrame, smell_names: dict[str, str]) -> None:
    individual = association_df[association_df["smell"] != ALL_SMELLS].sort_values(
        "difference_pp",
        ascending=True,
    )
    if individual.empty:
        ax.text(0.5, 0.5, "No association data", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return

    y = list(range(len(individual)))
    differences = individual["difference_pp"].astype(float).tolist()
    lower = individual["difference_ci_low"].astype(float).tolist()
    upper = individual["difference_ci_high"].astype(float).tolist()
    colors = ["tab:blue" if str(value) == "x" else "0.55" for value in individual["significant"]]
    for position, difference, low, high, color in zip(y, differences, lower, upper, colors):
        ax.errorbar(
            difference,
            position,
            xerr=[[difference - low], [high - difference]],
            fmt="none",
            ecolor=color,
            elinewidth=1.3,
            capsize=3,
            zorder=1,
        )
    ax.scatter(differences, y, c=colors, edgecolor="black", linewidth=0.5, zorder=2)
    ax.axvline(0, color="black", linewidth=0.9, linestyle="--")
    ax.set_yticks(y)
    ax.set_yticklabels([display_smell(smell, smell_names) for smell in individual["smell"]])
    ax.set_xlabel("Prevalence difference: RRT - RP (percentage points)")
    ax.legend(
        handles=[
            Line2D([0], [0], marker="o", color="tab:blue", linestyle="None", label="BH-adjusted p < .05"),
            Line2D([0], [0], marker="o", color="0.55", linestyle="None", label="Not significant"),
        ],
        frameon=False,
        fontsize=8,
        loc="lower right",
    )
    ax.grid(True, axis="x", alpha=0.25)


def plot_effect(
    association_df: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    change: str,
    smell_names: dict[str, str],
    output_file: Path,
) -> None:
    plot_df = association_df[
        (association_df["strategy"] == strategy)
        & (association_df["tool"] == tool)
        & (association_df["smell_detector"] == smell_detector)
        & (association_df["change"] == change)
    ].copy()
    if plot_df.empty:
        return
    summary = plot_df[plot_df["smell"] == ALL_SMELLS]
    summary_text = ""
    if not summary.empty:
        row = summary.iloc[0]
        summary_text = (
            f"Any test smell: RP {row['baseline_percent']:.1f}% vs "
            f"RRT {row['focal_percent']:.1f}% "
            f"({row['difference_pp']:+.1f} pp)"
        )

    fig, ax = plt.subplots(figsize=(7.2, max(5.0, len(effect_order(plot_df)) * 0.32)))
    plot_effect_axis(ax, plot_df, smell_names)
    fig.suptitle("Initial test smells associated with recurrent revision-proneness", fontsize=11)
    if summary_text:
        ax.set_title(summary_text, fontsize=9, loc="left", pad=8)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    os.makedirs(output_file.parent, exist_ok=True)
    fig.savefig(output_file, bbox_inches="tight")
    plt.close(fig)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    project_directory = Path(args.project_directory)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    output_directory = (
        resolve_path(project_directory, args.output_directory, Path())
        if args.output_directory is not None
        else experiment_directory / "figure"
    )
    input_file = experiment_directory / "aggregate" / ASSOCIATION_OUTPUT_FILE_NAME
    if not input_file.exists():
        warnings.warn(f"File not found, skipping: {input_file}")
        return

    selected_tools, _, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_types = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )
    smell_names = load_test_smell_names(smell_detector)
    association_df = pd.read_csv(input_file, keep_default_na=False, na_filter=False)
    if association_df.empty:
        print("No test smell effect plots generated.")
        return

    frame = association_df[association_df["smell_detector"] == smell_detector].copy()
    if "loc_group" in frame.columns:
        frame = frame[frame["loc_group"] == "ALL"].copy()
    if selected_tools is not None:
        frame = frame[frame["tool"].isin(selected_tools)]
    if selected_strategies is not None:
        frame = frame[frame["strategy"].isin(selected_strategies)]
    if revision_types:
        frame = frame[frame["change"].isin(revision_types)]

    plotted_any = False
    combinations = frame[["strategy", "tool", "smell_detector", "change"]].drop_duplicates()
    for row in combinations.itertuples(index=False):
        output_file = (
            output_directory
            / f"t2p-test-smell-effectplot--{row.tool}--{row.strategy}--{row.smell_detector}--{row.change}.pdf"
        )
        plot_effect(
            frame,
            strategy=row.strategy,
            tool=row.tool,
            smell_detector=row.smell_detector,
            change=row.change,
            smell_names=smell_names,
            output_file=output_file,
        )
        if output_file.exists():
            plotted_any = True
            print(f"Wrote {output_file}")

    if not plotted_any:
        print("No test smell effect plots generated.")


if __name__ == "__main__":
    main()
