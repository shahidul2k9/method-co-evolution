import os
import time
import logging
from contextlib import nullcontext
from pathlib import Path

import pandas as pd
from pandas import DataFrame

import mhc.git_repository as git
import mhc.util as util
from mhc.zip import file_lock, remove_empty_directory_tree, remove_file_if_exists

CALLGRAPH_FLUSH_INTERVAL_SECONDS = 15 * 60
CALLGRAPH_SCAN_MARKER = "__scan_marker__"
CALLGRAPH_ERROR_MARKER = "__error_marker__"
CALLGRAPH_FLAG_COLUMN = "_flag"
CALLGRAPH_ERROR_COLUMN = "_error"
CALLGRAPH_ERROR_MAX_LENGTH = 256

CALLGRAPH_COLUMNS = [
    "project",
    "from_name", "to_name",
    "from_url", "to_url",
    "from_expression", "to_expression",
    "from_pkg", "to_pkg",
    "from_fqn", "to_fqn",
    "from_fqs", "from_tctracer_fqs", "from_testlinker_fqs", "from_testlinker_fqp",
    "to_fqs", "to_tctracer_fqs", "to_testlinker_fqs", "to_testlinker_fqp",
    "from_start", "from_end",
    "to_start", "to_end",
    "from_invocation", "to_invocation",
    "from_lcba", "to_lcba",
    "from_file", "to_file",
    "from_caller_url", "to_caller_url",
    "from_call_depth", "to_call_depth",
    "hash",
    "from_resolver", "to_resolver",
]

CALLGRAPH_CACHE_COLUMNS = CALLGRAPH_COLUMNS + [
    CALLGRAPH_FLAG_COLUMN,
    CALLGRAPH_ERROR_COLUMN,
]

_METHOD_SIDE_COLUMNS = [
    "name",
    "url",
    "expression",
    "pkg",
    "fqn",
    "fqs",
    "tctracer_fqs",
    "testlinker_fqs",
    "testlinker_fqp",
    "start",
    "end",
    "lcba",
    "file",
    "caller_url",
    "call_depth",
    "resolver",
]


def _collect_java_files(repository_path: str) -> list[str]:
    return sorted(map(os.fspath, Path(repository_path).rglob("*.java")))


def _load_cached_callgraph_files(cache_file: str) -> set[str]:
    if not os.path.exists(cache_file):
        return set()
    try:
        df = _read_callgraph_cache(cache_file)
        return _completed_callgraph_files(df)
    except (ValueError, pd.errors.EmptyDataError):
        return set()


def _is_callgraph_file_completed(cache_file: str, lock_path: str, file_without_base: str) -> bool:
    with file_lock(lock_path):
        return file_without_base in _completed_callgraph_files(_read_callgraph_cache(cache_file))


def _read_callgraph_cache(cache_file: str) -> pd.DataFrame:
    if not os.path.exists(cache_file):
        return pd.DataFrame(columns=CALLGRAPH_CACHE_COLUMNS)
    try:
        return pd.read_csv(cache_file, dtype=str).reindex(columns=CALLGRAPH_CACHE_COLUMNS)
    except pd.errors.EmptyDataError:
        return pd.DataFrame(columns=CALLGRAPH_CACHE_COLUMNS)


def _completed_callgraph_files(df: pd.DataFrame) -> set[str]:
    if df.empty:
        return set()
    rows = df[df[CALLGRAPH_FLAG_COLUMN] != CALLGRAPH_ERROR_MARKER]
    return set(rows["from_file"].dropna())


def _tried_callgraph_files(df: pd.DataFrame) -> set[str]:
    if df.empty:
        return set()
    return set(df["from_file"].dropna())


def _failed_callgraph_files(df: pd.DataFrame) -> set[str]:
    if df.empty:
        return set()
    completed_files = _completed_callgraph_files(df)
    error_files = set(df.loc[df[CALLGRAPH_FLAG_COLUMN] == CALLGRAPH_ERROR_MARKER, "from_file"].dropna())
    return error_files - completed_files


def _build_callgraph_scan_marker(file_without_base: str) -> dict:
    return {col: None for col in CALLGRAPH_CACHE_COLUMNS} | {
        "from_file": file_without_base,
        CALLGRAPH_FLAG_COLUMN: CALLGRAPH_SCAN_MARKER,
    }


def _build_callgraph_error_marker(file_without_base: str, error: Exception | str | None = None) -> dict:
    error_text = str(error)[:CALLGRAPH_ERROR_MAX_LENGTH] if error is not None else None
    return {col: None for col in CALLGRAPH_CACHE_COLUMNS} | {
        "from_file": file_without_base,
        CALLGRAPH_FLAG_COLUMN: CALLGRAPH_ERROR_MARKER,
        CALLGRAPH_ERROR_COLUMN: error_text,
    }


def _method_call_to_rows(mc, repository_name: str, commit_hash: str) -> list[dict]:
    def _s(v):
        return str(v) if v is not None else None

    def _i(v):
        return int(v) if v is not None else None

    from_m = mc.getMethod()
    fan_methods = list(mc.getFanMethods())
    if not fan_methods:
        return []

    from_data = {
        "project": repository_name,
        "from_name": _s(from_m.getName()),
        "from_url": _s(from_m.getUrl()),
        "from_expression": _s(from_m.getExpression()),
        "from_pkg": _s(from_m.getPkg()),
        "from_fqn": _s(from_m.getFqn()),
        "from_fqs": _s(from_m.getFqs()),
        "from_tctracer_fqs": _s(from_m.getTcTracerFqs()),
        "from_testlinker_fqs": _s(from_m.getTestlinkerFqs()),
        "from_testlinker_fqp": _s(from_m.getTestlinkerFqp()),
        "from_start": _i(from_m.getStartLine()),
        "from_end": _i(from_m.getEndLine()),
        "from_lcba": _i(from_m.getLcba()),
        "from_file": _s(from_m.getFile()),
        "from_caller_url": None,
        "from_call_depth": None,
        "from_resolver": _s(from_m.getResolver()),
        "hash": commit_hash,
    }

    rows = []
    for to_m in fan_methods:
        row = dict(from_data)
        row.update({
            "to_name": _s(to_m.getName()),
            "to_url": _s(to_m.getUrl()),
            "to_expression": _s(to_m.getExpression()),
            "to_pkg": _s(to_m.getPkg()),
            "to_fqn": _s(to_m.getFqn()),
            "to_fqs": _s(to_m.getFqs()),
            "to_tctracer_fqs": _s(to_m.getTcTracerFqs()),
            "to_testlinker_fqs": _s(to_m.getTestlinkerFqs()),
            "to_testlinker_fqp": _s(to_m.getTestlinkerFqp()),
            "to_start": _i(to_m.getStartLine()),
            "to_end": _i(to_m.getEndLine()),
            "from_invocation": _i(to_m.getInvocationLine()),
            "to_invocation": None,
            "to_lcba": _i(to_m.getLcba()),
            "to_file": _s(to_m.getFile()),
            "to_caller_url": None,
            "to_call_depth": None,
            "to_resolver": _s(to_m.getResolver()),
        })
        rows.append(row)
    return rows


def _flush_callgraph(cache_file: str, lock_path: str, pending_rows: list[dict]) -> None:
    if not pending_rows:
        return
    rows_copy = list(pending_rows)
    pending_rows.clear()
    with file_lock(lock_path):
        completed_files = _completed_callgraph_files(_read_callgraph_cache(cache_file))
        rows_copy = [
            row for row in rows_copy
            if row.get("from_file") not in completed_files
        ]
        if not rows_copy:
            return
        file_exists = os.path.exists(cache_file) and os.path.getsize(cache_file) > 0
        pd.DataFrame(rows_copy, columns=CALLGRAPH_CACHE_COLUMNS).to_csv(
            cache_file,
            mode="a" if file_exists else "w",
            header=not file_exists,
            index=False,
        )


def _fan_in_from_fan_out(fan_out_df: pd.DataFrame) -> pd.DataFrame:
    fan_in_df = pd.DataFrame(columns=CALLGRAPH_COLUMNS)
    if fan_out_df.empty:
        return fan_in_df

    fan_in_df["project"] = fan_out_df["project"]
    fan_in_df["hash"] = fan_out_df["hash"]
    for column in _METHOD_SIDE_COLUMNS:
        fan_in_df[f"from_{column}"] = fan_out_df[f"to_{column}"]
        fan_in_df[f"to_{column}"] = fan_out_df[f"from_{column}"]
    fan_in_df["from_invocation"] = None
    fan_in_df["to_invocation"] = None
    fan_in_df["from_caller_url"] = None
    fan_in_df["to_caller_url"] = None
    fan_in_df["from_call_depth"] = None
    fan_in_df["to_call_depth"] = None
    return fan_in_df.reindex(columns=CALLGRAPH_COLUMNS)


def _write_callgraph_csv(df: pd.DataFrame, output_file: str) -> None:
    df = util.convert_float_int_columns_to_nullable_int(df)
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    tmp_file = f"{output_file}.tmp"
    df.reindex(columns=CALLGRAPH_COLUMNS).to_csv(tmp_file, index=False)
    os.replace(tmp_file, output_file)


def _finalize_callgraph(
    cache_file: str,
    callgraph_output_file: str,
    fanin_output_file: str,
    error_output_file: str,
    expected_files: set[str],
    lock_path: str | None = None,
    delete_tmp: bool = True,
    delete_lock: bool = True,
) -> bool:
    context = file_lock(lock_path) if lock_path else nullcontext()
    with context:
        df = _read_callgraph_cache(cache_file)
        tried_files = _tried_callgraph_files(df)
        missing_files = expected_files - tried_files
        if missing_files:
            logging.info(
                "Skipping callgraph merge for %s; %s files have not been tried",
                Path(callgraph_output_file).stem,
                len(missing_files),
            )
            return False

        failed_files = _failed_callgraph_files(df)
        error_rows = df[df["from_file"].isin(failed_files)].copy()
        callgraph_df = df[
            df[CALLGRAPH_FLAG_COLUMN].isna()
        ].copy()

        _write_callgraph_csv(callgraph_df, callgraph_output_file)
        _write_callgraph_csv(_fan_in_from_fan_out(callgraph_df), fanin_output_file)

        if not error_rows.empty:
            os.makedirs(os.path.dirname(error_output_file), exist_ok=True)
            tmp_error_file = f"{error_output_file}.tmp"
            error_rows.reindex(columns=CALLGRAPH_CACHE_COLUMNS).to_csv(tmp_error_file, index=False)
            os.replace(tmp_error_file, error_output_file)
        elif os.path.exists(error_output_file):
            os.remove(error_output_file)

        if delete_tmp:
            remove_file_if_exists(cache_file)
            remove_file_if_exists(f"{cache_file}.tmp")
            remove_file_if_exists(f"{callgraph_output_file}.tmp")
            remove_file_if_exists(f"{fanin_output_file}.tmp")
            remove_file_if_exists(f"{error_output_file}.tmp")
    if delete_lock and lock_path:
        remove_file_if_exists(lock_path)
    return True


def execute_callgraph_per_file(
    repository_df: DataFrame,
    repository_directory: str,
    data_directory: str,
    workspace_directory: str,
    replace: bool = False,
    shards: int = 1,
    shard: int = 1,
    merge_only: bool = False,
    merge_only_delete_empty: bool = False,
    merge_only_delete_tmp: bool = False,
    merge_only_delete_lock: bool = False,
) -> None:
    CallGraphServiceImpl = None
    if not merge_only:
        from jpype import JClass
        CallGraphServiceImpl = JClass("rnd.method.parser.call.graph.service.CallGraphServiceImpl")

    for _, repository in repository_df.iterrows():
        repository_name = repository["project"]
        url = repository["url"]
        commit_hash = repository["updated_hash"]
        repository_path = util.format_git_project_directory(repository_directory, repository_name)

        cache_dir = os.path.join(workspace_directory, "data", ".callgraph")
        cache_file = os.path.join(cache_dir, f"{repository_name}.csv")
        lock_path = os.path.join(cache_dir, f"{repository_name}.lock")
        callgraph_output_file = os.path.join(data_directory, "callgraph", f"{repository_name}.csv")
        fanin_output_file = os.path.join(data_directory, "fanin", f"{repository_name}.csv")
        error_dir = os.path.join(workspace_directory, "data", ".callgraph-error")
        error_output_file = os.path.join(error_dir, f"{repository_name}.csv")

        if replace:
            for f in (cache_file, callgraph_output_file, fanin_output_file, error_output_file):
                if os.path.exists(f):
                    os.remove(f)
        elif not merge_only and shards == 1 and os.path.exists(callgraph_output_file) and os.path.exists(fanin_output_file):
            logging.info(f"Skipping callgraph for {repository_name}; outputs already exist")
            continue

        git.clone_and_checkout_commit(url, repository_path, commit_hash)
        java_files = _collect_java_files(repository_path)
        expected_files = {
            file[len(repository_path) + 1:]
            for file in java_files
        }

        if merge_only:
            merged = _finalize_callgraph(
                cache_file,
                callgraph_output_file,
                fanin_output_file,
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

        method_mapping_file = util.format_method_mapping_file(workspace_directory, data_directory, repository_name)
        if not method_mapping_file:
            logging.warning(
                f"No method mapping file found for {repository_name}. "
                f"Expected one of: {util.format_method_list_file(data_directory, repository_name)} "
                f"or {os.path.join(workspace_directory, 'method', repository_name + '.csv')}"
            )

        scanner = CallGraphServiceImpl.getInstance()
        scanner.init(url, repository_path, commit_hash, method_mapping_file)

        cached_files = _load_cached_callgraph_files(cache_file)

        last_flush_time = time.monotonic()
        pending_rows: list[dict] = []

        for file in java_files:
            file_without_base = file[len(repository_path) + 1:]
            if util.stable_shard_for_key(file_without_base, shards) != shard:
                continue
            if file_without_base in cached_files:
                continue
            if _is_callgraph_file_completed(cache_file, lock_path, file_without_base):
                cached_files.add(file_without_base)
                continue

            try:
                method_calls = scanner.findCallgraph(file_without_base)
                for mc in method_calls:
                    pending_rows.extend(_method_call_to_rows(mc, repository_name, commit_hash))
                pending_rows.append(_build_callgraph_scan_marker(file_without_base))
            except Exception as e:
                logging.warning(f"Callgraph failed for {file_without_base}: {e}")
                pending_rows.append(_build_callgraph_error_marker(file_without_base, e))

            if time.monotonic() - last_flush_time >= CALLGRAPH_FLUSH_INTERVAL_SECONDS:
                _flush_callgraph(cache_file, lock_path, pending_rows)
                cached_files = _load_cached_callgraph_files(cache_file)
                last_flush_time = time.monotonic()

        _flush_callgraph(cache_file, lock_path, pending_rows)
        if shards == 1:
            _finalize_callgraph(
                cache_file,
                callgraph_output_file,
                fanin_output_file,
                error_output_file,
                expected_files,
                lock_path,
            )
