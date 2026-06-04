from __future__ import annotations

import os
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
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
from ptc.generator.t2p_test_smell_prevalence import ALL_SMELLS, OUTPUT_FILE_NAME
from ptc.generator.t2p_test_smell_revision import CHANGE_COLUMNS, REVISION_GROUP_LABELS, REVISION_GROUP_ORDER
from ptc.plot.t2p_test_smell_boxplot import GROUP_STYLE_COLORS
from ptc.plot_util import build_experiment_plot_parser


def build_parser():
    parser = build_experiment_plot_parser(
        "Plot aggregate test-smell prevalence by linked revision group.",
        include_projects=False,
        include_revision_types=True,
        include_smell_detector=True,
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
    selected = parse_name_list(value) or list(REVISION_GROUP_ORDER)
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
    for index, group in enumerate(revision_groups):
        group_df = prevalence_df[prevalence_df["revision_group"] == group].set_index("smell")
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
    plot_df = prevalence_df[
        (prevalence_df["strategy"] == strategy)
        & (prevalence_df["tool"] == tool)
        & (prevalence_df["smell_detector"] == smell_detector)
        & (prevalence_df["change"] == change)
        & (prevalence_df["revision_group"].isin(revision_groups))
    ].copy()
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


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    input_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    if not input_file.exists():
        warnings.warn(f"File not found, skipping: {input_file}")
        return

    selected_tools, _, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_groups = selected_revision_groups(args.revision_groups)
    revision_types = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )
    smell_names = load_test_smell_names(smell_detector)
    prevalence_df = pd.read_csv(input_file, keep_default_na=False, na_filter=False)
    if prevalence_df.empty:
        print("No test smell prevalence plots generated.")
        return

    frame = prevalence_df[prevalence_df["smell_detector"] == smell_detector].copy()
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
            experiment_directory
            / "figure"
            / f"t2p-test-smell-barchart--{row.tool}--{row.strategy}--{row.smell_detector}--{row.change}.pdf"
        )
        plot_prevalence(
            frame,
            strategy=row.strategy,
            tool=row.tool,
            smell_detector=row.smell_detector,
            change=row.change,
            revision_groups=revision_groups,
            smell_names=smell_names,
            output_file=output_file,
        )
        if output_file.exists():
            plotted_any = True
            print(f"Wrote {output_file}")

    if not plotted_any:
        print("No test smell prevalence plots generated.")


if __name__ == "__main__":
    main()
