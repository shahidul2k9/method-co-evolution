import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import mhc.util as util
from mhc.command_util import (
    load_test_smell_names,
    non_negative_int,
    resolve_min_t2p_links,
    resolve_smell_detector,
)
from ptc.plot.t2p_test_smell_common import (
    TEST_RECURRENT,
    expand_smell_types,
    format_count,
    load_recurrent_change_frame,
)
from ptc.plot_util import (
    build_experiment_plot_parser,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)

MIN_SMELL_TYPE_COUNT = 5


def build_parser():
    parser = build_experiment_plot_parser(
        "Plot individual test smell types against recurrent test changes.",
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


def smell_type_summary(expanded: pd.DataFrame) -> pd.DataFrame:
    if expanded.empty:
        return pd.DataFrame(
            columns=[
                "smell_name",
                "count",
                "median_test_revision",
                "median_revision_delta",
                "test_recurrent_percent",
            ]
        )

    summary = (
        expanded.groupby("smell_name")
        .agg(
            count=("smell_name", "size"),
            median_test_revision=("test_revision", "median"),
            median_revision_delta=("revision_delta", "median"),
            test_recurrent_percent=("change_group", lambda values: (values == TEST_RECURRENT).mean() * 100),
        )
        .reset_index()
    )
    return summary[summary["count"] >= MIN_SMELL_TYPE_COUNT].copy()


def _barh(ax, summary: pd.DataFrame, value_column: str, title: str, xlabel: str) -> None:
    plotted = summary.sort_values(value_column, ascending=True)
    ax.barh(plotted["smell_name"], plotted[value_column], color="tab:blue")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.grid(True, axis="x", alpha=0.25)


def plot_smell_types(summary: pd.DataFrame, output_file) -> None:
    fig, axes = plt.subplots(2, 2, figsize=(14, max(7, 0.38 * len(summary) + 4)))
    _barh(axes[0][0], summary, "count", "Smell frequency", "Linked rows")
    _barh(axes[0][1], summary, "median_test_revision", "Median test revisions", "Median revisions")
    _barh(axes[1][0], summary, "median_revision_delta", "Median test - production revisions", "Median delta")
    _barh(axes[1][1], summary, "test_recurrent_percent", "Test recurrent rows", "Rows (%)")
    fig.suptitle(f"Test smell type and recurrent test change (types={format_count(len(summary))})", fontsize=13)
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
    smell_names = load_test_smell_names(smell_detector)
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
            expanded = expand_smell_types(frame, smell_names)
            summary = smell_type_summary(expanded)
            if summary.empty:
                continue
            output_file = (
                experiment_directory
                / "figure"
                / f"t2p-test-smell-type--{tool}--{strategy}--{smell_detector}.pdf"
            )
            plot_smell_types(summary, output_file)
            plotted_any = True
            print(f"Wrote {output_file}")

    if not plotted_any:
        print("No test smell type plots generated.")


if __name__ == "__main__":
    main()
