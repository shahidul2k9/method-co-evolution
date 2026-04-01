import argparse
import os
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import cliffs_delta
from scipy.stats import mannwhitneyu

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


TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
FALSE_ENV_VALUES = {"0", "false", "no", "off"}


def _env(name: str) -> str | None:
    value = os.getenv(name)
    if value is None:
        return None

    value = value.strip()
    return value or None


def _env_bool(name: str, default: bool = False) -> bool:
    value = _env(name)
    if value is None:
        return default

    lowered_value = value.lower()
    if lowered_value in TRUE_ENV_VALUES:
        return True
    if lowered_value in FALSE_ENV_VALUES:
        return False

    raise ValueError(
        f"Environment variable {name} must be a boolean value such as true/false or 1/0, got {value!r}."
    )


def _parse_name_list(values: str | Sequence[str] | None) -> list[str] | None:
    if values is None:
        return None

    if isinstance(values, str):
        raw_values = [values]
    else:
        raw_values = [str(value) for value in values if value is not None]

    parsed_values: list[str] = []
    for raw_value in raw_values:
        parsed_values.extend(part.strip() for part in raw_value.split(","))

    parsed_values = [value for value in parsed_values if value]
    if not parsed_values:
        return None

    unique_values: list[str] = []
    for value in parsed_values:
        if value not in unique_values:
            unique_values.append(value)

    return unique_values


def resolve_experiment_filters(
    *,
    use_filters: bool | None = None,
    tools: str | Sequence[str] | None = None,
    projects: str | Sequence[str] | None = None,
    strategies: str | Sequence[str] | None = None,
) -> tuple[list[str] | None, list[str] | None, list[str] | None]:
    explicit_tools = _parse_name_list(tools)
    explicit_projects = _parse_name_list(projects)
    explicit_strategies = _parse_name_list(strategies)
    has_explicit_filters = any(value is not None for value in (tools, projects, strategies))

    if use_filters is False:
        return None, None, None

    if use_filters is None:
        use_filters = has_explicit_filters or _env_bool("ME_EXPERIMENT_FILTERS_ENABLED", False)

    if not use_filters:
        return None, None, None

    resolved_tools = explicit_tools if tools is not None else _parse_name_list(_env("ME_EXPERIMENT_TOOLS"))
    resolved_projects = explicit_projects if projects is not None else _parse_name_list(_env("ME_EXPERIMENT_PROJECTS"))
    resolved_strategies = (
        explicit_strategies if strategies is not None else _parse_name_list(_env("ME_EXPERIMENT_STRATEGIES"))
    )
    return resolved_tools, resolved_projects, resolved_strategies


def select_named_items(
    items: Sequence[str],
    selected_items: str | Sequence[str] | None = None,
    *,
    item_label: str = "item",
    strict: bool = True,
) -> list[str]:
    items = list(items)
    selected_names = _parse_name_list(selected_items)
    if selected_names is None:
        return items

    item_lookup = {item: item for item in items}
    missing_items = [item for item in selected_names if item not in item_lookup]
    if missing_items and strict:
        available_items = ", ".join(items) if items else "<none>"
        missing_display = ", ".join(repr(item) for item in missing_items)
        raise ValueError(
            f"Unknown {item_label}(s): {missing_display}. Available {item_label}s: {available_items}"
        )

    return [item_lookup[item] for item in selected_names if item in item_lookup]


def list_csv_files(
    input_dir: str | Path,
    projects: str | Sequence[str] | None = None,
    *,
    strict: bool = True,
) -> list[Path]:
    csv_files = sorted(Path(input_dir).rglob("*.csv"))
    selected_projects = _parse_name_list(projects)
    if selected_projects is None:
        return csv_files

    grouped_paths: dict[str, list[Path]] = {}
    for path in csv_files:
        grouped_paths.setdefault(path.stem, []).append(path)

    missing_projects = [project for project in selected_projects if project not in grouped_paths]
    if missing_projects and strict:
        available_projects = ", ".join(sorted(grouped_paths)) if grouped_paths else "<none>"
        missing_display = ", ".join(repr(project) for project in missing_projects)
        raise ValueError(
            f"Unknown project(s): {missing_display}. Available projects: {available_projects}"
        )

    selected_paths: list[Path] = []
    for project in selected_projects:
        if project in grouped_paths:
            selected_paths.extend(sorted(grouped_paths[project]))

    return selected_paths


def build_experiment_plot_parser(
    description: str,
    *,
    include_tools: bool = True,
    include_projects: bool = True,
    include_strategies: bool = True,
    include_filter_toggle: bool = True,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    if include_filter_toggle:
        parser.add_argument(
            "--filters",
            dest="use_filters",
            action=argparse.BooleanOptionalAction,
            default=None,
            help="Apply tool, projects, and strategy filters. Use --no-filters to ignore them.",
        )
    if include_tools:
        parser.add_argument(
            "--tools",
            dest="tools",
            type=str,
            help="Comma-separated tool names to plot. Defaults to ME_EXPERIMENT_TOOLS when filters are enabled.",
        )
    if include_projects:
        parser.add_argument(
            "--projects",
            dest="projects",
            type=str,
            help="Comma-separated project names to include. Defaults to ME_EXPERIMENT_PROJECTS when filters are enabled.",
        )
    if include_strategies:
        parser.add_argument(
            "--strategies",
            dest="strategies",
            type=str,
            help="Comma-separated strategy names to include. Defaults to ME_EXPERIMENT_STRATEGIES when filters are enabled.",
        )
    return parser


GRAPH_STYLES = ["-", "--", "-.", ":", "--", "--", "-.", ":"]
GRAPH_MARKS = ["^", "d", "o", "v", "p", "s", "<", ">"]
GRAPH_WIDTHS = [4, 4, 4, 4, 3, 3, 3, 3]
GRAPH_MARKER_SIZES = [10, 10, 12, 14, 20, 10, 12, 15]
GRAPH_MARKER_COLORS = ['r', 'b', 'brown', '#c994c7', '#0F52BA', '#ff7518', '#6CA939', '#636363']
GRAPH_GAPS = [3, 3, 6, 5, 5, 4, 4, 4]
