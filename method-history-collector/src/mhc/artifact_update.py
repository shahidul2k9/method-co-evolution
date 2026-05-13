from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
from pandas import DataFrame

import mhc.util as util
from mhc.artifacts import encode_tags, is_test_code, is_test_resource, is_production_resource, split_tags
from mhc.method_scanner import clone_and_checkout_commit


@dataclass
class _ArtifactUpdateStats:
    total_rows: int = 0
    processed_rows: int = 0
    skipped_rows: int = 0
    changed_rows: int = 0
    unchanged_rows: int = 0
    classified_files: int = 0
    parsed_java_files: int = 0
    fallback_method_rows: int = 0
    resource_rows: int = 0


def update_artifacts(
    repository_df: DataFrame,
    repository_directory: str,
    data_directory: str,
    artifact_config_path: str | None,
    targets: list[str],
    dry_run: bool = False,
    backup: bool = False,
    replace: bool = False,
) -> None:
    unsupported = sorted(set(targets) - {"method", "class"})
    if unsupported:
        raise ValueError(f"Unsupported artifact-update target(s): {', '.join(unsupported)}")

    from jpype import JClass

    PathClass = JClass("java.nio.file.Path")
    Detector = JClass("rnd.method.parser.call.graph.artifact.TestArtifactDetector")

    for _, repository in repository_df.iterrows():
        repository_name = repository["project"]
        url = repository["url"]
        commit_hash = repository["updated_hash"]
        repo_root = util.format_git_project_directory(repository_directory, repository_name)
        clone_and_checkout_commit(url, repo_root, commit_hash)

        config_path = PathClass.of(artifact_config_path) if artifact_config_path else None
        detector = Detector.load(PathClass.of(repo_root), repository_name, config_path)

        if "method" in targets:
            _update_csv(
                util.format_method_list_file(data_directory, repository_name),
                repo_root,
                detector,
                dry_run,
                backup,
                replace,
                is_method=True,
            )
        if "class" in targets:
            _update_csv(
                util.format_class_list_file(data_directory, repository_name),
                repo_root,
                detector,
                dry_run,
                backup,
                replace,
                is_method=False,
            )


def _update_csv(
    csv_file: str,
    repo_root: str,
    detector,
    dry_run: bool,
    backup: bool,
    replace: bool,
    is_method: bool,
) -> None:
    if not os.path.exists(csv_file):
        print(f"{csv_file}: skipped, CSV file does not exist")
        return
    df = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_filter=False)
    if "artifact" not in df.columns or "file" not in df.columns:
        print(f"{csv_file}: skipped, required columns are missing")
        return

    stats = _ArtifactUpdateStats(total_rows=len(df))
    original = df["artifact"].copy()
    file_context_cache: dict[tuple[str, str], str] = {}
    method_artifact_cache: dict[tuple[str, str], dict[tuple[str, str], str]] = {}
    processed_indexes = []

    for index, row in df.iterrows():
        rel_file = str(row.get("file") or "")
        pkg = str(row.get("pkg") or "")
        if not rel_file:
            stats.skipped_rows += 1
            continue
        stats.processed_rows += 1
        processed_indexes.append(index)
        context = file_context_cache.get((rel_file, pkg))
        if context is None:
            context = _classify_file(detector, repo_root, rel_file, pkg)
            file_context_cache[(rel_file, pkg)] = context
        if is_test_resource(context) or is_production_resource(context):
            stats.resource_rows += 1
            df.at[index, "artifact"] = context
            continue
        if is_method and is_test_code(context):
            artifacts = method_artifact_cache.get((rel_file, pkg))
            if artifacts is None:
                artifacts = _classify_methods(detector, repo_root, rel_file, pkg)
                method_artifact_cache[(rel_file, pkg)] = artifacts
            artifact = artifacts.get((str(row.get("name") or ""), _normalize_line(row.get("start_line") or "")))
            if artifact is None:
                stats.fallback_method_rows += 1
                artifact = encode_tags([*split_tags(context), "test-utility"])
            df.at[index, "artifact"] = artifact
        else:
            df.at[index, "artifact"] = context

    if processed_indexes:
        stats.changed_rows = int((original.loc[processed_indexes] != df.loc[processed_indexes, "artifact"]).sum())
    stats.unchanged_rows = stats.processed_rows - stats.changed_rows
    stats.classified_files = len(file_context_cache)
    stats.parsed_java_files = len(method_artifact_cache)

    should_write = not dry_run and (stats.changed_rows > 0 or replace)
    if dry_run:
        action = "dry run, no write performed"
    elif should_write and stats.changed_rows == 0:
        action = "wrote CSV because --replace"
    elif should_write:
        action = "wrote updated CSV"
    else:
        action = "already up to date, no write performed"
    print(_format_update_summary(csv_file, stats, action))

    if not should_write:
        return
    if backup:
        csv_path = Path(csv_file)
        shutil.copy2(csv_file, csv_path.with_name(f"bk_{csv_path.name}"))
    tmp_file = f"{csv_file}.tmp"
    df.to_csv(tmp_file, index=False)
    os.replace(tmp_file, csv_file)


def _format_update_summary(csv_file: str, stats: _ArtifactUpdateStats, action: str) -> str:
    return (
        f"{csv_file}: total {stats.total_rows} row(s), processed {stats.processed_rows} row(s), "
        f"{stats.changed_rows} changed, {stats.unchanged_rows} unchanged"
        f"{_format_optional_count(stats.skipped_rows, 'skipped')}; "
        f"{stats.classified_files} file(s) classified, "
        f"{stats.parsed_java_files} Java file(s) parsed"
        f"{_format_optional_count(stats.resource_rows, 'resource')}"
        f"{_format_optional_count(stats.fallback_method_rows, 'fallback')}; "
        f"{action}"
    )


def _format_optional_count(count: int, label: str) -> str:
    return f", {count} {label}" if count else ""


def _classify_file(detector, repo_root: str, rel_file: str, pkg: str) -> str:
    from jpype import JClass

    PathClass = JClass("java.nio.file.Path")
    package_name = pkg or _read_package(Path(repo_root) / rel_file)
    classification = detector.classify(PathClass.of(str(Path(repo_root) / rel_file)), package_name)
    return str(classification.encodedArtifact())


def _classify_methods(detector, repo_root: str, rel_file: str, pkg: str) -> dict[tuple[str, str], str]:
    from jpype import JClass

    PathClass = JClass("java.nio.file.Path")
    package_name = pkg or _read_package(Path(repo_root) / rel_file)
    try:
        classifications = detector.classifyMethodArtifacts(PathClass.of(str(Path(repo_root) / rel_file)), package_name)
    except BaseException as error:
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"{rel_file}: method artifact parse failed, falling back to file-level artifact ({type(error).__name__})")
        _request_java_gc()
        return {}
    result: dict[tuple[str, str], str] = {}
    for classification in classifications:
        method_name = str(classification.methodName() or "")
        start_line = _normalize_line(classification.startLine())
        if method_name and start_line:
            result[(method_name, start_line)] = str(classification.encodedArtifact())
    return result


def _request_java_gc() -> None:
    try:
        from jpype import JClass

        JClass("java.lang.System").gc()
    except BaseException:
        return


def _normalize_line(value) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return text


def _read_package(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    import re
    match = re.search(r"^\s*package\s+([\w.]+)\s*;", text, re.MULTILINE)
    return match.group(1) if match else ""
