import os
import subprocess
import sys
import hashlib
import shlex
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_INDEX_HELP = (
    "project-index must use Python-style indexes or slices like 10, -1, 10:20, :10, 10:, or :, "
    "or comma-separated indexes like 0,2,4"
)


def _parse_project_index_token(project_index: str, projects: Sequence[str]) -> list[str]:
    if ":" not in project_index:
        try:
            return [projects[int(project_index)]]
        except (ValueError, IndexError) as exc:
            raise ValueError(PROJECT_INDEX_HELP) from exc

    if project_index.count(":") > 2:
        raise ValueError(PROJECT_INDEX_HELP)

    parts = project_index.split(":")
    try:
        parsed_parts = [int(part) if part else None for part in parts]
    except ValueError as exc:
        raise ValueError(PROJECT_INDEX_HELP) from exc
    return list(projects[slice(*parsed_parts)])


def parse_project_index(project_index: str | None, known_projects: Sequence[str]) -> list[str]:
    if not project_index:
        return []

    projects = list(known_projects)
    value = project_index.strip()
    if value == ":":
        return projects
    if "," not in value:
        return _parse_project_index_token(value, projects)

    selected_projects: list[str] = []
    selected_project_set: set[str] = set()
    for token in (part.strip() for part in value.split(",")):
        if not token:
            raise ValueError(PROJECT_INDEX_HELP)
        for project in _parse_project_index_token(token, projects):
            if project not in selected_project_set:
                selected_projects.append(project)
                selected_project_set.add(project)
    return selected_projects


def format_git_project_directory(repository_directory: str, repository_name: str) -> str:
    return os.path.join(f"{repository_directory}", repository_name)


def require_project_name(repository) -> str:
    try:
        project_name = repository["project"]
    except (KeyError, TypeError):
        raise ValueError("Missing required project column")

    if pd.isna(project_name) or str(project_name).strip() == "":
        raise ValueError("Project name is required")
    return str(project_name).strip()


def format_method_list_file(data_directory: str, repository_name: str) -> str:
    return os.path.join(f"{data_directory}/method", f"{repository_name}.csv")


def format_method_mapping_file(workspace_directory: str, data_directory: str, repository_name: str) -> str | None:
    data_method_file = format_method_list_file(data_directory, repository_name)
    if os.path.exists(data_method_file):
        return data_method_file

    cache_method_file = os.path.join(f"{workspace_directory}/method", f"{repository_name}.csv")
    if os.path.exists(cache_method_file):
        return cache_method_file

    return None


def format_logback_config_file(workspace_directory: str) -> str | None:
    logback_file = os.path.join(f"{workspace_directory}/config", "logback.xml")
    return logback_file if os.path.exists(logback_file) else None


def java_options_with_logback_config(java_options: str | None, workspace_directory: str) -> str | None:
    options = shlex.split(java_options) if java_options else []
    logback_file = format_logback_config_file(workspace_directory)
    if logback_file and not any(option.startswith("-Dlogback.configurationFile=") for option in options):
        options.append(f"-Dlogback.configurationFile={logback_file}")
    return " ".join(shlex.quote(option) for option in options) if options else None


def format_method_code_file(data_directory: str, repository_name: str) -> str:
    return os.path.join(f"{data_directory}/method-code", f"{repository_name}.csv")


def format_class_list_file(data_directory: str, repository_name: str) -> str:
    return os.path.join(f"{data_directory}/class", f"{repository_name}.csv")


def format_class_mapping_file(workspace_directory: str, data_directory: str, repository_name: str) -> str | None:
    data_class_file = format_class_list_file(data_directory, repository_name)
    if os.path.exists(data_class_file):
        return data_class_file

    cache_class_file = os.path.join(f"{workspace_directory}/class", f"{repository_name}.csv")
    if os.path.exists(cache_class_file):
        return cache_class_file

    return None


def format_class_cache_file(data_directory: str, repository_name: str) -> str:
    return os.path.join(f"{data_directory}/class-cache", f"{repository_name}.csv")


def format_method_cache_file(data_directory: str, repository_name: str, commit_hash: str) -> str:
    return os.path.join(f"{data_directory}/method-cache", f"{repository_name}.csv")


def format_method_history_path(history_directory: str, tool_name: str, repository_name) -> str:
    return os.path.join(f"{history_directory}/{tool_name}/{repository_name}")


def format_method_history_file_suffix(file: str, method_name: str, start_line: int) -> str:
    file_without_extension = file[:-len('.java')] if file.lower().endswith(".java") else file
    file.replace(".java", "")
    return os.path.join(f"{file_without_extension}--{method_name}--{start_line}.json")



def format_to_git_url(repository_url: str, hash: str, file: str, start_line_no: int) -> str:
    return f"{repository_url}/blob/{hash}/{file}#L{start_line_no}"

def convert_method_file_to_method_url(repository_url: str, hash: str, method_file: str) -> str:
    file_parts = method_file.rsplit("/", maxsplit=1)
    file_path_prefix = f"{file_parts[0]}/" if len(file_parts) > 1 else ""
    bare_method_file_name = file_parts[-1]
    file_name, method_name, start_line_no = bare_method_file_name.replace(".json", "").split("--")
    return f"{repository_url}/blob/{hash}/{file_path_prefix}{file_name}.java#L{start_line_no}"


def remove_prefix_if_exists(s: set[str], prefix) -> set[str]:
    return set(map(lambda f: f[len(prefix):] if f.startswith(prefix) else f, s))


def stable_shard_for_key(key: str, shards: int) -> int:
    if shards <= 0:
        raise ValueError("shards must be positive")
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()
    return (int(digest, 16) % shards) + 1


def sorted_directory_names(path: str | Path) -> list[str]:
    return sorted(entry.name for entry in os.scandir(path) if entry.is_dir())


def aggregate_csv_files(
    input_dir: str | Path,
    output_file_name: str,
    output_dir: str | Path | None = None,
) -> None:
    if output_dir is None:
        from mhc.config import EXPERIMENT_DIRECTORY

        output_dir = Path(EXPERIMENT_DIRECTORY) / "aggregate"

    dfs = [
        pd.read_csv(file, keep_default_na=False, na_filter=False, low_memory=False)
        for file in Path(input_dir).rglob("*.csv")
    ]
    dfs = [df for df in dfs if not df.empty]

    if not dfs:
        return

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    pd.concat(dfs, ignore_index=True).to_csv(output_path / output_file_name, index=False)


def lcs(s1, s2):
    n = len(s1)
    m = len(s2)
    c = [[0]*(m+1) for i in range(n+1)]
    for i in range(n+1):
        for j in range(m+1):
            if i==0 or j==0:
                c[i][j] = 0
            elif s1[i-1]==s2[j-1]:
                    c[i][j] = c[i-1][j-1] + 1
            else:
                    c[i][j] = max(c[i-1][j], c[i][j-1])
    return c[n][m]

def convert_float_int_columns_to_nullable_int(df: pd.DataFrame) -> pd.DataFrame:
    """
    Convert float columns that contain only integer-valued data
    (ignoring missing values) into pandas nullable Int64 columns.
    """
    df = df.copy()

    for col in df.columns:
        s = df[col]

        if pd.api.types.is_float_dtype(s):
            non_null = s.dropna()

            if non_null.empty or np.all(np.isclose(non_null, np.round(non_null))):
                df[col] = np.round(s).astype("Int64")

    return df


def normalize_integer_columns(df: pd.DataFrame, columns: Sequence[str]) -> pd.DataFrame:
    """
    Normalize integer-like CSV fields to plain integer text.

    Pandas often widens integer columns to floats when scan rows are mixed with
    marker rows containing missing values. Once those caches are read with
    dtype=str, values such as "72.0" need string-level cleanup too.
    """
    df = df.copy()

    for col in columns:
        if col not in df.columns:
            continue
        df[col] = df[col].map(_normalize_integer_cell)

    return df


def _normalize_integer_cell(value) -> str:
    if pd.isna(value):
        return ""
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return ""
    else:
        text = str(value).strip()

    try:
        numeric = float(text)
    except ValueError:
        return text

    if not np.isfinite(numeric) or not np.isclose(numeric, round(numeric)):
        return text
    return str(int(round(numeric)))


def find_root(start: Path) -> Path:
    current = start.resolve()
    for path in [current, *current.parents]:
        if (path / ".git").exists():
            return path
    return current


def run_module(
    module_name: str,
    project_root: Path = find_root(Path.cwd()),
    args: Sequence[str] | None = None,
):
    command = [sys.executable, "-m", module_name]
    if args:
        command.extend(args)

    subprocess.run(
        command,
        check=True,
        cwd=project_root,
    )
