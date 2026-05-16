import argparse

import numpy as np
import cliffs_delta
from scipy.stats import mannwhitneyu
from ptc.experiment_util import (
    build_experiment_parser,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)

def ecdf_with_rank(series):
    s = series.sort_values()
    y = s.rank(method="max", pct=True)
    return s, y


def ecdf(a):
    x, counts = np.unique(a, return_counts=True)
    cusum = np.cumsum(counts)
    return x, cusum / cusum[-1]

def man_utest(x, y):
    d, size = cliffs_delta.cliffs_delta(x, y)
    stat, p_value = mannwhitneyu(x, y, alternative='two-sided')
    return stat, p_value, d, size


def manu_test(x, y):
    return man_utest(x, y)


def build_experiment_plot_parser(
    description: str,
    *,
    include_tools: bool = True,
    include_projects: bool = True,
    include_strategies: bool = True,
    include_filter_toggle: bool = True,
) -> "argparse.ArgumentParser":
    return build_experiment_parser(
        description,
        include_tools=include_tools,
        include_projects=include_projects,
        include_strategies=include_strategies,
        include_filter_toggle=include_filter_toggle,
        filter_default=None,
        filters_help="Apply tool, projects, and strategy filters. Use --no-filters to ignore them.",
        tools_help="Comma-separated tool names to plot. Defaults to ME_EXPERIMENT_TOOLS when filters are enabled.",
        projects_help=(
            "Comma-separated project names to include. Defaults to ME_EXPERIMENT_PROJECTS when filters are enabled."
        ),
        strategies_help=(
            "Comma-separated strategy names to include. Defaults to ME_EXPERIMENT_STRATEGIES when filters are enabled."
        ),
    )


GRAPH_STYLES = ["-", "--", "-.", ":", "--", "--", "-.", ":"]
GRAPH_MARKS = ["^", "d", "o", "v", "p", "s", "<", ">"]
GRAPH_WIDTHS = [4, 4, 4, 4, 3, 3, 3, 3]
GRAPH_MARKER_SIZES = [10, 10, 12, 14, 20, 10, 12, 15]
GRAPH_MARKER_COLORS = ['r', 'b', 'brown', '#c994c7', '#0F52BA', '#ff7518', '#6CA939', '#636363']
GRAPH_GAPS = [3, 3, 6, 5, 5, 4, 4, 4]
