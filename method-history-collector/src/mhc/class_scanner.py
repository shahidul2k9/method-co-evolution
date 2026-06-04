import logging
import os
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
from pandas import DataFrame

import mhc.util as util
from mhc.method_scanner import (
    clone_and_checkout_commit,
    collect_files,
    DEFAULT_SCAN_MERGE_THRESHOLD,
    SCAN_SLOW_SECONDS,
    _log_scan_cache_filter,
    _log_scan_repository_start,
    _log_slow_operation,
    _maybe_log_scan_progress,
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
    requested_rows = len(pending)
    started_at = time.monotonic()
    if not pending:
        logging.info(
            "class-scan flush skipped rows_requested=0 cache_file=%s",
            cache_file,
        )
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
        appended_rows = len(rows_copy)
        _append_dataframe_csv(
            cache_file,
            rows_copy,
            CLASS_SCAN_CACHE_COLUMNS,
            CLASS_SCAN_INTEGER_COLUMNS,
        )
    logging.info(
        "class-scan flush rows_requested=%s rows_appended=%s cache_file=%s elapsed_seconds=%.1f",
        requested_rows,
        appended_rows,
        cache_file,
        time.monotonic() - started_at,
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


def _build_class_scanner(
    ClassScannerImpl,
    repository_name: str,
    repository_root: str,
    url: str,
    commit_hash: str,
    artifact_config_path: str | None,
):
    started_at = time.monotonic()
    thread_name = threading.current_thread().name
    logging.info(
        "class-scan scanner-init start thread=%s repository_root=%s commit=%s",
        thread_name,
        repository_root,
        commit_hash,
    )
    scanner = ClassScannerImpl.getInstance()
    scanner.init(repository_name, repository_root, url, commit_hash, artifact_config_path, False)
    _log_slow_operation(
        "class-scan scanner-init finish thread=%s repository_root=%s commit=%s",
        time.monotonic() - started_at,
        thread_name,
        repository_root,
        commit_hash,
    )
    return scanner


def _scan_class_file_task(
    thread_local,
    ClassScannerImpl,
    repository_root: str,
    url: str,
    repository_name: str,
    commit_hash: str,
    artifact_config_path: str | None,
    file_without_base: str,
) -> list[dict]:
    if not hasattr(thread_local, "scanner"):
        thread_local.scanner = _build_class_scanner(
            ClassScannerImpl,
            repository_name,
            repository_root,
            url,
            commit_hash,
            artifact_config_path,
        )
    started_at = time.monotonic()
    try:
        classes, error = _scan_classes_in_file(thread_local.scanner, repository_name, commit_hash, file_without_base)
    except Exception:
        logging.warning(
            "class-scan file exception project=%s file=%s",
            repository_name,
            file_without_base,
            exc_info=True,
        )
        raise
    elapsed = time.monotonic() - started_at
    if elapsed >= SCAN_SLOW_SECONDS:
        logging.warning(
            "class-scan slow-file project=%s file=%s rows=%s elapsed_seconds=%.1f",
            repository_name,
            file_without_base,
            len(classes),
            elapsed,
        )
    rows = list(classes)
    if error is None:
        rows.append(_build_class_scan_marker(repository_name, file_without_base, commit_hash))
    else:
        rows.append(_build_class_scan_error_marker(repository_name, file_without_base, commit_hash, error))
    return rows


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
    max_workers: int = 1,
    artifact_config_path: str | None = None,
) -> None:
    ClassScannerImpl = None
    if merge_interval_seconds is None:
        merge_interval_seconds = SCAN_CLASS_FLUSH_INTERVAL_SECONDS
    if not merge_only:
        from jpype import JClass
        ClassScannerImpl = JClass("rnd.method.parser.call.graph.service.ClassScannerImpl")

    for _, repository in repository_df.iterrows():
        repository_name = util.require_project_name(repository)
        url = repository["url"]
        commit_hash = repository["updated_hash"]
        repository_started_at = time.monotonic()
        _log_scan_repository_start(
            "class-scan",
            repository_name,
            commit_hash,
            shard,
            shards,
            max_workers,
            merge_threshold,
            merge_interval_seconds,
        )
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
            logging.info(
                "class-scan skip-current project=%s output_file=%s",
                repository_name,
                output_file,
            )
            continue

        checkout_started_at = time.monotonic()
        logging.info("class-scan checkout start project=%s repository_root=%s", repository_name, repository_root)
        clone_and_checkout_commit(url, repository_root, commit_hash)
        logging.info(
            "class-scan checkout finish project=%s elapsed_seconds=%.1f",
            repository_name,
            time.monotonic() - checkout_started_at,
        )
        discovery_started_at = time.monotonic()
        java_files = sorted(collect_files(repository_root, "*.java"))
        logging.info(
            "class-scan discovery finish project=%s java_files=%s elapsed_seconds=%.1f",
            repository_name,
            len(java_files),
            time.monotonic() - discovery_started_at,
        )
        expected_files = {
            file[len(repository_root) + 1:]
            for file in java_files
        }

        if merge_only:
            logging.info("class-scan finalize start project=%s merge_only=true", repository_name)
            finalize_started_at = time.monotonic()
            merged = _finalize_class_scan_outputs(
                cache_file,
                output_file,
                error_output_file,
                expected_files,
                lock_path,
                True,
                True,
            )
            logging.info(
                "class-scan finalize finish project=%s merged=%s elapsed_seconds=%.1f",
                repository_name,
                merged,
                time.monotonic() - finalize_started_at,
            )
            if merged and merge_only_delete_empty:
                remove_empty_directory_tree(cache_dir)
                remove_empty_directory_tree(error_dir)
            continue

        os.makedirs(cache_dir, exist_ok=True)

        cached_files = _load_cached_class_scan_files(cache_file, retry_errors)
        files_to_scan = [
            file[len(repository_root) + 1:]
            for file in java_files
            if util.stable_shard_for_key(file[len(repository_root) + 1:], shards) == shard
            and file[len(repository_root) + 1:] not in cached_files
        ]
        _log_scan_cache_filter(
            "class-scan",
            repository_name,
            len(java_files),
            len(cached_files),
            len(files_to_scan),
        )

        pending: list[dict] = []
        last_flush = time.monotonic()
        scan_started_at = time.monotonic()
        last_progress_at = scan_started_at
        last_progress_completed = 0
        completed_files = 0
        produced_rows = 0
        error_count = 0
        total_files = len(files_to_scan)
        logging.info(
            "class-scan executor start project=%s submitted_files=%s max_workers=%s",
            repository_name,
            total_files,
            max_workers,
        )

        if max_workers == 1:
            scanner = _build_class_scanner(
                ClassScannerImpl,
                repository_name,
                repository_root,
                url,
                commit_hash,
                artifact_config_path,
            )
            thread_local = threading.local()
            thread_local.scanner = scanner
            for file_without_base in files_to_scan:
                try:
                    rows = _scan_class_file_task(
                        thread_local,
                        ClassScannerImpl,
                        repository_root,
                        url,
                        repository_name,
                        commit_hash,
                        artifact_config_path,
                        file_without_base,
                    )
                except Exception as exc:
                    logging.warning(
                        "class-scan file exception project=%s file=%s",
                        repository_name,
                        file_without_base,
                        exc_info=True,
                    )
                    rows = [_build_class_scan_error_marker(repository_name, file_without_base, commit_hash, exc)]
                completed_files += 1
                produced_rows += len(rows)
                if any(row.get(CLASS_SCAN_FLAG_COLUMN) == CLASS_SCAN_ERROR_MARKER for row in rows):
                    error_count += 1
                pending.extend(rows)
                last_progress_at, last_progress_completed = _maybe_log_scan_progress(
                    "class-scan",
                    repository_name,
                    completed_files,
                    total_files,
                    len(pending),
                    produced_rows,
                    error_count,
                    scan_started_at,
                    last_progress_at,
                    last_progress_completed,
                )
                if _should_flush_scan_cache(len(pending), last_flush, merge_threshold, merge_interval_seconds):
                    _flush_class_scan_buffers(cache_file, lock_path, pending, retry_errors)
                    last_flush = time.monotonic()
        else:
            thread_local = threading.local()
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _scan_class_file_task,
                        thread_local,
                        ClassScannerImpl,
                        repository_root,
                        url,
                        repository_name,
                        commit_hash,
                        artifact_config_path,
                        file_without_base,
                    ): file_without_base
                    for file_without_base in files_to_scan
                }
                for future in as_completed(futures):
                    file_without_base = futures[future]
                    try:
                        rows = future.result()
                    except Exception as exc:
                        logging.warning(
                            "class-scan future exception project=%s file=%s",
                            repository_name,
                            file_without_base,
                            exc_info=True,
                        )
                        rows = [_build_class_scan_error_marker(repository_name, file_without_base, commit_hash, exc)]
                    completed_files += 1
                    produced_rows += len(rows)
                    if any(row.get(CLASS_SCAN_FLAG_COLUMN) == CLASS_SCAN_ERROR_MARKER for row in rows):
                        error_count += 1
                    pending.extend(rows)
                    last_progress_at, last_progress_completed = _maybe_log_scan_progress(
                        "class-scan",
                        repository_name,
                        completed_files,
                        total_files,
                        len(pending),
                        produced_rows,
                        error_count,
                        scan_started_at,
                        last_progress_at,
                        last_progress_completed,
                    )
                    if _should_flush_scan_cache(len(pending), last_flush, merge_threshold, merge_interval_seconds):
                        _flush_class_scan_buffers(cache_file, lock_path, pending, retry_errors)
                        last_flush = time.monotonic()

        logging.info(
            "class-scan final-flush start project=%s pending_rows=%s",
            repository_name,
            len(pending),
        )
        _flush_class_scan_buffers(cache_file, lock_path, pending, retry_errors)

        if shards == 1:
            logging.info("class-scan finalize start project=%s", repository_name)
            finalize_started_at = time.monotonic()
            merged = _finalize_class_scan_outputs(
                cache_file,
                output_file,
                error_output_file,
                expected_files,
                lock_path,
            )
            logging.info(
                "class-scan finalize finish project=%s merged=%s elapsed_seconds=%.1f",
                repository_name,
                merged,
                time.monotonic() - finalize_started_at,
            )
        else:
            logging.info(
                "class-scan finalize skipped project=%s shard=%s/%s",
                repository_name,
                shard,
                shards,
            )
        logging.info(
            "class-scan finish project=%s completed_files=%s/%s produced_rows=%s errors=%s elapsed_seconds=%.1f",
            repository_name,
            completed_files,
            total_files,
            produced_rows,
            error_count,
            time.monotonic() - repository_started_at,
        )
