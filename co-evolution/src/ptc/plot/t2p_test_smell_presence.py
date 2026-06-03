import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import mhc.util as util
from mhc.command_util import non_negative_int, resolve_min_t2p_links, resolve_smell_detector
from ptc.plot.t2p_test_smell_common import (
    CHANGE_GROUP_LABELS,
    CHANGE_GROUP_ORDER,
    SMELL_PRESENCE_LABELS,
    format_count,
    format_percent,
    load_recurrent_change_frame,
)
from ptc.plot_util import (
    build_experiment_plot_parser,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)


def build_parser():
    parser = build_experiment_plot_parser(
        "Plot test smell presence against recurrent test changes.",
        include_smell_detector=True,
    )
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum linked test-production pairs required before plots are generated. Defaults to ME_MIN_T2P_LINKS.",
    )
    return parser


def _boxplot_by_smell(ax, frame: pd.DataFrame, column: str, ylabel: str) -> None:
    data = [
        frame.loc[frame["has_smell"] == has_smell, column].astype(float).values
        for has_smell in [False, True]
    ]
    ax.boxplot(data, labels=[SMELL_PRESENCE_LABELS[False], SMELL_PRESENCE_LABELS[True]], showfliers=False)
    ax.set_ylabel(ylabel)
    ax.grid(True, axis="y", alpha=0.25)


def _plot_group_percentages(ax, frame: pd.DataFrame) -> None:
    counts = (
        frame.groupby(["has_smell", "change_group"])
        .size()
        .unstack(fill_value=0)
        .reindex(index=[False, True], columns=CHANGE_GROUP_ORDER, fill_value=0)
    )
    percentages = counts.div(counts.sum(axis=1).replace(0, 1), axis=0) * 100
    x = range(len(percentages.index))
    bottom = [0.0] * len(percentages.index)
    colors = ["tab:orange", "tab:gray", "tab:blue"]
    for index, group in enumerate(CHANGE_GROUP_ORDER):
        values = percentages[group].values
        ax.bar(x, values, bottom=bottom, label=CHANGE_GROUP_LABELS[group], color=colors[index])
        bottom = [current + added for current, added in zip(bottom, values)]
    ax.set_xticks(list(x))
    ax.set_xticklabels([SMELL_PRESENCE_LABELS[value] for value in percentages.index])
    ax.set_ylabel("Rows (%)")
    ax.set_ylim(0, 100)
    ax.legend(frameon=False, fontsize=9)
    ax.grid(True, axis="y", alpha=0.25)


def plot_presence(frame: pd.DataFrame, output_file) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
    _boxplot_by_smell(axes[0], frame, "test_revision", "Test revisions")
    _boxplot_by_smell(axes[1], frame, "revision_delta", "Test - production revisions")
    _plot_group_percentages(axes[2], frame)
    total = len(frame)
    smelly = int(frame["has_smell"].sum())
    fig.suptitle(
        f"Test smell presence and recurrent test change (n={format_count(total)}, smelly={format_percent(smelly / total * 100 if total else 0)})",
        fontsize=13,
    )
    fig.tight_layout()
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    fig.savefig(output_file, bbox_inches="tight")
    plt.close(fig)


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
    smell_detector = resolve_smell_detector(args.smell_detector)
    t2p_change_directory = experiment_directory / "t2p-change"
    tools = select_named_items(util.sorted_directory_names(t2p_change_directory), selected_tools, item_label="tool")

    plotted_any = False
    for tool in tools:
        strategies = select_named_items(
            util.sorted_directory_names(t2p_change_directory / tool),
            selected_strategies,
            item_label="strategy",
        )
        for strategy in strategies:
            frame = load_recurrent_change_frame(
                experiment_directory,
                tool,
                strategy,
                smell_detector,
                selected_projects,
                min_t2p_links=args.min_t2p_links,
            )
            if frame.empty:
                continue
            output_file = (
                experiment_directory
                / "figure"
                / f"t2p-test-smell-presence--{tool}--{strategy}--{smell_detector}.pdf"
            )
            plot_presence(frame, output_file)
            plotted_any = True
            print(f"Wrote {output_file}")

    if not plotted_any:
        print("No test smell presence plots generated.")


if __name__ == "__main__":
    main()
