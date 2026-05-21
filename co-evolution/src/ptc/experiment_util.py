import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from mhc.config import (
    ME_EXPERIMENT_NAME,
    WORKSPACE_DIRECTORY,
    resolve_experiment_name,
    resolve_experiment_directory,
)


TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
FALSE_ENV_VALUES = {"0", "false", "no", "off"}


@dataclass(frozen=True)
class ExperimentPaths:
    workspace_directory: Path
    experiment_name: str
    experiment_directory: Path


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


def build_experiment_parser(
    description: str,
    *,
    include_tools: bool = True,
    include_projects: bool = True,
    include_strategies: bool = True,
    include_filter_toggle: bool = True,
    include_workspace: bool = True,
    include_experiment: bool = True,
    include_replace: bool = False,
    filter_default: bool | None = None,
    replace_default: bool = True,
    filters_help: str | None = None,
    tools_help: str | None = None,
    projects_help: str | None = None,
    strategies_help: str | None = None,
    experiment_help: str | None = None,
    replace_help: str | None = None,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    if include_workspace:
        parser.add_argument(
            "--workspace-directory",
            dest="workspace_directory",
            default=WORKSPACE_DIRECTORY,
            help=f"Shared workspace root. Defaults to ME_WORKSPACE_DIRECTORY (currently: {WORKSPACE_DIRECTORY}).",
        )
    if include_filter_toggle:
        parser.add_argument(
            "--filters",
            dest="use_filters",
            action=argparse.BooleanOptionalAction,
            default=filter_default,
            help=filters_help or "Apply tool, projects, and strategy filters. Use --no-filters to ignore them.",
        )
    if include_tools:
        parser.add_argument(
            "--tools",
            dest="tools",
            type=str,
            help=tools_help or "Comma-separated tool names to include.",
        )
    if include_projects:
        parser.add_argument(
            "--projects",
            dest="projects",
            type=str,
            help=projects_help or "Comma-separated project names to include.",
        )
    if include_strategies:
        parser.add_argument(
            "--strategies",
            dest="strategies",
            type=str,
            help=strategies_help or "Comma-separated strategy names to include.",
        )
    if include_experiment:
        parser.add_argument(
            "--experiment-name",
            dest="experiment_name",
            type=str,
            default=ME_EXPERIMENT_NAME,
            help=experiment_help or f"Experiment name. Defaults to ME_EXPERIMENT_NAME (currently: {ME_EXPERIMENT_NAME}).",
        )
    if include_replace:
        parser.add_argument(
            "--replace",
            dest="replace",
            action=argparse.BooleanOptionalAction,
            default=replace_default,
            help=replace_help or "Regenerate outputs even when output files already exist. Use --no-replace to skip existing outputs.",
        )
    return parser


def resolve_experiment_paths(
    workspace_directory: str | Path | None = None,
    experiment_name: str | None = None,
) -> ExperimentPaths:
    base_workspace = Path(workspace_directory or WORKSPACE_DIRECTORY)
    resolved_experiment_name = resolve_experiment_name(experiment_name)
    return ExperimentPaths(
        workspace_directory=base_workspace,
        experiment_name=resolved_experiment_name,
        experiment_directory=resolve_experiment_directory(base_workspace, resolved_experiment_name),
    )
