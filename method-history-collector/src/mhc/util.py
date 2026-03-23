import os
import pandas as pd
import numpy as np
from pathlib import Path

def format_git_project_directory(repository_directory: str, repository_name: str) -> str:
    return os.path.join(f"{repository_directory}", repository_name)


def format_method_list_file(data_directory: str, repository_name: str) -> str:
    return os.path.join(f"{data_directory}/method", f"{repository_name}.csv")


def format_method_code_file(data_directory: str, repository_name: str) -> str:
    return os.path.join(f"{data_directory}/method-code", f"{repository_name}.csv")


def format_method_cache_file(data_directory: str, repository_name: str, commit_hash: str) -> str:
    return os.path.join(f"{data_directory}/method_cache", f"{repository_name}.csv")


def format_repository_history_index_file(cache_dir: str) -> str:
    return os.path.join(f"{cache_dir}", f"repository-history-index.csv")


def format_method_history_path(cache_directory: str, tool_name: str, repository_name) -> str:
    return os.path.join(f"{cache_directory}/history/{tool_name}/{repository_name}")


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


def sorted_directory_names(path: str | Path) -> list[str]:
    return sorted(entry.name for entry in os.scandir(path) if entry.is_dir())


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
