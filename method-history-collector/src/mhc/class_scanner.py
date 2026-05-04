import os
import time
from pathlib import Path

import pandas as pd
from pandas import DataFrame

import mhc.util as util
from mhc.method_scanner import (
    clone_and_checkout_commit,
    collect_files,
    _write_dataframe_csv,
    _append_dataframe_csv,
    _read_source_file_text,
)

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

SCAN_CLASS_FLUSH_INTERVAL_SECONDS = 15 * 60
_CLASS_SCAN_MARKER_PARSER = "__class_scan_marker__"
_CLASS_SCAN_MARKER_EXPRESSION = "__file_scanned__"


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
        "expression": _CLASS_SCAN_MARKER_EXPRESSION,
        "artifact": None,
        "abstract": None,
        "parent_names": None,
        "parent_fqns": None,
        "hash": commit_hash,
    }


def _load_cached_class_scan_files(cache_file: str) -> set[str]:
    if not os.path.exists(cache_file):
        return set()
    try:
        df = pd.read_csv(cache_file, usecols=["file"])
    except (ValueError, pd.errors.EmptyDataError):
        return set()
    return set(filter(None, df["file"].dropna().astype(str)))


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
) -> list[dict]:
    rows = []
    try:
        java_classes = scanner.scanClass(file_without_base)
        for jc in java_classes:
            rows.append({
                "project":      repository_name,
                "name":         jc.getName(),
                "fqn":          jc.getFqn(),
                "pkg":          jc.getPkg(),
                "url":          jc.getUrl(),
                "file":         jc.getFile(),
                "start_line":   jc.getStartLine(),
                "end_line":     jc.getEndLine(),
                "expression":   jc.getExpression(),
                "artifact":     jc.getArtifact(),
                "abstract":     jc.getAbstractClass(),
                "parent_names": jc.getParentNames(),
                "parent_fqns":  jc.getParentFqns(),
                "hash":         jc.getHash(),
            })
    except Exception:
        pass
    return rows


def scan_class(
    repository_df: DataFrame,
    repository_directory: str,
    data_directory: str,
    _cache_directory: str,
    replace: bool = False,
) -> None:
    from jpype import JClass
    ClassScannerImpl = JClass("rnd.method.parser.call.graph.service.ClassScannerImpl")

    for _, repository in repository_df.iterrows():
        scanner = ClassScannerImpl.getInstance()
        repository_name = repository["project"]
        url = repository["url"]
        commit_hash = repository["updated_hash"]
        repository_root = util.format_git_project_directory(repository_directory, repository_name)
        output_file = util.format_class_list_file(data_directory, repository_name)
        cache_file = util.format_class_cache_file(data_directory, repository_name)

        if replace:
            for f in (output_file, cache_file):
                if os.path.exists(f):
                    os.remove(f)
        elif not os.path.exists(cache_file) and _is_class_output_current(output_file, commit_hash):
            continue

        clone_and_checkout_commit(url, repository_root, commit_hash)
        scanner.init(repository_root, url, commit_hash)
        java_files = sorted(collect_files(repository_root, "*.java"))
        cached_files = _load_cached_class_scan_files(cache_file)

        last_flush = time.monotonic()
        pending: list[dict] = []

        for file in java_files:
            file_without_base = file[len(repository_root) + 1:]
            if file_without_base in cached_files:
                continue

            pending.extend(
                _scan_classes_in_file(scanner, repository_name, commit_hash, file_without_base)
            )
            pending.append(_build_class_scan_marker(repository_name, file_without_base, commit_hash))

            if time.monotonic() - last_flush >= SCAN_CLASS_FLUSH_INTERVAL_SECONDS:
                _append_dataframe_csv(cache_file, pending, CLASS_SCAN_COLUMNS)
                pending.clear()
                last_flush = time.monotonic()

        _append_dataframe_csv(cache_file, pending, CLASS_SCAN_COLUMNS)
        pending.clear()

        # Finalise: strip markers, write clean output
        if os.path.exists(cache_file):
            try:
                cache_df = pd.read_csv(cache_file)
            except pd.errors.EmptyDataError:
                cache_df = pd.DataFrame(columns=CLASS_SCAN_COLUMNS)
            cache_df = cache_df.reindex(columns=CLASS_SCAN_COLUMNS)
            out_df = cache_df[cache_df["expression"] != _CLASS_SCAN_MARKER_EXPRESSION].copy()
            out_df = util.convert_float_int_columns_to_nullable_int(out_df)
            _write_dataframe_csv(output_file, out_df, CLASS_SCAN_COLUMNS)
            os.remove(cache_file)
        else:
            _write_dataframe_csv(
                output_file, pd.DataFrame(columns=CLASS_SCAN_COLUMNS), CLASS_SCAN_COLUMNS
            )
