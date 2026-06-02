import os
import os.path
import shlex
import shutil
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from pathlib import Path

import javalang
import jpype
import jpype.imports
import pandas as pd
from git import GitCommandError, Repo
from pandas import DataFrame

import mhc.util as util
from mhc.zip import file_lock, remove_empty_directory_tree, remove_file_if_exists

TEST_ANNOTATION_FQNS = {
    # JUnit 4
    "org.junit.Test",
    "org.junit.Before",
    "org.junit.After",
    "org.junit.BeforeClass",
    "org.junit.AfterClass",
    "org.junit.Ignore",

    # JUnit 5-6
    "org.junit.jupiter.api.Test",
    "org.junit.jupiter.api.ParameterizedTest",
    "org.junit.jupiter.api.RepeatedTest",
    "org.junit.jupiter.api.TestFactory",
    "org.junit.jupiter.api.TestTemplate",
    "org.junit.jupiter.api.TestClassOrder",
    "org.junit.jupiter.api.TestMethodOrder",
    "org.junit.jupiter.api.TestInstance",
    "org.junit.jupiter.api.DisplayName",
    "org.junit.jupiter.api.DisplayNameGeneration",
    "org.junit.jupiter.api.BeforeEach",
    "org.junit.jupiter.api.AfterEach",
    "org.junit.jupiter.api.BeforeAll",
    "org.junit.jupiter.api.AfterAll",
    "org.junit.jupiter.api.ParameterizedClass",
    "org.junit.jupiter.api.BeforeParameterizedClassInvocation",
    "org.junit.jupiter.api.AfterParameterizedClassInvocation",
    "org.junit.jupiter.api.ClassTemplate",
    "org.junit.jupiter.api.Nested",
    "org.junit.jupiter.api.Tag",
    "org.junit.jupiter.api.Disabled",
    "org.junit.jupiter.api.AutoClose",
    "org.junit.jupiter.api.Timeout",
    "org.junit.jupiter.api.TempDir",
    "org.junit.jupiter.api.ExtendWith",
    "org.junit.jupiter.api.RegisterExtension"


    # JUnit Theories
    "org.junit.experimental.theories.Theory",

    # TestNG
    # https://testng.org/annotations.html#_annotations

    "org.testng.annotations.Test",
    "org.testng.annotations.BeforeSuite",
    "org.testng.annotations.AfterSuite",
    "org.testng.annotations.BeforeTest",
    "org.testng.annotations.AfterTest",
    "org.testng.annotations.BeforeGroups",
    "org.testng.annotations.AfterGroups",
    "org.testng.annotations.BeforeClass",
    "org.testng.annotations.AfterClass",
    "org.testng.annotations.BeforeMethod",
    "org.testng.annotations.AfterMethod",
    "org.testng.annotations.Factory",
    # These are not related to method
    # "org.testng.annotations.DataProvider",
    # "org.testng.annotations.Listeners",
    # "org.testng.annotations.Parameters"
}
UNIT_TEST_SUPERCLASS_FQNS = {
    # JUnit 3
    "junit.framework.TestCase",

    # Android
    "android.test.AndroidTestCase",
    "android.test.InstrumentationTestCase",
}
TEST_PACKAGE_ROOT_DIRECTORY = {"test", "androidTest"}
TEST_ANNOTATION_NAMES = set(map(lambda x: x.split(".")[-1], TEST_ANNOTATION_FQNS))
METHOD_SCAN_COLUMNS = [
    "project",
    "name",
    "url",
    "artifact",
    "start_line",
    "end_line",
    "expression",
    "file",
    "pkg",
    "fqn",
    "fqs",
    "tctracer_fqs",
    "testlinker_fqs",
    "testlinker_fqp",
    "abstract",
    "parser",
    "resolver",
    "hash",
]
METHOD_SCAN_INTEGER_COLUMNS = ["start_line", "end_line", "abstract"]
METHOD_CODE_COLUMNS = [
    "project",
    "name",
    "url",
    "artifact",
    "start_line",
    "end_line",
    "code",
]
METHOD_CODE_INTEGER_COLUMNS = ["start_line", "end_line"]
METHOD_CODE_MARKER = "__scan_marker__"
METHOD_CODE_ERROR_MARKER = "__error_marker__"
METHOD_CODE_FLAG_COLUMN = "_flag"
METHOD_CODE_ERROR_COLUMN = "_error"
METHOD_CODE_KEY_COLUMN = "_key"
METHOD_CODE_ERROR_MAX_LENGTH = 256
METHOD_CODE_CACHE_COLUMNS = METHOD_CODE_COLUMNS + [
    METHOD_CODE_KEY_COLUMN,
    METHOD_CODE_FLAG_COLUMN,
    METHOD_CODE_ERROR_COLUMN,
]
SCAN_METHOD_FLUSH_INTERVAL_SECONDS = 1 * 15 * 60
DEFAULT_SCAN_MERGE_THRESHOLD = 10_000
SCAN_PROGRESS_FILE_INTERVAL = 100
SCAN_PROGRESS_SECONDS_INTERVAL = 60
SCAN_SLOW_SECONDS = 60
METHOD_SCAN_MARKER = "__scan_marker__"
METHOD_SCAN_ERROR_MARKER = "__error_marker__"
METHOD_SCAN_FLAG_COLUMN = "_flag"
METHOD_SCAN_ERROR_COLUMN = "_error"
METHOD_SCAN_ERROR_MAX_LENGTH = 256
METHOD_SCAN_CACHE_COLUMNS = METHOD_SCAN_COLUMNS + [
    METHOD_SCAN_FLAG_COLUMN,
    METHOD_SCAN_ERROR_COLUMN,
]


def _should_flush_scan_cache(
    pending_count: int,
    last_flush_time: float,
    merge_threshold: int,
    merge_interval_seconds: int,
) -> bool:
    return (
        (merge_threshold > 0 and pending_count >= merge_threshold)
        or (
            merge_interval_seconds > 0
            and time.monotonic() - last_flush_time >= merge_interval_seconds
        )
    )


def _log_scan_repository_start(
    command: str,
    repository_name: str,
    commit_hash: str,
    shard: int,
    shards: int,
    max_workers: int,
    merge_threshold: int,
    merge_interval_seconds: int,
) -> None:
    logging.info(
        "%s start project=%s commit=%s shard=%s/%s max_workers=%s merge_threshold=%s merge_interval_seconds=%s",
        command,
        repository_name,
        commit_hash,
        shard,
        shards,
        max_workers,
        merge_threshold,
        merge_interval_seconds,
    )


def _log_scan_cache_filter(
    command: str,
    repository_name: str,
    total_files: int,
    cached_files: int,
    submitted_files: int,
) -> None:
    logging.info(
        "%s cache-filter project=%s total_java_files=%s cached_files=%s submitted_files=%s",
        command,
        repository_name,
        total_files,
        cached_files,
        submitted_files,
    )


def _maybe_log_scan_progress(
    command: str,
    repository_name: str,
    completed_files: int,
    total_files: int,
    pending_rows: int,
    produced_rows: int,
    error_count: int,
    started_at: float,
    last_progress_at: float,
    last_progress_completed: int,
) -> tuple[float, int]:
    now = time.monotonic()
    should_log = (
        completed_files == total_files
        or completed_files - last_progress_completed >= SCAN_PROGRESS_FILE_INTERVAL
        or now - last_progress_at >= SCAN_PROGRESS_SECONDS_INTERVAL
    )
    if should_log:
        logging.info(
            "%s progress project=%s completed_files=%s/%s pending_rows=%s produced_rows=%s errors=%s elapsed_seconds=%.1f",
            command,
            repository_name,
            completed_files,
            total_files,
            pending_rows,
            produced_rows,
            error_count,
            now - started_at,
        )
        return now, completed_files
    return last_progress_at, last_progress_completed


def _log_slow_operation(
    message: str,
    elapsed_seconds: float,
    *args,
) -> None:
    if elapsed_seconds >= SCAN_SLOW_SECONDS:
        logging.warning(message + " elapsed_seconds=%.1f", *args, elapsed_seconds)
    else:
        logging.info(message + " elapsed_seconds=%.1f", *args, elapsed_seconds)


class Method:
    def __init__(self, file: str, artifact: str, name: str, line: int):
        self.file = file
        self.artifact = artifact
        self.name = name
        self.line = line


def _write_dataframe_csv(
    output_file: str,
    dataframe: pd.DataFrame,
    columns: list[str],
    integer_columns: list[str] | None = None,
) -> None:
    output_directory = os.path.dirname(output_file)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    temporary_output_file = f"{output_file}.tmp"
    out_df = dataframe.reindex(columns=columns)
    if integer_columns:
        out_df = util.normalize_integer_columns(out_df, integer_columns)
    out_df.to_csv(temporary_output_file, index=False)
    os.replace(temporary_output_file, output_file)


def _append_dataframe_csv(
    output_file: str,
    rows: list[dict],
    columns: list[str],
    integer_columns: list[str] | None = None,
) -> None:
    if not rows:
        return

    output_directory = os.path.dirname(output_file)
    if output_directory:
        os.makedirs(output_directory, exist_ok=True)

    file_exists = os.path.exists(output_file) and os.path.getsize(output_file) > 0
    out_df = pd.DataFrame(rows, columns=columns)
    if integer_columns:
        out_df = util.normalize_integer_columns(out_df, integer_columns)
    out_df.to_csv(
        output_file,
        mode="a" if file_exists else "w",
        header=not file_exists,
        index=False,
    )


def _build_scan_marker_row(
    repository_name: str,
    file_without_base: str,
    commit_hash: str,
) -> dict:
    return {
        "project": repository_name,
        "name": None,
        "url": None,
        "artifact": None,
        "start_line": None,
        "end_line": None,
        "expression": None,
        "file": file_without_base,
        "pkg": None,
        "fqn": None,
        "fqs": None,
        "tctracer_fqs": None,
        "testlinker_fqs": None,
        "testlinker_fqp": None,
        "abstract": None,
        "parser": None,
        "resolver": None,
        "hash": commit_hash,
        METHOD_SCAN_FLAG_COLUMN: METHOD_SCAN_MARKER,
        METHOD_SCAN_ERROR_COLUMN: None,
    }


def _build_scan_error_row(
    repository_name: str,
    file_without_base: str,
    commit_hash: str,
    error: Exception | str | None = None,
) -> dict:
    row = _build_scan_marker_row(repository_name, file_without_base, commit_hash)
    row[METHOD_SCAN_FLAG_COLUMN] = METHOD_SCAN_ERROR_MARKER
    row[METHOD_SCAN_ERROR_COLUMN] = str(error)[:METHOD_SCAN_ERROR_MAX_LENGTH] if error is not None else None
    return row


def _read_method_scan_cache(method_cache_file: str) -> pd.DataFrame:
    if not os.path.exists(method_cache_file):
        return pd.DataFrame(columns=METHOD_SCAN_CACHE_COLUMNS)
    try:
        return pd.read_csv(method_cache_file, dtype=str).reindex(columns=METHOD_SCAN_CACHE_COLUMNS)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=METHOD_SCAN_CACHE_COLUMNS)


def _completed_method_scan_files(cache_df: pd.DataFrame, retry_errors: bool = True) -> set[str]:
    if cache_df.empty:
        return set()
    rows = cache_df
    if retry_errors:
        rows = cache_df[cache_df[METHOD_SCAN_FLAG_COLUMN] != METHOD_SCAN_ERROR_MARKER]
    return set(rows["file"].dropna().astype(str))


def _tried_method_scan_files(cache_df: pd.DataFrame) -> set[str]:
    if cache_df.empty:
        return set()
    return set(cache_df["file"].dropna().astype(str))


def _failed_method_scan_files(cache_df: pd.DataFrame) -> set[str]:
    if cache_df.empty:
        return set()
    completed_files = _completed_method_scan_files(cache_df)
    error_files = set(
        cache_df.loc[
            cache_df[METHOD_SCAN_FLAG_COLUMN] == METHOD_SCAN_ERROR_MARKER,
            "file",
        ].dropna().astype(str)
    )
    return error_files - completed_files


def _load_cached_method_scan_files(method_cache_file: str, retry_errors: bool = True) -> set[str]:
    if not os.path.exists(method_cache_file):
        return set()
    return _completed_method_scan_files(_read_method_scan_cache(method_cache_file), retry_errors)


def _is_method_scan_file_completed(
    method_cache_file: str,
    lock_path: str,
    file_without_base: str,
    retry_errors: bool = True,
) -> bool:
    with file_lock(lock_path):
        return file_without_base in _completed_method_scan_files(
            _read_method_scan_cache(method_cache_file),
            retry_errors,
        )


def _evict_method_scanner_cache(
    scanner,
    repository_name: str,
    reason: str,
    completed_since_last_evict: int,
    seconds_since_last_evict: float,
) -> bool:
    started_at = time.monotonic()
    logging.info(
        "method-scan cache-evict start project=%s reason=%s completed_since_last_evict=%s seconds_since_last_evict=%.1f",
        repository_name,
        reason,
        completed_since_last_evict,
        seconds_since_last_evict,
    )
    try:
        scanner.evictCache()
        success = True
    except Exception as exc:
        logging.debug("method-scan cache-evict failed project=%s error=%s", repository_name, exc)
        success = False
    logging.info(
        "method-scan cache-evict finish project=%s success=%s elapsed_seconds=%.1f",
        repository_name,
        success,
        time.monotonic() - started_at,
    )
    return success


def _cache_evict_reason(
    completed_since_last_evict: int,
    seconds_since_last_evict: float,
    cache_evict_interval_files: int,
    cache_evict_interval_seconds: int,
) -> str | None:
    reasons = []
    if cache_evict_interval_files > 0 and completed_since_last_evict >= cache_evict_interval_files:
        reasons.append("files")
    if cache_evict_interval_seconds > 0 and seconds_since_last_evict >= cache_evict_interval_seconds:
        reasons.append("seconds")
    return "+".join(reasons) if reasons else None


def _flush_method_scan_buffers(
    method_cache_file: str,
    lock_path: str,
    pending_method_rows: list[dict],
    retry_errors: bool = True,
) -> None:
    requested_rows = len(pending_method_rows)
    started_at = time.monotonic()
    if not pending_method_rows:
        logging.info(
            "method-scan flush skipped rows_requested=0 cache_file=%s",
            method_cache_file,
        )
        return
    rows_copy = list(pending_method_rows)
    pending_method_rows.clear()
    with file_lock(lock_path):
        completed_files = _completed_method_scan_files(
            _read_method_scan_cache(method_cache_file),
            retry_errors,
        )
        rows_copy = [
            row for row in rows_copy
            if row.get("file") not in completed_files
        ]
        appended_rows = len(rows_copy)
        _append_dataframe_csv(
            method_cache_file,
            rows_copy,
            METHOD_SCAN_CACHE_COLUMNS,
            METHOD_SCAN_INTEGER_COLUMNS,
        )
    logging.info(
        "method-scan flush rows_requested=%s rows_appended=%s cache_file=%s elapsed_seconds=%.1f",
        requested_rows,
        appended_rows,
        method_cache_file,
        time.monotonic() - started_at,
    )


def _finalize_method_scan_outputs(
    method_cache_file: str,
    output_method_file: str,
    error_output_file: str,
    expected_files: set[str],
    lock_path: str | None = None,
    delete_tmp: bool = True,
    delete_lock: bool = True,
) -> bool:
    context = file_lock(lock_path) if lock_path else nullcontext()
    with context:
        cache_df = _read_method_scan_cache(method_cache_file)
        missing_files = expected_files - _tried_method_scan_files(cache_df)
        if missing_files:
            logging.info(
                "Skipping method scan merge for %s; %s files have not been tried",
                Path(output_method_file).stem,
                len(missing_files),
            )
            return False

        failed_files = _failed_method_scan_files(cache_df)
        error_rows = cache_df[cache_df["file"].isin(failed_files)].copy()
        method_df = cache_df[cache_df[METHOD_SCAN_FLAG_COLUMN].isna()].copy()
        _write_dataframe_csv(
            output_method_file,
            method_df,
            METHOD_SCAN_COLUMNS,
            METHOD_SCAN_INTEGER_COLUMNS,
        )

        if not error_rows.empty:
            _write_dataframe_csv(
                error_output_file,
                error_rows,
                METHOD_SCAN_CACHE_COLUMNS,
                METHOD_SCAN_INTEGER_COLUMNS,
            )
        elif os.path.exists(error_output_file):
            os.remove(error_output_file)

        if delete_tmp:
            remove_file_if_exists(method_cache_file)
            remove_file_if_exists(f"{method_cache_file}.tmp")
            remove_file_if_exists(f"{output_method_file}.tmp")
            remove_file_if_exists(f"{error_output_file}.tmp")
    if delete_lock and lock_path:
        remove_file_if_exists(lock_path)
    return True


def _extract_method_code(repository_root: str, file_path: str, start_line, end_line) -> str:
    if pd.isna(start_line) or pd.isna(end_line) or not file_path:
        return ""

    start_line_number = int(start_line)
    end_line_number = int(end_line)
    if start_line_number <= 0 or end_line_number < start_line_number:
        return ""

    absolute_file_path = os.path.join(repository_root, file_path)
    if not os.path.exists(absolute_file_path):
        return ""

    lines = _read_source_file_lines(absolute_file_path)
    if lines is None:
        return ""

    start_index = start_line_number - 1
    end_index = min(end_line_number, len(lines))
    if start_index >= len(lines):
        return ""

    return "".join(lines[start_index:end_index]).rstrip("\n")


def _method_code_key(row) -> str:
    url = row.get("url")
    if pd.notna(url) and str(url):
        return str(url)
    return "::".join(
        [
            str(row.get("file") or ""),
            str(row.get("name") or ""),
            str(row.get("start_line") or ""),
        ]
    )


def _read_method_code_cache(cache_file: str) -> pd.DataFrame:
    if not os.path.exists(cache_file):
        return pd.DataFrame(columns=METHOD_CODE_CACHE_COLUMNS)
    try:
        return pd.read_csv(cache_file, dtype=str).reindex(columns=METHOD_CODE_CACHE_COLUMNS)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=METHOD_CODE_CACHE_COLUMNS)


def _completed_method_code_keys(cache_df: pd.DataFrame, retry_errors: bool = True) -> set[str]:
    if cache_df.empty:
        return set()
    rows = cache_df
    if retry_errors:
        rows = cache_df[cache_df[METHOD_CODE_FLAG_COLUMN] != METHOD_CODE_ERROR_MARKER]
    return set(rows[METHOD_CODE_KEY_COLUMN].dropna().astype(str))


def _tried_method_code_keys(cache_df: pd.DataFrame) -> set[str]:
    if cache_df.empty:
        return set()
    return set(cache_df[METHOD_CODE_KEY_COLUMN].dropna().astype(str))


def _failed_method_code_keys(cache_df: pd.DataFrame) -> set[str]:
    if cache_df.empty:
        return set()
    completed_keys = _completed_method_code_keys(cache_df)
    error_keys = set(
        cache_df.loc[
            cache_df[METHOD_CODE_FLAG_COLUMN] == METHOD_CODE_ERROR_MARKER,
            METHOD_CODE_KEY_COLUMN,
        ].dropna().astype(str)
    )
    return error_keys - completed_keys


def _load_cached_method_code_keys(cache_file: str, retry_errors: bool = True) -> set[str]:
    if not os.path.exists(cache_file):
        return set()
    return _completed_method_code_keys(_read_method_code_cache(cache_file), retry_errors)


def _is_method_code_key_completed(
    cache_file: str,
    lock_path: str,
    key: str,
    retry_errors: bool = True,
) -> bool:
    with file_lock(lock_path):
        return key in _completed_method_code_keys(
            _read_method_code_cache(cache_file),
            retry_errors,
        )


def _method_code_cache_row(method_row, repository_root: str, key: str) -> dict:
    row = {
        column: method_row.get(column)
        for column in METHOD_CODE_COLUMNS
        if column != "code"
    }
    row["code"] = _extract_method_code(
        repository_root,
        method_row.get("file"),
        method_row.get("start_line"),
        method_row.get("end_line"),
    )
    row[METHOD_CODE_KEY_COLUMN] = key
    row[METHOD_CODE_FLAG_COLUMN] = None
    row[METHOD_CODE_ERROR_COLUMN] = None
    return row


def _method_code_error_row(method_row, key: str, error: Exception | str | None = None) -> dict:
    row = {
        column: method_row.get(column)
        for column in METHOD_CODE_COLUMNS
        if column != "code"
    }
    row["code"] = None
    row[METHOD_CODE_KEY_COLUMN] = key
    row[METHOD_CODE_FLAG_COLUMN] = METHOD_CODE_ERROR_MARKER
    row[METHOD_CODE_ERROR_COLUMN] = str(error)[:METHOD_CODE_ERROR_MAX_LENGTH] if error is not None else None
    return row


def _method_code_task(method_row, repository_root: str, key: str) -> dict:
    try:
        return _method_code_cache_row(method_row, repository_root, key)
    except Exception as error:
        return _method_code_error_row(method_row, key, error)


def _flush_method_code_buffers(
    cache_file: str,
    lock_path: str,
    pending_rows: list[dict],
    retry_errors: bool = True,
) -> None:
    if not pending_rows:
        return
    rows_copy = list(pending_rows)
    pending_rows.clear()
    with file_lock(lock_path):
        completed_keys = _completed_method_code_keys(
            _read_method_code_cache(cache_file),
            retry_errors,
        )
        rows_copy = [
            row for row in rows_copy
            if row.get(METHOD_CODE_KEY_COLUMN) not in completed_keys
        ]
        _append_dataframe_csv(
            cache_file,
            rows_copy,
            METHOD_CODE_CACHE_COLUMNS,
            METHOD_CODE_INTEGER_COLUMNS,
        )


def _finalize_method_code_outputs(
    cache_file: str,
    output_file: str,
    error_output_file: str,
    expected_keys: set[str],
    lock_path: str | None = None,
    delete_tmp: bool = True,
    delete_lock: bool = True,
) -> bool:
    context = file_lock(lock_path) if lock_path else nullcontext()
    with context:
        cache_df = _read_method_code_cache(cache_file)
        missing_keys = expected_keys - _tried_method_code_keys(cache_df)
        if missing_keys:
            logging.info(
                "Skipping method-code merge for %s; %s methods have not been tried",
                Path(output_file).stem,
                len(missing_keys),
            )
            return False

        failed_keys = _failed_method_code_keys(cache_df)
        error_rows = cache_df[cache_df[METHOD_CODE_KEY_COLUMN].isin(failed_keys)].copy()
        output_df = cache_df[cache_df[METHOD_CODE_FLAG_COLUMN].isna()].copy()
        _write_dataframe_csv(
            output_file,
            output_df,
            METHOD_CODE_COLUMNS,
            METHOD_CODE_INTEGER_COLUMNS,
        )

        if not error_rows.empty:
            error_rows[METHOD_CODE_ERROR_COLUMN] = error_rows[METHOD_CODE_ERROR_COLUMN].apply(
                lambda value: str(value)[:METHOD_CODE_ERROR_MAX_LENGTH] if pd.notna(value) else value
            )
            _write_dataframe_csv(
                error_output_file,
                error_rows,
                METHOD_CODE_CACHE_COLUMNS,
                METHOD_CODE_INTEGER_COLUMNS,
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


def _read_source_file_text(source_file_path: str) -> str | None:
    try:
        with open(source_file_path, "r", encoding="utf-8") as source_file:
            return source_file.read()
    except UnicodeDecodeError:
        return None


def _read_source_file_lines(source_file_path: str) -> list[str] | None:
    source_text = _read_source_file_text(source_file_path)
    if source_text is None:
        return None

    return source_text.splitlines(keepends=True)


def generate_method_code(
    repository_df: DataFrame,
    repository_directory: str,
    data_directory: str,
    workspace_directory: str | None = None,
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
    max_workers: int = 1,
) -> list[str]:
    output_files = []
    if workspace_directory is None:
        workspace_directory = data_directory
    if merge_interval_seconds is None:
        merge_interval_seconds = SCAN_METHOD_FLUSH_INTERVAL_SECONDS

    for _, repository in repository_df.iterrows():
        repository_name = repository["project"]
        repository_url = repository["url"]
        commit_hash = repository["updated_hash"]
        repository_root = util.format_git_project_directory(repository_directory, repository_name)
        input_file = util.format_method_list_file(data_directory, repository_name)
        output_file = util.format_method_code_file(data_directory, repository_name)
        cache_dir = os.path.join(workspace_directory, ".method-code")
        cache_file = os.path.join(cache_dir, f"{repository_name}.csv")
        lock_path = os.path.join(cache_dir, f"{repository_name}.lock")
        error_dir = os.path.join(workspace_directory, ".method-code-error")
        error_output_file = os.path.join(error_dir, f"{repository_name}.csv")

        if replace:
            for existing_file in (output_file, cache_file, error_output_file):
                remove_file_if_exists(existing_file)
        elif not merge_only and shards == 1 and os.path.exists(output_file) and not os.path.exists(cache_file):
            output_files.append(output_file)
            continue

        if not os.path.exists(input_file):
            logging.warning(
                "Skipping %s: method index file not found (%s). "
                "Run 'mhc scan-method' first to generate it.",
                repository_name,
                input_file,
            )
            continue

        method_df = pd.read_csv(input_file)
        missing_columns = [
            column for column in METHOD_CODE_COLUMNS if column != "code" and column not in method_df.columns
        ]
        if missing_columns:
            raise ValueError(
                f"Missing required columns in {input_file}: {', '.join(missing_columns)}"
            )

        expected_keys = {
            _method_code_key(row)
            for _, row in method_df.iterrows()
        }

        if merge_only:
            merged = _finalize_method_code_outputs(
                cache_file,
                output_file,
                error_output_file,
                expected_keys,
                lock_path,
                True,
                True,
            )
            if merged and merge_only_delete_empty:
                remove_empty_directory_tree(cache_dir)
                remove_empty_directory_tree(error_dir)
            if merged:
                output_files.append(output_file)
            continue

        clone_and_checkout_commit(repository_url, repository_root, commit_hash)
        os.makedirs(cache_dir, exist_ok=True)

        cached_keys = _load_cached_method_code_keys(cache_file, retry_errors)
        pending_rows: list[dict] = []
        last_flush = time.monotonic()
        methods_to_process = [
            (method_row, _method_code_key(method_row))
            for _, method_row in method_df.iterrows()
            if util.stable_shard_for_key(_method_code_key(method_row), shards) == shard
            and _method_code_key(method_row) not in cached_keys
        ]

        if max_workers == 1:
            row_iter = (_method_code_task(method_row, repository_root, key) for method_row, key in methods_to_process)
            for row in row_iter:
                pending_rows.append(row)
                if _should_flush_scan_cache(len(pending_rows), last_flush, merge_threshold, merge_interval_seconds):
                    _flush_method_code_buffers(cache_file, lock_path, pending_rows, retry_errors)
                    cached_keys = _load_cached_method_code_keys(cache_file, retry_errors)
                    last_flush = time.monotonic()
        else:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(_method_code_task, method_row, repository_root, key): key
                    for method_row, key in methods_to_process
                }
                for future in as_completed(futures):
                    try:
                        row = future.result()
                    except Exception as error:
                        row = _method_code_error_row({}, futures[future], error)
                    pending_rows.append(row)
                    if _should_flush_scan_cache(len(pending_rows), last_flush, merge_threshold, merge_interval_seconds):
                        _flush_method_code_buffers(cache_file, lock_path, pending_rows, retry_errors)
                        cached_keys = _load_cached_method_code_keys(cache_file, retry_errors)
                        last_flush = time.monotonic()

        _flush_method_code_buffers(cache_file, lock_path, pending_rows, retry_errors)

        if shards == 1:
            _finalize_method_code_outputs(
                cache_file,
                output_file,
                error_output_file,
                expected_keys,
                lock_path,
            )
        output_files.append(output_file)

    return output_files


def _is_method_output_current(output_method_file: str, commit_hash: str) -> bool:
    if not os.path.exists(output_method_file):
        return False

    try:
        output_df = pd.read_csv(output_method_file, usecols=["hash"])
    except (ValueError, pd.errors.EmptyDataError):
        return True

    hashes = set(output_df["hash"].dropna().astype(str))
    return not hashes or hashes == {commit_hash}


def _scan_methods_in_file(
    scanner,
    repository_name: str,
    url: str,
    commit_hash: str,
    file: str,
    file_without_base: str,
) -> tuple[list[dict], str | None]:
    methods_in_file = []

    try:
        java_methods = scanner.scanMethod(file_without_base)
        for jm in java_methods:
            methods_in_file.append(
                {
                    "project": repository_name,
                    "name": jm.getName(),
                    "url": jm.getUrl(),
                    "artifact": jm.getArtifact(),
                    "start_line": jm.getStartLine(),
                    "end_line": jm.getEndLine(),
                    "expression": jm.getExpression(),
                    "file": jm.getFile(),
                    "pkg": jm.getPkg(),
                    "fqn": jm.getFqn(),
                    "fqs": jm.getFqs(),
                    "tctracer_fqs": jm.getTcTracerFqs(),
                    "testlinker_fqs": jm.getTestlinkerFqs(),
                    "testlinker_fqp": jm.getTestlinkerFqp(),
                    "abstract": jm.getAbstractMethod(),
                    "parser": "javaparser",
                    "resolver": jm.getResolver(),
                    "hash": jm.getHash(),
                }
            )
        return methods_in_file, None
    except Exception as java_parser_error:
        try:
            java_code = _read_source_file_text(file)
            if java_code is None:
                return methods_in_file, f"Unable to read source file after JavaParser error: {java_parser_error}"
            tree = javalang.parse.parse(java_code)
            for _, node in tree.filter(javalang.tree.MethodDeclaration):
                if node.position:
                    start_line = node.position.line if node.position else None
                    methods_in_file.append(
                        {
                            "project": repository_name,
                            "name": node.name,
                            "url": util.format_to_git_url(url, commit_hash, file_without_base, start_line),
                            "artifact": "",
                            "start_line": start_line,
                            "end_line": None,
                            "expression": None,
                            "pkg": None,
                            "fqn": None,
                            "fqs": None,
                            "tctracer_fqs": None,
                            "testlinker_fqs": None,
                            "testlinker_fqp": None,
                            "abstract": None,
                            "file": file_without_base,
                            "parser": "javalang",
                            "resolver": None,
                            "hash": commit_hash,
                        }
                    )
            return methods_in_file, None
        except Exception as javalang_error:
            return methods_in_file, f"{java_parser_error}; fallback failed: {javalang_error}"

    return methods_in_file, None


def _build_method_scanner(MethodScannerImpl, repository_root: str, url: str, commit_hash: str, artifact_config_path: str | None):
    started_at = time.monotonic()
    thread_name = threading.current_thread().name
    logging.info(
        "method-scan scanner-init start thread=%s repository_root=%s commit=%s",
        thread_name,
        repository_root,
        commit_hash,
    )
    scanner = MethodScannerImpl.getInstance()
    scanner.init(repository_root, url, commit_hash, artifact_config_path, False)
    _log_slow_operation(
        "method-scan scanner-init finish thread=%s repository_root=%s commit=%s",
        time.monotonic() - started_at,
        thread_name,
        repository_root,
        commit_hash,
    )
    return scanner


def _scan_method_file_task(
    thread_local,
    MethodScannerImpl,
    repository_root: str,
    repository_name: str,
    url: str,
    commit_hash: str,
    artifact_config_path: str | None,
    file: str,
    file_without_base: str,
) -> list[dict]:
    if not hasattr(thread_local, "scanner"):
        thread_local.scanner = _build_method_scanner(MethodScannerImpl, repository_root, url, commit_hash, artifact_config_path)
    started_at = time.monotonic()
    try:
        methods, error = _scan_methods_in_file(
            thread_local.scanner,
            repository_name,
            url,
            commit_hash,
            file,
            file_without_base,
        )
    except Exception:
        logging.warning(
            "method-scan file exception project=%s file=%s",
            repository_name,
            file_without_base,
            exc_info=True,
        )
        raise
    elapsed = time.monotonic() - started_at
    if elapsed >= SCAN_SLOW_SECONDS:
        logging.warning(
            "method-scan slow-file project=%s file=%s rows=%s elapsed_seconds=%.1f",
            repository_name,
            file_without_base,
            len(methods),
            elapsed,
        )
    rows = list(methods)
    if error is None:
        rows.append(_build_scan_marker_row(repository_name, file_without_base, commit_hash))
    else:
        rows.append(_build_scan_error_row(repository_name, file_without_base, commit_hash, error))
    return rows


def scan_method(
    repository_df: DataFrame,
    repository_directory: str,
    data_directory: str,
    _workspace_directory,
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
    max_workers: int = 1,
    artifact_config_path: str | None = None,
    cache_evict_interval_seconds: int = 0,
    cache_evict_interval_files: int = 0,
):
    MethodScannerImpl = None
    if merge_interval_seconds is None:
        merge_interval_seconds = SCAN_METHOD_FLUSH_INTERVAL_SECONDS
    if not merge_only:
        from jpype import JClass
        MethodScannerImpl = JClass(
            "rnd.method.parser.call.graph.service.MethodScannerImpl"
        )

    for _, repository in repository_df.iterrows():
        repository_name = repository["project"]
        url = repository['url']
        commit_hash = repository['updated_hash']
        repository_started_at = time.monotonic()
        _log_scan_repository_start(
            "method-scan",
            repository_name,
            commit_hash,
            shard,
            shards,
            max_workers,
            merge_threshold,
            merge_interval_seconds,
        )
        dot_file_directory = util.format_git_project_directory(repository_directory, repository_name)
        output_method_file = util.format_method_list_file(f"{data_directory}", repository_name)
        method_workspace_directory = os.path.join(_workspace_directory, ".method")
        method_cache_file = os.path.join(method_workspace_directory, f"{repository_name}.csv")
        lock_path = os.path.join(method_workspace_directory, f"{repository_name}.lock")
        error_directory = os.path.join(_workspace_directory, ".method-error")
        error_output_file = os.path.join(error_directory, f"{repository_name}.csv")
        if replace:
            for existing_file in (output_method_file, method_cache_file, error_output_file):
                if os.path.exists(existing_file):
                    os.remove(existing_file)
        elif not merge_only and shards == 1 and not os.path.exists(method_cache_file) and _is_method_output_current(output_method_file, commit_hash):
            logging.info(
                "method-scan skip-current project=%s output_file=%s",
                repository_name,
                output_method_file,
            )
            continue

        checkout_started_at = time.monotonic()
        logging.info("method-scan checkout start project=%s repository_root=%s", repository_name, dot_file_directory)
        clone_and_checkout_commit(url, dot_file_directory, commit_hash)
        logging.info(
            "method-scan checkout finish project=%s elapsed_seconds=%.1f",
            repository_name,
            time.monotonic() - checkout_started_at,
        )
        discovery_started_at = time.monotonic()
        java_files = sorted(collect_files(dot_file_directory, "*.java"))
        logging.info(
            "method-scan discovery finish project=%s java_files=%s elapsed_seconds=%.1f",
            repository_name,
            len(java_files),
            time.monotonic() - discovery_started_at,
        )
        expected_files = {
            file[len(dot_file_directory) + 1:]
            for file in java_files
        }

        if merge_only:
            logging.info("method-scan finalize start project=%s merge_only=true", repository_name)
            finalize_started_at = time.monotonic()
            merged = _finalize_method_scan_outputs(
                method_cache_file,
                output_method_file,
                error_output_file,
                expected_files,
                lock_path,
                True,
                True,
            )
            logging.info(
                "method-scan finalize finish project=%s merged=%s elapsed_seconds=%.1f",
                repository_name,
                merged,
                time.monotonic() - finalize_started_at,
            )
            if merged and merge_only_delete_empty:
                remove_empty_directory_tree(method_workspace_directory)
                remove_empty_directory_tree(error_directory)
            continue

        os.makedirs(method_workspace_directory, exist_ok=True)

        cached_files = _load_cached_method_scan_files(method_cache_file, retry_errors)
        files_to_scan = [
            (file, file[len(dot_file_directory) + 1:])
            for file in java_files
            if util.stable_shard_for_key(file[len(dot_file_directory) + 1:], shards) == shard
            and file[len(dot_file_directory) + 1:] not in cached_files
        ]
        _log_scan_cache_filter(
            "method-scan",
            repository_name,
            len(java_files),
            len(cached_files),
            len(files_to_scan),
        )

        pending_method_rows: list[dict] = []
        last_flush_time = time.monotonic()
        scan_started_at = time.monotonic()
        last_progress_at = scan_started_at
        last_progress_completed = 0
        last_cache_evict_time = scan_started_at
        last_cache_evict_completed_files = 0
        completed_files = 0
        produced_rows = 0
        error_count = 0
        total_files = len(files_to_scan)
        cache_evict_scanner = None
        if cache_evict_interval_seconds > 0 or cache_evict_interval_files > 0:
            cache_evict_scanner = MethodScannerImpl.getInstance()
            logging.info(
                "method-scan cache-evict configured project=%s interval_seconds=%s interval_files=%s",
                repository_name,
                cache_evict_interval_seconds,
                cache_evict_interval_files,
            )
        logging.info(
            "method-scan executor start project=%s submitted_files=%s max_workers=%s",
            repository_name,
            total_files,
            max_workers,
        )

        if max_workers == 1:
            scanner = _build_method_scanner(MethodScannerImpl, dot_file_directory, url, commit_hash, artifact_config_path)
            thread_local = threading.local()
            thread_local.scanner = scanner
            for file, file_without_base in files_to_scan:
                try:
                    rows = _scan_method_file_task(
                        thread_local,
                        MethodScannerImpl,
                        dot_file_directory,
                        repository_name,
                        url,
                        commit_hash,
                        artifact_config_path,
                        file,
                        file_without_base,
                    )
                except Exception as exc:
                    logging.warning(
                        "method-scan file exception project=%s file=%s",
                        repository_name,
                        file_without_base,
                        exc_info=True,
                    )
                    rows = [_build_scan_error_row(repository_name, file_without_base, commit_hash, exc)]
                completed_files += 1
                produced_rows += len(rows)
                if any(row.get(METHOD_SCAN_FLAG_COLUMN) == METHOD_SCAN_ERROR_MARKER for row in rows):
                    error_count += 1
                pending_method_rows.extend(rows)
                if cache_evict_scanner is not None:
                    seconds_since_last_evict = time.monotonic() - last_cache_evict_time
                    completed_since_last_evict = completed_files - last_cache_evict_completed_files
                    reason = _cache_evict_reason(
                        completed_since_last_evict,
                        seconds_since_last_evict,
                        cache_evict_interval_files,
                        cache_evict_interval_seconds,
                    )
                    if reason is not None:
                        _evict_method_scanner_cache(
                            cache_evict_scanner,
                            repository_name,
                            reason,
                            completed_since_last_evict,
                            seconds_since_last_evict,
                        )
                        last_cache_evict_time = time.monotonic()
                        last_cache_evict_completed_files = completed_files
                last_progress_at, last_progress_completed = _maybe_log_scan_progress(
                    "method-scan",
                    repository_name,
                    completed_files,
                    total_files,
                    len(pending_method_rows),
                    produced_rows,
                    error_count,
                    scan_started_at,
                    last_progress_at,
                    last_progress_completed,
                )
                if _should_flush_scan_cache(len(pending_method_rows), last_flush_time, merge_threshold, merge_interval_seconds):
                    _flush_method_scan_buffers(method_cache_file, lock_path, pending_method_rows, retry_errors)
                    last_flush_time = time.monotonic()
        else:
            thread_local = threading.local()
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _scan_method_file_task,
                        thread_local,
                        MethodScannerImpl,
                        dot_file_directory,
                        repository_name,
                        url,
                        commit_hash,
                        artifact_config_path,
                        file,
                        file_without_base,
                    ): file_without_base
                    for file, file_without_base in files_to_scan
                }
                for future in as_completed(futures):
                    file_without_base = futures[future]
                    try:
                        rows = future.result()
                    except Exception as exc:
                        logging.warning(
                            "method-scan future exception project=%s file=%s",
                            repository_name,
                            file_without_base,
                            exc_info=True,
                        )
                        rows = [_build_scan_error_row(repository_name, file_without_base, commit_hash, exc)]
                    completed_files += 1
                    produced_rows += len(rows)
                    if any(row.get(METHOD_SCAN_FLAG_COLUMN) == METHOD_SCAN_ERROR_MARKER for row in rows):
                        error_count += 1
                    pending_method_rows.extend(rows)
                    if cache_evict_scanner is not None:
                        seconds_since_last_evict = time.monotonic() - last_cache_evict_time
                        completed_since_last_evict = completed_files - last_cache_evict_completed_files
                        reason = _cache_evict_reason(
                            completed_since_last_evict,
                            seconds_since_last_evict,
                            cache_evict_interval_files,
                            cache_evict_interval_seconds,
                        )
                        if reason is not None:
                            _evict_method_scanner_cache(
                                cache_evict_scanner,
                                repository_name,
                                reason,
                                completed_since_last_evict,
                                seconds_since_last_evict,
                            )
                            last_cache_evict_time = time.monotonic()
                            last_cache_evict_completed_files = completed_files
                    last_progress_at, last_progress_completed = _maybe_log_scan_progress(
                        "method-scan",
                        repository_name,
                        completed_files,
                        total_files,
                        len(pending_method_rows),
                        produced_rows,
                        error_count,
                        scan_started_at,
                        last_progress_at,
                        last_progress_completed,
                    )
                    if _should_flush_scan_cache(len(pending_method_rows), last_flush_time, merge_threshold, merge_interval_seconds):
                        _flush_method_scan_buffers(method_cache_file, lock_path, pending_method_rows, retry_errors)
                        last_flush_time = time.monotonic()

        logging.info(
            "method-scan final-flush start project=%s pending_rows=%s",
            repository_name,
            len(pending_method_rows),
        )
        _flush_method_scan_buffers(
            method_cache_file,
            lock_path,
            pending_method_rows,
            retry_errors,
        )
        if shards == 1:
            logging.info("method-scan finalize start project=%s", repository_name)
            finalize_started_at = time.monotonic()
            merged = _finalize_method_scan_outputs(
                method_cache_file,
                output_method_file,
                error_output_file,
                expected_files,
                lock_path,
            )
            logging.info(
                "method-scan finalize finish project=%s merged=%s elapsed_seconds=%.1f",
                repository_name,
                merged,
                time.monotonic() - finalize_started_at,
            )
        else:
            logging.info(
                "method-scan finalize skipped project=%s shard=%s/%s",
                repository_name,
                shard,
                shards,
            )
        logging.info(
            "method-scan finish project=%s completed_files=%s/%s produced_rows=%s errors=%s elapsed_seconds=%.1f",
            repository_name,
            completed_files,
            total_files,
            produced_rows,
            error_count,
            time.monotonic() - repository_started_at,
        )


def start_java_jar(jars: [str], java_options: str | None = None):
    if not jpype.isJVMStarted():
        jvm_args = shlex.split(java_options) if java_options else []
        jpype.startJVM(*jvm_args, classpath=jars)


def stop_java_jar():
    if jpype.isJVMStarted():
        jpype.shutdownJVM()


def collect_methods(repository_directory: str, path: str):
    return None


def collect_files(repository_directory: str, file_pattern: str):
    path = Path(repository_directory)
    return list(map(os.fspath, path.rglob(file_pattern)))


def clone_and_checkout_commit(repo_url, repository_directory, commit_hash):
    """Clone a GitHub repository and checkout a specific commit hash.
       Raises an exception if cloning or checking out fails.
    """
    clone_attempts = 3
    try:
        repo = None
        last_error: GitCommandError | None = None
        for attempt in range(1, clone_attempts + 1):
            try:
                if os.path.exists(repository_directory):
                    print(f"Repository already exists at {repository_directory}. Opening local checkout...")
                    repo = Repo(repository_directory)
                    if repo.bare:
                        raise Exception(f"Error: The repository at {repository_directory} is corrupted or incomplete.")
                else:
                    print(f"Cloning repository {repo_url} into {repository_directory} (attempt {attempt}/{clone_attempts})...")
                    repo = Repo.clone_from(
                        repo_url,
                        repository_directory,
                        multi_options=["--filter=blob:none", "--no-tags"],
                    )
                break
            except GitCommandError as error:
                last_error = error
                if os.path.exists(repository_directory):
                    shutil.rmtree(repository_directory, ignore_errors=True)
                if attempt == clone_attempts:
                    raise
                time.sleep(min(5, attempt))

        if repo is None:
            raise Exception(f"Failed to clone repository after {clone_attempts} attempts: {last_error}")

        # Checkout specific commit hash
        print(f"Checking out commit {commit_hash}...")
        try:
            repo.git.fetch("origin", commit_hash, "--depth", "1")
        except GitCommandError:
            repo.remotes.origin.fetch()
        repo.git.checkout(commit_hash)

        # Verify checkout success
        current_commit = repo.head.object.hexsha
        if commit_hash not in current_commit:
            raise Exception(
                f"Failed to checkout the correct commit. Expected: {commit_hash}, Got: {current_commit}")

        print(f"Successfully checked out commit: {commit_hash}")
        return current_commit

    except GitCommandError as e:
        raise Exception(f"Git command failed: {repository_directory} {str(e)}")
    except Exception as e:
        raise Exception(f"Error: {str(e)}")


def get_all_commit_info(repo_path, branch="HEAD"):
    repo = Repo(repo_path)
    commits = []

    for c in repo.iter_commits(branch):
        commits.append({
            "hash": c.hexsha,
            "author": c.author.name,
            "email": c.author.email,
            "date": c.committed_datetime,
            "message": c.message.strip(),
            "parents": [p.hexsha for p in c.parents],
        })

    return commits
