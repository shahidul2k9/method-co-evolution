from __future__ import annotations

import os
import warnings
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import MultipleLocator
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
from ptc.generator.t2p_test_smell_prevalence import (
    ALL_SMELLS,
    ANY_SMELL,
    NO_SMELL,
    OUTPUT_FILE_NAME,
    PSEUDO_SMELLS,
)
from ptc.generator.t2p_test_smell_revision import (
    CHANGE_COLUMNS,
    REVISION_GROUP_LABELS,
    REVISION_GROUP_ORDER,
    REVISION_GROUP_1,
    REVISION_GROUP_2,
    REVISION_GROUP_3,
    normalize_revision_group,
)
from ptc.plot.method_history_runtime_table import resolve_path
from ptc.plot.t2p_test_smell_boxplot import GROUP_STYLE_COLORS
from ptc.plot_util import build_experiment_plot_parser

SIGNIFICANT_MARKER = "D"
NONSIGNIFICANT_MARKER = "o"
PRIMARY_EFFECT_PAIR = (REVISION_GROUP_3, REVISION_GROUP_1)
EFFECT_COMPARISON_STYLES = {
    (REVISION_GROUP_3, REVISION_GROUP_1): {
        "marker": "D",
        "color": "#1f77b4",
        "linestyle": "-",
        "label": "HTR - NTR",
    },
    (REVISION_GROUP_2, REVISION_GROUP_1): {
        "marker": "s",
        "color": "#d55e00",
        "linestyle": "--",
        "label": "MTR - NTR",
    },
    ("MHTR", REVISION_GROUP_1): {
        "marker": "^",
        "color": "#009e73",
        "linestyle": "-.",
        "label": "MHTR - NTR",
    },
}
EFFECT_XTICK_FONTSIZE = 13
EFFECT_YTICK_FONTSIZE = 9
EFFECT_LEGEND_FONTSIZE = 8.5
EFFECT_X_AXIS_LABEL = "Initial Test-Smell Difference with 95% CI (%)"
EFFECT_Y_AXIS_LABEL = "Test Smell Type"
EFFECT_X_AXIS_MIN = -4
EFFECT_X_AXIS_MAX = 20
EFFECT_MATCHED_XTICK_FONTSIZE = EFFECT_XTICK_FONTSIZE + 2
EFFECT_MATCHED_AXIS_LABEL_FONTSIZE = EFFECT_XTICK_FONTSIZE + 1
EFFECT_MATCHED_CI_LINEWIDTH = 2.6
EFFECT_MATCHED_CI_CAP_LINEWIDTH = 2.0
EFFECT_MATCHED_CI_CAP_HALF_HEIGHT = 0.07
EFFECT_MATCHED_MARKER_SIZE = 58


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
        help="Comma-separated revision groups to plot. Defaults to NTR,MTR,HTR.",
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
    if acronym in {ALL_SMELLS, ANY_SMELL}:
        return "Any smell"
    if acronym == NO_SMELL:
        return "No smell"
    return smell_names.get(acronym, acronym)


def smell_order(frame: pd.DataFrame) -> list[str]:
    counts = (
        frame.groupby("smell", sort=False)["smell_n"].sum().sort_values(ascending=False)
        if not frame.empty
        else pd.Series(dtype=int)
    )
    pseudo_order = [smell for smell in [ANY_SMELL, ALL_SMELLS, NO_SMELL] if smell in counts.index]
    smells = [smell for smell in counts.index.tolist() if smell not in {ANY_SMELL, ALL_SMELLS, NO_SMELL}]
    return [*pseudo_order, *smells]


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


def comparison_pair(row: pd.Series) -> tuple[str, str]:
    return normalize_revision_group(row["focal_group"]), normalize_revision_group(row["baseline_group"])


def comparison_label(pair: tuple[str, str]) -> str:
    style = EFFECT_COMPARISON_STYLES.get(pair)
    if style is not None:
        return str(style["label"])
    return f"{pair[0]} - {pair[1]}"


def comparison_style(pair: tuple[str, str]) -> dict[str, str]:
    return {
        "marker": "o",
        "color": "black",
        "linestyle": "-.",
        "label": comparison_label(pair),
        **EFFECT_COMPARISON_STYLES.get(pair, {}),
    }


def comparison_pairs(frame: pd.DataFrame) -> list[tuple[str, str]]:
    if frame.empty:
        return []
    pairs = [comparison_pair(row) for _, row in frame[["focal_group", "baseline_group"]].drop_duplicates().iterrows()]
    preferred = [pair for pair in EFFECT_COMPARISON_STYLES if pair in pairs]
    remaining = [pair for pair in pairs if pair not in preferred]
    return [*preferred, *remaining]


def effect_order(frame: pd.DataFrame, primary_pair: tuple[str, str] = PRIMARY_EFFECT_PAIR) -> list[str]:
    individual = frame[~frame["smell"].isin(PSEUDO_SMELLS)].copy()
    if individual.empty:
        return []

    individual["_pair"] = individual.apply(comparison_pair, axis=1)
    primary = individual[individual["_pair"] == primary_pair]
    sort_frame = primary if not primary.empty else individual[individual["_pair"] == comparison_pairs(individual)[0]]
    return (
        sort_frame.sort_values("difference_pp", ascending=True)
        .drop_duplicates("smell")["smell"]
        .tolist()
    )


def format_any_smell_summary(association_df: pd.DataFrame) -> str:
    summary = association_df[association_df["smell"] == ANY_SMELL]
    if summary.empty:
        summary = association_df[association_df["smell"] == ALL_SMELLS]
    if summary.empty:
        return ""
    lines = []
    for pair in comparison_pairs(summary):
        pair_df = summary[summary.apply(lambda row: comparison_pair(row) == pair, axis=1)]
        if pair_df.empty:
            continue
        row = pair_df.iloc[0]
        lines.append(
            f"Any test smell: {pair[1]} {float(row['baseline_percent']):.1f}% vs "
            f"{pair[0]} {float(row['focal_percent']):.1f}% "
            f"({float(row['difference_pp']):+.1f} pp)"
        )
    return "\n".join(lines)


def draw_horizontal_ci(
    ax,
    y: float,
    low: float,
    high: float,
    *,
    color: str,
    linestyle: str,
    linewidth: float = 1.4,
    cap_linewidth: float = 1.1,
    cap_half_height: float = 0.045,
) -> None:
    ax.hlines(y, low, high, colors=color, linestyles=linestyle, linewidth=linewidth, zorder=1)
    ax.vlines([low, high], y - cap_half_height, y + cap_half_height, colors=color, linewidth=cap_linewidth, zorder=1)


def plot_effect_axis(ax, association_df: pd.DataFrame, smell_names: dict[str, str]) -> None:
    individual = association_df[~association_df["smell"].isin(PSEUDO_SMELLS)].copy()
    if individual.empty:
        ax.text(0.5, 0.5, "No association data", ha="center", va="center", transform=ax.transAxes)
        ax.axis("off")
        return

    smells = effect_order(individual)
    y_by_smell = {smell: index for index, smell in enumerate(smells)}
    pairs = comparison_pairs(individual)
    offsets = {pair: 0.0 for pair in pairs}
    if len(pairs) > 1:
        step = 0.22
        offsets = {pair: (index - (len(pairs) - 1) / 2) * step for index, pair in enumerate(pairs)}

    individual["_pair"] = individual.apply(comparison_pair, axis=1)
    for pair in pairs:
        style = comparison_style(pair)
        pair_df = individual[individual["_pair"] == pair].set_index("smell")
        for smell in smells:
            if smell not in pair_df.index:
                continue
            row = pair_df.loc[smell]
            y_position = y_by_smell[smell] + offsets[pair]
            difference = float(row["difference_pp"])
            low = float(row["difference_ci_low"])
            high = float(row["difference_ci_high"])
            draw_horizontal_ci(
                ax,
                y_position,
                low,
                high,
                color=str(style["color"]),
                linestyle=str(style["linestyle"]),
                linewidth=EFFECT_MATCHED_CI_LINEWIDTH,
                cap_linewidth=EFFECT_MATCHED_CI_CAP_LINEWIDTH,
                cap_half_height=EFFECT_MATCHED_CI_CAP_HALF_HEIGHT,
            )
            ax.scatter(
                [difference],
                [y_position],
                marker=str(style["marker"]),
                facecolor=str(style["color"]) if str(row["significant"]) == "x" else "white",
                edgecolor="black",
                linewidth=1.0,
                s=EFFECT_MATCHED_MARKER_SIZE,
                zorder=2,
            )
    ax.axvline(0, color="black", linewidth=0.9, linestyle="--")
    ax.set_yticks(list(range(len(smells))))
    ax.set_yticklabels([display_smell(smell, smell_names) for smell in smells], fontsize=EFFECT_YTICK_FONTSIZE)
    ax.set_ylabel(EFFECT_Y_AXIS_LABEL, fontsize=EFFECT_MATCHED_AXIS_LABEL_FONTSIZE)
    comparison_handles = [
        Line2D(
            [0],
            [0],
            marker=str(comparison_style(pair)["marker"]),
            markerfacecolor=str(comparison_style(pair)["color"]),
            markeredgecolor="black",
            color=str(comparison_style(pair)["color"]),
            linestyle=str(comparison_style(pair)["linestyle"]),
            label=comparison_label(pair),
        )
        for pair in pairs
    ]
    ax.legend(
        handles=comparison_handles,
        frameon=False,
        fontsize=EFFECT_LEGEND_FONTSIZE,
        loc="lower right",
    )
    ax.set_xlabel(EFFECT_X_AXIS_LABEL, fontsize=EFFECT_MATCHED_AXIS_LABEL_FONTSIZE)
    ax.set_xlim(EFFECT_X_AXIS_MIN, EFFECT_X_AXIS_MAX)
    ax.set_xticks(list(range(EFFECT_X_AXIS_MIN, EFFECT_X_AXIS_MAX + 1, 2)))
    ax.xaxis.set_minor_locator(MultipleLocator(1))
    ax.tick_params(axis="x", labelsize=EFFECT_MATCHED_XTICK_FONTSIZE)
    ax.tick_params(axis="y", labelsize=EFFECT_YTICK_FONTSIZE)
    ax.grid(True, axis="x", which="major", alpha=0.3)
    ax.grid(True, axis="x", which="minor", alpha=0.18)


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

    fig, ax = plt.subplots(figsize=(8.2, max(5.2, len(effect_order(plot_df)) * 0.34)))
    plot_effect_axis(ax, plot_df, smell_names)
    fig.tight_layout()
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
            summary = format_any_smell_summary(
                frame[
                    (frame["strategy"] == row.strategy)
                    & (frame["tool"] == row.tool)
                    & (frame["smell_detector"] == row.smell_detector)
                    & (frame["change"] == row.change)
                ]
            )
            if summary:
                print(summary)

    if not plotted_any:
        print("No test smell effect plots generated.")


if __name__ == "__main__":
    main()
