import logging
import os
import time
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
from pandas import DataFrame

import mhc.util as util
from mhc.method_scanner import (
    clone_and_checkout_commit,
    collect_files,
    DEFAULT_SCAN_MERGE_THRESHOLD,
    _should_flush_scan_cache,
    _write_dataframe_csv,
    _append_dataframe_csv,
)
from mhc.zip import file_lock, remove_empty_directory_tree, remove_file_if_exists

CLASS_SCAN_COLUMNS = [
    "project",
    "name",
    "fqn",
    "pkg",
    "url",
    "file",
    "start_line",
    "end_line",
    "expression",
    "artifact",
    "abstract",
    "parent_names",
    "parent_fqns",
    "hash",
]
CLASS_SCAN_INTEGER_COLUMNS = ["start_line", "end_line", "abstract"]

SCAN_CLASS_FLUSH_INTERVAL_SECONDS = 15 * 60
CLASS_SCAN_MARKER = "__scan_marker__"
CLASS_SCAN_ERROR_MARKER = "__error_marker__"
CLASS_SCAN_FLAG_COLUMN = "_flag"
CLASS_SCAN_ERROR_COLUMN = "_error"
CLASS_SCAN_ERROR_MAX_LENGTH = 256
CLASS_SCAN_CACHE_COLUMNS = CLASS_SCAN_COLUMNS + [
    CLASS_SCAN_FLAG_COLUMN,
    CLASS_SCAN_ERROR_COLUMN,
]


def _build_class_scan_marker(repository_name: str, file_without_base: str, commit_hash: str) -> dict:
    return {
        "project": repository_name,
        "name": None,
        "fqn": None,
        "pkg": None,
        "url": None,
        "file": file_without_base,
        "start_line": None,
        "end_line": None,
        "expression": None,
        "artifact": None,
        "abstract": None,
        "parent_names": None,
        "parent_fqns": None,
        "hash": commit_hash,
        CLASS_SCAN_FLAG_COLUMN: CLASS_SCAN_MARKER,
        CLASS_SCAN_ERROR_COLUMN: None,
    }


def _build_class_scan_error_marker(
    repository_name: str,
    file_without_base: str,
    commit_hash: str,
    error: Exception | str | None = None,
) -> dict:
    row = _build_class_scan_marker(repository_name, file_without_base, commit_hash)
    row[CLASS_SCAN_FLAG_COLUMN] = CLASS_SCAN_ERROR_MARKER
    row[CLASS_SCAN_ERROR_COLUMN] = str(error)[:CLASS_SCAN_ERROR_MAX_LENGTH] if error is not None else None
    return row


def _read_class_scan_cache(cache_file: str) -> pd.DataFrame:
    if not os.path.exists(cache_file):
        return pd.DataFrame(columns=CLASS_SCAN_CACHE_COLUMNS)
    try:
        return pd.read_csv(cache_file, dtype=str).reindex(columns=CLASS_SCAN_CACHE_COLUMNS)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=CLASS_SCAN_CACHE_COLUMNS)


def _completed_class_scan_files(cache_df: pd.DataFrame, retry_errors: bool = True) -> set[str]:
    if cache_df.empty:
        return set()
    rows = cache_df
    if retry_errors:
        rows = cache_df[cache_df[CLASS_SCAN_FLAG_COLUMN] != CLASS_SCAN_ERROR_MARKER]
    return set(rows["file"].dropna().astype(str))


def _tried_class_scan_files(cache_df: pd.DataFrame) -> set[str]:
    if cache_df.empty:
        return set()
    return set(cache_df["file"].dropna().astype(str))


def _failed_class_scan_files(cache_df: pd.DataFrame) -> set[str]:
    if cache_df.empty:
        return set()
    completed_files = _completed_class_scan_files(cache_df)
    error_files = set(
        cache_df.loc[
            cache_df[CLASS_SCAN_FLAG_COLUMN] == CLASS_SCAN_ERROR_MARKER,
            "file",
        ].dropna().astype(str)
    )
    return error_files - completed_files


def _load_cached_class_scan_files(cache_file: str, retry_errors: bool = True) -> set[str]:
    if not os.path.exists(cache_file):
        return set()
    return _completed_class_scan_files(_read_class_scan_cache(cache_file), retry_errors)


def _is_class_scan_file_completed(
    cache_file: str,
    lock_path: str,
    file_without_base: str,
    retry_errors: bool = True,
) -> bool:
    with file_lock(lock_path):
        return file_without_base in _completed_class_scan_files(
            _read_class_scan_cache(cache_file),
            retry_errors,
        )


def _flush_class_scan_buffers(
    cache_file: str,
    lock_path: str,
    pending: list[dict],
    retry_errors: bool = True,
) -> None:
    if not pending:
        return
    rows_copy = list(pending)
    pending.clear()
    with file_lock(lock_path):
        completed_files = _completed_class_scan_files(
            _read_class_scan_cache(cache_file),
            retry_errors,
        )
        rows_copy = [
            row for row in rows_copy
            if row.get("file") not in completed_files
        ]
        _append_dataframe_csv(
            cache_file,
            rows_copy,
            CLASS_SCAN_CACHE_COLUMNS,
            CLASS_SCAN_INTEGER_COLUMNS,
        )


def _is_class_output_current(output_file: str, commit_hash: str) -> bool:
    if not os.path.exists(output_file):
        return False
    try:
        df = pd.read_csv(output_file, usecols=["hash"])
    except (ValueError, pd.errors.EmptyDataError):
        return True
    hashes = set(df["hash"].dropna().astype(str))
    return not hashes or hashes == {commit_hash}


def _scan_classes_in_file(
    scanner,
    repository_name: str,
    commit_hash: str,
    file_without_base: str,
) -> tuple[list[dict], str | None]:
    rows = []
    try:
        java_classes = scanner.scanClass(file_without_base)
        for jc in java_classes:
            rows.append({
                "project": repository_name,
                "name": jc.getName(),
                "fqn": jc.getFqn(),
                "pkg": jc.getPkg(),
                "url": jc.getUrl(),
                "file": jc.getFile(),
                "start_line": jc.getStartLine(),
                "end_line": jc.getEndLine(),
                "expression": jc.getExpression(),
                "artifact": jc.getArtifact(),
                "abstract": jc.getAbstractClass(),
                "parent_names": jc.getParentNames(),
                "parent_fqns": jc.getParentFqns(),
                "hash": jc.getHash(),
            })
        return rows, None
    except Exception as error:
        return rows, str(error)


def _finalize_class_scan_outputs(
    cache_file: str,
    output_file: str,
    error_output_file: str,
    expected_files: set[str],
    lock_path: str | None = None,
    delete_tmp: bool = True,
    delete_lock: bool = True,
) -> bool:
    context = file_lock(lock_path) if lock_path else nullcontext()
    with context:
        cache_df = _read_class_scan_cache(cache_file)
        missing_files = expected_files - _tried_class_scan_files(cache_df)
        if missing_files:
            logging.info(
                "Skipping class scan merge for %s; %s files have not been tried",
                Path(output_file).stem,
                len(missing_files),
            )
            return False

        failed_files = _failed_class_scan_files(cache_df)
        error_rows = cache_df[cache_df["file"].isin(failed_files)].copy()
        out_df = cache_df[cache_df[CLASS_SCAN_FLAG_COLUMN].isna()].copy()
        _write_dataframe_csv(
            output_file,
            out_df,
            CLASS_SCAN_COLUMNS,
            CLASS_SCAN_INTEGER_COLUMNS,
        )

        if not error_rows.empty:
            _write_dataframe_csv(
                error_output_file,
                error_rows,
                CLASS_SCAN_CACHE_COLUMNS,
                CLASS_SCAN_INTEGER_COLUMNS,
            )
        elif os.path.exists(error_output_file):
            os.remove(error_output_file)

        if delete_tmp:
            remove_file_if_exists(cache_file)
            remove_file_if_exists(f"{cache_file}.tmp")
            remove_file_if_exists(f"{output_file}.tmp")
            remove_file_if_exists(f"{error_output_file}.tmp")
    if delete_lock and lock_path:
        remove_file_if_exists(lock_path)
    return True


def scan_class(
    repository_df: DataFrame,
    repository_directory: str,
    data_directory: str,
    _workspace_directory: str,
    replace: bool = False,
    shards: int = 1,
    shard: int = 1,
    merge_only: bool = False,
    merge_only_delete_empty: bool = False,
    merge_only_delete_tmp: bool = False,
    merge_only_delete_lock: bool = False,
    retry_errors: bool = True,
    merge_threshold: int = DEFAULT_SCAN_MERGE_THRESHOLD,
    merge_interval_seconds: int | None = None,
    artifact_config_path: str | None = None,
) -> None:
    ClassScannerImpl = None
    if merge_interval_seconds is None:
        merge_interval_seconds = SCAN_CLASS_FLUSH_INTERVAL_SECONDS
    if not merge_only:
        from jpype import JClass
        ClassScannerImpl = JClass("rnd.method.parser.call.graph.service.ClassScannerImpl")

    for _, repository in repository_df.iterrows():
        repository_name = repository["project"]
        url = repository["url"]
        commit_hash = repository["updated_hash"]
        repository_root = util.format_git_project_directory(repository_directory, repository_name)
        output_file = util.format_class_list_file(data_directory, repository_name)
        cache_dir = os.path.join(_workspace_directory, ".class")
        cache_file = os.path.join(cache_dir, f"{repository_name}.csv")
        lock_path = os.path.join(cache_dir, f"{repository_name}.lock")
        error_dir = os.path.join(_workspace_directory, ".class-error")
        error_output_file = os.path.join(error_dir, f"{repository_name}.csv")

        if replace:
            for f in (output_file, cache_file, error_output_file):
                remove_file_if_exists(f)
        elif not merge_only and shards == 1 and not os.path.exists(cache_file) and _is_class_output_current(output_file, commit_hash):
            continue

        clone_and_checkout_commit(url, repository_root, commit_hash)
        java_files = sorted(collect_files(repository_root, "*.java"))
        expected_files = {
            file[len(repository_root) + 1:]
            for file in java_files
        }

        if merge_only:
            merged = _finalize_class_scan_outputs(
                cache_file,
                output_file,
                error_output_file,
                expected_files,
                lock_path,
                True,
                True,
            )
            if merged and merge_only_delete_empty:
                remove_empty_directory_tree(cache_dir)
                remove_empty_directory_tree(error_dir)
            continue

        os.makedirs(cache_dir, exist_ok=True)

        scanner = ClassScannerImpl.getInstance()
        if artifact_config_path:
            scanner.init(repository_root, url, commit_hash, artifact_config_path)
        else:
            scanner.init(repository_root, url, commit_hash)
        cached_files = _load_cached_class_scan_files(cache_file, retry_errors)

        last_flush = time.monotonic()
        pending: list[dict] = []

        for file in java_files:
            file_without_base = file[len(repository_root) + 1:]
            if util.stable_shard_for_key(file_without_base, shards) != shard:
                continue
            if file_without_base in cached_files:
                continue
            if _is_class_scan_file_completed(cache_file, lock_path, file_without_base, retry_errors):
                cached_files.add(file_without_base)
                continue

            classes_in_file, scan_error = _scan_classes_in_file(
                scanner,
                repository_name,
                commit_hash,
                file_without_base,
            )
            pending.extend(classes_in_file)
            if scan_error is None:
                pending.append(_build_class_scan_marker(repository_name, file_without_base, commit_hash))
            else:
                pending.append(_build_class_scan_error_marker(repository_name, file_without_base, commit_hash, scan_error))

            if _should_flush_scan_cache(
                len(pending),
                last_flush,
                merge_threshold,
                merge_interval_seconds,
            ):
                _flush_class_scan_buffers(cache_file, lock_path, pending, retry_errors)
                cached_files = _load_cached_class_scan_files(cache_file, retry_errors)
                last_flush = time.monotonic()

        _flush_class_scan_buffers(cache_file, lock_path, pending, retry_errors)

        if shards == 1:
            _finalize_class_scan_outputs(
                cache_file,
                output_file,
                error_output_file,
                expected_files,
                lock_path,
            )
