import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import yaml

from mhc import config
from mhc.artifacts import split_tags


TRUE_ENV_VALUES = {"1", "true", "yes", "on"}
FALSE_ENV_VALUES = {"0", "false", "no", "off"}
UNRESTRICTED_VALUES = {":"}


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


def _env_bool(name: str, default: bool | None = False) -> bool | None:
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


def non_negative_int(value: str | int) -> int:
    try:
        parsed_value = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected a non-negative integer, got {value!r}.") from exc

    if parsed_value < 0:
        raise ValueError(f"Expected a non-negative integer, got {value!r}.")

    return parsed_value


def _parse_name_list(
    values: str | Sequence[str] | None,
    *,
    unrestricted_values: set[str] | None = None,
) -> list[str] | None:
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

    if unrestricted_values and any(value in unrestricted_values for value in parsed_values):
        return None

    unique_values: list[str] = []
    for value in parsed_values:
        if value not in unique_values:
            unique_values.append(value)

    return unique_values


def parse_name_list(values: str | Sequence[str] | None) -> list[str] | None:
    return _parse_name_list(values)


def _default_env_value(name: str, default: str | None) -> str | None:
    value = _env(name)
    return value if value is not None else default


def resolve_experiment_filters(
    *,
    tools: str | Sequence[str] | None = None,
    projects: str | Sequence[str] | None = None,
    strategies: str | Sequence[str] | None = None,
) -> tuple[list[str] | None, list[str] | None, list[str] | None]:
    resolved_tools = _parse_name_list(
        tools if tools is not None else _default_env_value("ME_TOOLS", config.ME_TOOLS)
    )
    resolved_projects = _parse_name_list(
        projects if projects is not None else _default_env_value("ME_PROJECTS", config.ME_PROJECTS),
        unrestricted_values=UNRESTRICTED_VALUES,
    )
    resolved_strategies = _parse_name_list(
        strategies if strategies is not None else _default_env_value("ME_STRATEGIES", config.ME_STRATEGIES)
    )
    return resolved_tools, resolved_projects, resolved_strategies


def resolve_artifacts(artifacts: str | Sequence[str] | None = None) -> list[str] | None:
    return _parse_name_list(
        artifacts if artifacts is not None else _default_env_value("ME_ARTIFACTS", config.ME_ARTIFACTS),
        unrestricted_values=UNRESTRICTED_VALUES,
    )


def resolve_revision_types(revision_types: str | Sequence[str] | None = None) -> list[str] | None:
    return _parse_name_list(
        revision_types
        if revision_types is not None
        else _default_env_value("ME_REVISION_TYPES", config.ME_REVISION_TYPES),
        unrestricted_values=UNRESTRICTED_VALUES,
    )


def resolve_min_t2p_links(min_t2p_links: str | int | None = None) -> int:
    if min_t2p_links is not None:
        return non_negative_int(min_t2p_links)
    return non_negative_int(_default_env_value("ME_MIN_T2P_LINKS", config.ME_MIN_T2P_LINKS) or "30")


def resolve_smell_detector(smell_detector: str | None = None) -> str:
    return (smell_detector or _default_env_value("ME_SMELL_DETECTOR", "jnose") or "jnose").strip()


def test_smell_config_path() -> Path:
    return Path(config.PROJECT_DIRECTORY) / "config" / "test-smell.yml"


def load_test_smell_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path is not None else test_smell_config_path()
    if not config_path.exists():
        raise FileNotFoundError(f"Test smell config not found: {config_path}")
    with config_path.open(encoding="utf-8") as config_file:
        loaded = yaml.safe_load(config_file) or {}
    if not isinstance(loaded, dict):
        raise ValueError(f"Test smell config must be a mapping: {config_path}")
    return loaded


def load_test_smell_acronyms(smell_detector: str = "jnose", path: str | Path | None = None) -> dict[str, str]:
    loaded = load_test_smell_config(path)
    detector_config = loaded.get("smell_detectors", {}).get(smell_detector, {})
    smells = detector_config.get("smells", {})
    if not isinstance(smells, dict):
        raise ValueError(f"Test smell config smells must be a mapping for detector={smell_detector!r}.")
    return {str(full_name): str(acronym) for full_name, acronym in smells.items()}


def load_test_smell_names(smell_detector: str = "jnose", path: str | Path | None = None) -> dict[str, str]:
    names: dict[str, str] = {}
    for full_name, acronym in load_test_smell_acronyms(smell_detector, path).items():
        names.setdefault(acronym, full_name)
    return names


def artifact_matches(artifact: str | None, selected_artifacts: str | Sequence[str] | None = None) -> bool:
    selected = _parse_name_list(selected_artifacts, unrestricted_values=UNRESTRICTED_VALUES)
    if selected is None:
        return True
    return bool(split_tags(artifact).intersection(selected))


def filter_artifact_dataframe(
    df,
    selected_artifacts: str | Sequence[str] | None = None,
    *,
    artifact_column: str = "artifact",
):
    selected = resolve_artifacts(selected_artifacts)
    if selected is None or artifact_column not in df.columns:
        return df
    return df[df[artifact_column].map(lambda artifact: artifact_matches(artifact, selected))].copy()


def select_revision_columns(
    columns: Sequence[str],
    selected_revision_types: str | Sequence[str] | None = None,
    *,
    preferred_order: Sequence[str] | None = None,
    include_extra: bool = False,
) -> list[str]:
    columns = list(columns)
    selected = resolve_revision_types(selected_revision_types)
    if selected is not None:
        selected_set = set(selected)
        columns = [column for column in columns if column in selected_set]

    if preferred_order is None:
        return columns

    preferred = [column for column in preferred_order if column in columns]
    if not include_extra:
        return preferred

    return preferred + [column for column in columns if column not in preferred]


def _project_index_value() -> str | None:
    return _default_env_value("ME_PROJECT_INDEX", config.ME_PROJECT_INDEX)


PROJECT_INDEX_ERROR = (
    "ME_PROJECT_INDEX must be ':' or Python slice syntax such as '0:10', '10:20', '::2', "
    "a single integer, or comma-separated integer indexes such as '0,2,4'."
)


def _parse_project_index_token(value: str, size: int) -> set[int]:
    if ":" in value:
        parts = value.split(":")
        if len(parts) > 3:
            raise ValueError
        parsed_parts = [int(part) if part else None for part in parts]
        return set(range(size)[slice(*parsed_parts)])

    index = int(value)
    if index < 0:
        index += size
    return {index} if 0 <= index < size else set()


def _parse_project_index(project_index: str | None, size: int) -> set[int] | None:
    if project_index is None:
        return None

    value = str(project_index).strip()
    if not value or value in UNRESTRICTED_VALUES:
        return None

    try:
        if "," in value:
            selected_indices: set[int] = set()
            for token in (part.strip() for part in value.split(",")):
                if not token:
                    raise ValueError
                selected_indices.update(_parse_project_index_token(token, size))
            return selected_indices

        return _parse_project_index_token(value, size)
    except ValueError as exc:
        raise ValueError(PROJECT_INDEX_ERROR) from exc


def select_project_items(
    items: Sequence[str],
    selected_projects: str | Sequence[str] | None = None,
    *,
    strict: bool = True,
    project_index: str | None = None,
) -> list[str]:
    items = list(items)
    selected_names = _parse_name_list(selected_projects, unrestricted_values=UNRESTRICTED_VALUES)
    selected_indices = _parse_project_index(
        _project_index_value() if project_index is None else project_index,
        len(items),
    )

    selected_name_set = set(selected_names) if selected_names is not None else None
    item_set = set(items)
    missing_projects = [project for project in selected_names or [] if project not in item_set]
    if missing_projects and strict:
        available_projects = ", ".join(items) if items else "<none>"
        missing_display = ", ".join(repr(project) for project in missing_projects)
        raise ValueError(
            f"Unknown project(s): {missing_display}. Available projects: {available_projects}"
        )

    selected_items: list[str] = []
    for index, item in enumerate(items):
        if selected_name_set is not None and item not in selected_name_set:
            continue
        if selected_indices is not None and index not in selected_indices:
            continue
        selected_items.append(item)

    return selected_items


def select_named_items(
    items: Sequence[str],
    selected_items: str | Sequence[str] | None = None,
    *,
    item_label: str = "item",
    strict: bool = True,
) -> list[str]:
    if item_label == "project":
        return select_project_items(items, selected_items, strict=strict)

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
    project_names = []
    grouped_paths: dict[str, list[Path]] = {}
    for path in csv_files:
        if path.stem not in grouped_paths:
            project_names.append(path.stem)
        grouped_paths.setdefault(path.stem, []).append(path)

    selected_projects = select_project_items(project_names, projects, strict=strict)
    if len(selected_projects) == len(project_names) and selected_projects == project_names:
        return csv_files

    selected_paths: list[Path] = []
    for project in selected_projects:
        selected_paths.extend(sorted(grouped_paths.get(project, [])))

    return selected_paths


def build_experiment_parser(
    description: str,
    *,
    include_tools: bool = True,
    include_projects: bool = True,
    include_strategies: bool = True,
    include_revision_types: bool = False,
    include_smell_detector: bool = False,
    include_project_directory: bool = False,
    include_output_directory: bool = False,
    include_workspace: bool = True,
    include_experiment: bool = True,
    include_replace: bool = False,
    replace_default: bool = False,
    tools_help: str | None = None,
    projects_help: str | None = None,
    strategies_help: str | None = None,
    revision_types_help: str | None = None,
    experiment_help: str | None = None,
    replace_help: str | None = None,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    if include_project_directory:
        parser.add_argument(
            "--project-directory",
            dest="project_directory",
            default=config.PROJECT_DIRECTORY,
            help=f"Project root. Defaults to ME_PROJECT_DIRECTORY (currently: {config.PROJECT_DIRECTORY}).",
        )
    if include_output_directory:
        parser.add_argument(
            "--output-directory",
            dest="output_directory",
            default=None,
            help="Directory for generated outputs. Relative paths resolve from the project root.",
        )
    if include_workspace:
        parser.add_argument(
            "--workspace-directory",
            dest="workspace_directory",
            default=config.WORKSPACE_DIRECTORY,
            help=f"Shared workspace root. Defaults to ME_WORKSPACE_DIRECTORY (currently: {config.WORKSPACE_DIRECTORY}).",
        )
    if include_tools:
        parser.add_argument(
            "--tools",
            dest="tools",
            type=str,
            help=tools_help or "Comma-separated tool names to include. Defaults to ME_TOOLS.",
        )
    if include_projects:
        parser.add_argument(
            "--projects",
            dest="projects",
            type=str,
            help=projects_help or "Comma-separated project names to include. Defaults to ME_PROJECTS.",
        )
    if include_strategies:
        parser.add_argument(
            "--strategies",
            dest="strategies",
            type=str,
            help=strategies_help or "Comma-separated strategy names to include. Defaults to ME_STRATEGIES.",
        )
    if include_revision_types:
        parser.add_argument(
            "--revision-types",
            dest="revision_types",
            type=str,
            default=_default_env_value("ME_REVISION_TYPES", config.ME_REVISION_TYPES),
            help=revision_types_help or "Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
        )
    if include_smell_detector:
        parser.add_argument(
            "--smell-detector",
            dest="smell_detector",
            type=str,
            default=resolve_smell_detector(),
            help="Test smell detector output to include. Defaults to ME_SMELL_DETECTOR or jnose.",
        )
    if include_experiment:
        parser.add_argument(
            "--experiment-name",
            dest="experiment_name",
            type=str,
            default=config.ME_EXPERIMENT_NAME,
            help=experiment_help
            or f"Experiment name. Defaults to ME_EXPERIMENT_NAME (currently: {config.ME_EXPERIMENT_NAME}).",
        )
    if include_replace:
        parser.add_argument(
            "--replace",
            dest="replace",
            action=argparse.BooleanOptionalAction,
            default=_env_bool("ME_REPLACE", replace_default),
            help=replace_help or "Regenerate outputs even when output files already exist. Use --no-replace to skip existing outputs.",
        )
    return parser


def resolve_experiment_paths(
    workspace_directory: str | Path | None = None,
    experiment_name: str | None = None,
) -> ExperimentPaths:
    base_workspace = Path(workspace_directory or config.WORKSPACE_DIRECTORY)
    resolved_experiment_name = config.resolve_experiment_name(experiment_name)
    return ExperimentPaths(
        workspace_directory=base_workspace,
        experiment_name=resolved_experiment_name,
        experiment_directory=config.resolve_experiment_directory(base_workspace, resolved_experiment_name),
    )
