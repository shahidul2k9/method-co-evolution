import os
import subprocess
import sys
import hashlib
import shlex
from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

def format_git_project_directory(repository_directory: str, repository_name: str) -> str:
    return os.path.join(f"{repository_directory}", repository_name)


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
        from mhc.config import DATA_DIRECTORY

        output_dir = Path(DATA_DIRECTORY) / "aggregate"

    dfs = [
        pd.read_csv(file, keep_default_na=False, na_filter=False)
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
