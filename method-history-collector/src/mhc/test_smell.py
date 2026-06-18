from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tarfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

import git
import pandas as pd

import mhc.util as util
from mhc.artifacts import has_tag
from mhc.command_util import load_test_smell_acronyms, parse_name_list
from mhc.method_scanner import clone_and_checkout_commit

TEST_SMELL_TOOL = "jnose"
CALLGRAPH_VARIANT = "callgraph"
HISTORY_TOOL = "historyFinder"
PREPROCESS_COLUMNS = [
    "appName",
    "pathToTestFile",
    "pathToProductionFile",
    "from_url",
    "to_url",
    "candidateCount",
    "confidence",
]
POSTPROCESS_COLUMNS = ["project", "name", "smell", "smell_detector", "url", "smell_begin", "smell_end", "loc"]
POSTPROCESS_ERROR_COLUMNS = [
    "project",
    "name",
    "pathFile",
    "testSmellName",
    "testSmellMethod",
    "testSmellLineBegin",
    "testSmellLineEnd",
    "reason",
]
BRIDGE_COLUMNS = [
    "project",
    "from_url",
    "to_url",
    "from_old_url",
    "to_old_url",
    "from_name",
    "to_name",
    "from_old_name",
    "to_old_name",
    "from_start",
    "from_end",
    "from_old_start",
    "from_old_end",
]
BRIDGE_FROM_METHOD_COLUMNS = [
    "from_url",
    "from_old_url",
    "from_name",
    "from_old_name",
    "from_start",
    "from_end",
    "from_old_start",
    "from_old_end",
]

SMELL_ACRONYMS = load_test_smell_acronyms(TEST_SMELL_TOOL)


def run_test_smell(
    repository_df: pd.DataFrame,
    repository_directory: str,
    data_directory: str,
    jar_file_map: dict[str, str],
    repositories: list[str],
    tool_name: str,
    stage: str = "all",
    replace: bool = False,
    max_workers: int = 1,
    strategies: str | list[str] | None = None,
) -> None:
    if tool_name != TEST_SMELL_TOOL:
        raise ValueError(f"Unsupported test-smell tool: {tool_name}")
    if stage not in {"preprocess", "execute", "postprocess", "all"}:
        raise ValueError("--stage must be one of: preprocess, execute, postprocess, all")

    selected = [repository for _, repository in repository_df[repository_df["project"].isin(repositories)].iterrows()]
    selected_strategies = parse_name_list(strategies)
    if selected_strategies:
        tasks = [(repository, strategy) for repository in selected for strategy in selected_strategies]
        if max_workers == 1:
            for repository, strategy in tasks:
                _run_strategy_test_smell_project(
                    repository,
                    repository_directory,
                    data_directory,
                    jar_file_map,
                    strategy,
                    stage,
                    replace,
                )
            return

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    _run_strategy_test_smell_project,
                    repository,
                    repository_directory,
                    data_directory,
                    jar_file_map,
                    strategy,
                    stage,
                    replace,
                )
                for repository, strategy in tasks
            ]
            for future in as_completed(futures):
                future.result()
        return

    if max_workers == 1:
        for repository in selected:
            _run_test_smell_project(
                repository,
                repository_directory,
                data_directory,
                jar_file_map,
                stage,
                replace,
            )
        return

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                _run_test_smell_project,
                repository,
                repository_directory,
                data_directory,
                jar_file_map,
                stage,
                replace,
            )
            for repository in selected
        ]
        for future in as_completed(futures):
            future.result()


def _run_test_smell_project(
    repository: pd.Series,
    repository_directory: str,
    data_directory: str,
    jar_file_map: dict[str, str],
    stage: str,
    replace: bool,
) -> None:
    project = util.require_project_name(repository)
    if not replace and _postprocess_file(data_directory, project, CALLGRAPH_VARIANT).exists():
        logging.info("Skipping test-smell for %s; precomputed output already exists", project)
        return

    if stage in {"preprocess", "all"}:
        if preprocess_project(repository, repository_directory, data_directory) is None:
            return
    if stage in {"execute", "all"}:
        _ensure_repository_checkout(repository, repository_directory)
        execute_project(project, data_directory, jar_file_map, CALLGRAPH_VARIANT)
    if stage in {"postprocess", "all"}:
        postprocess_project(repository, data_directory)


def _run_strategy_test_smell_project(
    repository: pd.Series,
    repository_directory: str,
    data_directory: str,
    jar_file_map: dict[str, str],
    strategy: str,
    stage: str,
    replace: bool,
) -> None:
    project = util.require_project_name(repository)
    if not replace and _postprocess_file(data_directory, project, strategy).exists():
        logging.info("Skipping test-smell for %s/%s; precomputed output already exists", strategy, project)
        return

    if stage in {"preprocess", "all"}:
        _ensure_repository_checkout(repository, repository_directory)
        if preprocess_strategy_project(repository, repository_directory, data_directory, strategy) is None:
            return
    if stage in {"execute", "all"}:
        execute_project(project, data_directory, jar_file_map, strategy)
    if stage in {"postprocess", "all"}:
        postprocess_strategy_project(repository, data_directory, strategy)


def preprocess_project(
    repository: pd.Series,
    repository_directory: str,
    data_directory: str,
) -> pd.DataFrame | None:
    project = util.require_project_name(repository)
    method_file = Path(data_directory) / "method" / f"{project}.csv"
    callgraph_file = Path(data_directory) / "callgraph" / f"{project}.csv"
    output_file = _input_file(data_directory, project, CALLGRAPH_VARIANT)
    output_file.parent.mkdir(parents=True, exist_ok=True)

    if not method_file.exists():
        logging.warning("Skipping test-smell for %s; method CSV not found: %s", project, method_file)
        return None
    if not callgraph_file.exists():
        logging.warning("Skipping test-smell for %s; callgraph CSV not found: %s", project, callgraph_file)
        return None

    method_df = pd.read_csv(method_file, dtype=str, keep_default_na=False)
    callgraph_df = pd.read_csv(callgraph_file, dtype=str, keep_default_na=False)
    _require_columns(method_df, {"url", "artifact", "file", "fqs"}, method_file)
    _require_columns(
        callgraph_df,
        {"from_url", "to_url", "from_file", "to_file", "from_fqs", "to_fqs"},
        callgraph_file,
    )

    method_by_url = method_df.drop_duplicates("url").set_index("url")
    rows = callgraph_df.drop_duplicates(["from_url", "to_url"]).copy()
    rows["from_artifact"] = rows["from_url"].map(method_by_url["artifact"])
    rows["to_artifact"] = rows["to_url"].map(method_by_url["artifact"])
    rows = rows[
        rows["from_artifact"].map(lambda value: has_tag(value, "test-case-method"))
        & rows["to_artifact"].map(lambda value: has_tag(value, "test-code"))
        & rows["from_file"].astype(bool)
        & rows["to_file"].astype(bool)
        & rows["to_file"].str.lower().str.endswith(".java")
    ].copy()

    test_files = _test_files(method_df)
    output_rows = []
    for test_file in test_files:
        candidate_rows = rows[rows["from_file"] == test_file]
        selected = _select_candidate(test_file, candidate_rows)
        production_files = sorted(
            {
                str(value)
                for value in candidate_rows.get("to_file", pd.Series(dtype=str)).dropna().astype(str)
                if value
            }
        )
        test_path = _absolute_repo_path(repository_directory, project, test_file)
        production_file = selected["to_file"] if len(production_files) == 1 else ""
        production_path = _absolute_repo_path(repository_directory, project, production_file) if production_file else ""
        output_rows.append(
            {
                "appName": project,
                "pathToTestFile": test_path,
                "pathToProductionFile": production_path,
                "from_url": _file_url(repository, test_file),
                "to_url": _file_url(repository, production_file) if production_file else "",
                "candidateCount": selected["candidate_count"],
                "confidence": f"{selected['confidence']:.6f}",
            }
        )

    output_df = pd.DataFrame(output_rows, columns=PREPROCESS_COLUMNS)
    output_df = _deduplicate_adapter_input(output_df)
    output_df.to_csv(output_file, index=False)
    return output_df


def execute_project(
    project: str,
    data_directory: str,
    jar_file_map: dict[str, str],
    variant: str = CALLGRAPH_VARIANT,
) -> Path:
    input_file = _input_file(data_directory, project, variant)
    output_file = _raw_output_file(data_directory, project, variant)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if not input_file.exists():
        raise FileNotFoundError(f"jNose input CSV not found: {input_file}")
    jar_file = _resolve_test_smell_jar(jar_file_map)
    subprocess.run(_execute_command(jar_file, input_file, output_file), check=True)
    return output_file


def _execute_command(jar_file: str, input_file: Path, output_file: Path) -> list[str]:
    return [
        "java",
        "-jar",
        jar_file,
        "--file",
        os.fspath(input_file),
        "--output",
        os.fspath(output_file),
    ]


def postprocess_project(repository: pd.Series, data_directory: str) -> pd.DataFrame:
    project = util.require_project_name(repository)
    raw_file = _raw_output_file(data_directory, project, CALLGRAPH_VARIANT)
    method_file = Path(data_directory) / "method" / f"{project}.csv"
    output_file = _postprocess_file(data_directory, project, CALLGRAPH_VARIANT)
    error_file = _postprocess_error_file(data_directory, project, CALLGRAPH_VARIANT)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    error_file.parent.mkdir(parents=True, exist_ok=True)
    if not raw_file.exists():
        raise FileNotFoundError(f"jNose raw output CSV not found: {raw_file}")

    raw_df = pd.read_csv(raw_file, sep=";", dtype=str, keep_default_na=False)
    if raw_df.empty:
        output_df = pd.DataFrame(columns=POSTPROCESS_COLUMNS)
        output_df.to_csv(output_file, index=False)
        pd.DataFrame(columns=POSTPROCESS_ERROR_COLUMNS).to_csv(error_file, index=False)
        return output_df

    _require_columns(
        raw_df,
        {"projectName", "pathFile", "testSmellName", "testSmellMethod", "testSmellLineBegin", "testSmellLineEnd"},
        raw_file,
    )
    method_candidates = _method_candidates_by_file(method_file)
    rows = []
    error_rows = []
    for _, raw_row in raw_df.iterrows():
        raw_project = raw_row.get("projectName") or project
        path_file = raw_row.get("pathFile", "")
        relative_file = _normalize_jnose_path(path_file, method_candidates.keys())
        smell_name = raw_row.get("testSmellName", "")
        acronym = SMELL_ACRONYMS.get(smell_name, smell_name)
        smell_begin = raw_row.get("testSmellLineBegin", "")
        smell_end = raw_row.get("testSmellLineEnd", "")
        method_names = _split_smell_methods(raw_row.get("testSmellMethod", ""))
        for method_index, method_name in enumerate(method_names):
            candidates = method_candidates.get(relative_file, {}).get(method_name, [])
            matches = _resolve_candidates_by_range(
                candidates,
                _smell_line_range_for_index(smell_begin, smell_end, method_index),
                "start_line",
                "end_line",
            )
            if len(matches) > 1:
                logging.warning(
                    "Multiple method rows matched test smell method %s in %s; emitting all distinct URLs",
                    method_name,
                    relative_file,
                )
            if not matches:
                error_rows.append(
                    {
                        "project": raw_project,
                        "name": raw_row.get("name", ""),
                        "pathFile": path_file,
                        "testSmellName": smell_name,
                        "testSmellMethod": method_name,
                        "testSmellLineBegin": smell_begin,
                        "testSmellLineEnd": smell_end,
                        "reason": f"No exact method match for {method_name} in {relative_file} at {smell_begin}-{smell_end}",
                    }
                )
                continue
            for match in matches:
                rows.append(
                    {
                        "project": raw_project,
                        "name": method_name,
                        "smell": acronym,
                        "smell_detector": TEST_SMELL_TOOL,
                        "url": match["url"],
                        "smell_begin": smell_begin,
                        "smell_end": smell_end,
                        "loc": "",
                    }
                )

    output_df = pd.DataFrame(rows, columns=POSTPROCESS_COLUMNS)
    output_df.to_csv(output_file, index=False)
    pd.DataFrame(error_rows, columns=POSTPROCESS_ERROR_COLUMNS).to_csv(error_file, index=False)
    return output_df


def preprocess_strategy_project(
    repository: pd.Series,
    repository_directory: str,
    data_directory: str,
    strategy: str,
) -> pd.DataFrame | None:
    project = util.require_project_name(repository)
    t2p_file = Path(data_directory) / "t2p-link" / strategy / f"{project}.csv"
    input_file = _input_file(data_directory, project, strategy)
    bridge_file = _bridge_file(data_directory, project, strategy)
    input_file.parent.mkdir(parents=True, exist_ok=True)
    bridge_file.parent.mkdir(parents=True, exist_ok=True)

    if not t2p_file.exists():
        logging.warning("Skipping test-smell for %s/%s; t2p-link CSV not found: %s", strategy, project, t2p_file)
        return None

    t2p_df = pd.read_csv(t2p_file, dtype=str, keep_default_na=False)
    _require_columns(t2p_df, {"from_url", "to_url", "from_name", "to_name"}, t2p_file)
    t2p_df = t2p_df.drop_duplicates(["from_url", "to_url"]).copy()
    history_index = _load_history_index(data_directory, project)
    bridge_rows = []
    for _, link_row in t2p_df.iterrows():
        from_url = str(link_row.get("from_url", ""))
        to_url = str(link_row.get("to_url", ""))
        from_history = _find_history(history_index, from_url, str(link_row.get("from_name", "")))
        if not from_history:
            logging.warning("Skipping t2p link for %s/%s; test method history not found: %s", strategy, project, from_url)
            continue
        from_detail = _introduction_detail(from_history)
        if not from_detail:
            logging.warning("Skipping t2p link for %s/%s; test introduction detail not found: %s", strategy, project, from_url)
            continue
        intro_commit = str(from_detail.get("commitName", "") or "")
        from_old_url = str(from_detail.get("newFileUrl", "") or "")
        from_old_name = _detail_new_method_name(from_detail) or str(link_row.get("from_name", ""))
        from_old_start = _line_from_git_url(from_old_url)
        from_old_end = _old_end_from_detail(from_old_start, from_detail)

        to_old_url = ""
        to_old_name = ""
        to_history = _find_history(history_index, to_url, str(link_row.get("to_name", ""))) if to_url else None
        if to_history and intro_commit:
            to_detail = _detail_for_commit(to_history, intro_commit)
            if to_detail:
                to_old_url = str(to_detail.get("newFileUrl", "") or "")
                to_old_name = _detail_new_method_name(to_detail) or str(link_row.get("to_name", ""))

        bridge_rows.append(
            {
                "project": project,
                "from_url": from_url,
                "to_url": to_url,
                "from_old_url": from_old_url,
                "to_old_url": to_old_url,
                "from_name": str(link_row.get("from_name", "")),
                "to_name": str(link_row.get("to_name", "")),
                "from_old_name": from_old_name,
                "to_old_name": to_old_name,
                "from_start": str(link_row.get("from_start", "")),
                "from_end": str(link_row.get("from_end", "")),
                "from_old_start": from_old_start,
                "from_old_end": from_old_end,
            }
        )

    full_bridge_df = pd.DataFrame(bridge_rows, columns=BRIDGE_COLUMNS)
    bridge_df = _deduplicate_bridge_by_from_method(full_bridge_df)
    bridge_df.to_csv(bridge_file, index=False)
    if full_bridge_df.empty:
        pd.DataFrame(columns=PREPROCESS_COLUMNS).to_csv(input_file, index=False)
        return bridge_df

    input_rows = []
    for from_old_url, group in full_bridge_df.groupby("from_old_url", sort=False):
        if not from_old_url:
            continue
        test_file = _materialize_adapter_input_file(repository_directory, data_directory, strategy, project, from_old_url)
        production_files = []
        for to_old_url in sorted({str(value) for value in group["to_old_url"].dropna() if str(value)}):
            production_files.append(
                _materialize_adapter_input_file(repository_directory, data_directory, strategy, project, to_old_url)
            )
        production_file = production_files[0] if len(set(production_files)) == 1 else ""
        input_rows.append(
            {
                "appName": project,
                "pathToTestFile": os.fspath(test_file),
                "pathToProductionFile": os.fspath(production_file) if production_file else "",
                "from_url": from_old_url,
                "to_url": _first_non_empty(group["to_old_url"]),
                "candidateCount": len({str(value) for value in group["to_old_url"].dropna() if str(value)}),
                "confidence": "1.000000",
            }
        )

    input_df = pd.DataFrame(input_rows, columns=PREPROCESS_COLUMNS)
    input_df = _deduplicate_adapter_input(input_df)
    input_df.to_csv(input_file, index=False)
    return input_df


def postprocess_strategy_project(repository: pd.Series, data_directory: str, strategy: str) -> pd.DataFrame:
    project = util.require_project_name(repository)
    raw_file = _raw_output_file(data_directory, project, strategy)
    bridge_file = _bridge_file(data_directory, project, strategy)
    output_file = _postprocess_file(data_directory, project, strategy)
    error_file = _postprocess_error_file(data_directory, project, strategy)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    error_file.parent.mkdir(parents=True, exist_ok=True)
    if not raw_file.exists():
        raise FileNotFoundError(f"jNose raw output CSV not found: {raw_file}")
    if not bridge_file.exists():
        raise FileNotFoundError(f"jNose t2p-link bridge CSV not found: {bridge_file}")

    raw_df = pd.read_csv(raw_file, sep=";", dtype=str, keep_default_na=False)
    bridge_df = pd.read_csv(bridge_file, dtype=str, keep_default_na=False)
    _require_columns(bridge_df, set(BRIDGE_COLUMNS), bridge_file)
    if raw_df.empty:
        output_df = pd.DataFrame(columns=POSTPROCESS_COLUMNS)
        output_df.to_csv(output_file, index=False)
        pd.DataFrame(columns=POSTPROCESS_ERROR_COLUMNS).to_csv(error_file, index=False)
        return output_df

    _require_columns(
        raw_df,
        {"projectName", "pathFile", "testSmellName", "testSmellMethod", "testSmellLineBegin", "testSmellLineEnd"},
        raw_file,
    )
    rows = []
    error_rows = []
    input_paths = _strategy_input_paths_by_url(data_directory, project, strategy)
    bridge_candidates = bridge_df.copy()
    bridge_candidates["_from_old_path"] = bridge_candidates["from_old_url"].map(
        lambda value: _normalized_path(input_paths.get(str(value), "")) if str(value) else ""
    )
    known_old_paths = set(bridge_candidates["_from_old_path"])
    for _, raw_row in raw_df.iterrows():
        raw_project = raw_row.get("projectName") or project
        path_file = raw_row.get("pathFile", "")
        old_path = _normalize_strategy_jnose_path(path_file, known_old_paths)
        smell_name = raw_row.get("testSmellName", "")
        acronym = SMELL_ACRONYMS.get(smell_name, smell_name)
        smell_begin = raw_row.get("testSmellLineBegin", "")
        smell_end = raw_row.get("testSmellLineEnd", "")
        method_names = _split_smell_methods(raw_row.get("testSmellMethod", ""))
        for method_index, method_name in enumerate(method_names):
            matches = bridge_candidates[
                (bridge_candidates["_from_old_path"] == old_path)
                & (bridge_candidates["from_old_name"] == method_name)
            ].drop_duplicates(BRIDGE_FROM_METHOD_COLUMNS)
            matches = _resolve_bridge_matches_by_range(
                matches,
                _smell_line_range_for_index(smell_begin, smell_end, method_index),
            )
            if len(matches) > 1:
                logging.warning(
                    "Multiple t2p-link bridge rows matched old test method %s in %s for %s/%s; emitting all distinct test methods",
                    method_name,
                    old_path,
                    strategy,
                    project,
                )
            if matches.empty:
                error_rows.append(
                    {
                        "project": raw_project,
                        "name": raw_row.get("name", ""),
                        "pathFile": path_file,
                        "testSmellName": smell_name,
                        "testSmellMethod": method_name,
                        "testSmellLineBegin": smell_begin,
                        "testSmellLineEnd": smell_end,
                        "reason": f"No bridge match for old method {method_name} in {old_path}",
                    }
                )
                continue
            for _, match in matches.iterrows():
                rows.append(
                    {
                        "project": raw_project,
                        "name": match["from_name"],
                        "smell": acronym,
                        "smell_detector": TEST_SMELL_TOOL,
                        "url": match["from_url"],
                        "smell_begin": smell_begin,
                        "smell_end": smell_end,
                        "loc": _method_loc(match.get("from_old_start", ""), match.get("from_old_end", "")),
                    }
                )

    output_df = pd.DataFrame(rows, columns=POSTPROCESS_COLUMNS)
    output_df.to_csv(output_file, index=False)
    pd.DataFrame(error_rows, columns=POSTPROCESS_ERROR_COLUMNS).to_csv(error_file, index=False)
    return output_df


def _select_candidate(test_file: str, rows: pd.DataFrame) -> dict:
    candidates = []
    if not rows.empty:
        for to_file, candidate_rows in rows.groupby("to_file", sort=True):
            candidates.append(
                {
                    "to_file": to_file,
                    "to_fqs": _first_non_empty(candidate_rows.get("to_fqs", pd.Series(dtype=str))),
                }
            )

    if not candidates:
        return {"to_file": "", "candidate_count": 0, "confidence": 0.0}

    stripped_test_name = _strip_test_marker(Path(test_file).stem)
    exact_matches = [
        candidate
        for candidate in candidates
        if Path(candidate["to_file"]).stem.lower() == stripped_test_name.lower()
    ]
    ranked_pool = exact_matches or candidates
    test_fqs = _first_non_empty(rows.get("from_fqs", pd.Series(dtype=str)))
    for candidate in ranked_pool:
        candidate["fqs_similarity"] = _normalized_similarity(test_fqs, candidate["to_fqs"])
    ranked_pool.sort(
        key=lambda candidate: (
            -candidate["fqs_similarity"],
            candidate["to_file"],
        )
    )
    selected = ranked_pool[0]
    confidence = 1.0 if exact_matches and selected["fqs_similarity"] >= 0 else selected["fqs_similarity"]
    return {
        "to_file": selected["to_file"],
        "candidate_count": len(candidates),
        "confidence": confidence,
    }


def _strip_test_marker(class_name: str) -> str:
    lowered = class_name.lower()
    suffixes = ["testcase", "tests", "test", "_estest"]
    prefixes = ["testcase", "tests", "test"]
    for suffix in suffixes:
        if lowered.endswith(suffix) and len(class_name) > len(suffix):
            return class_name[: -len(suffix)]
    for prefix in prefixes:
        if lowered.startswith(prefix) and len(class_name) > len(prefix):
            return class_name[len(prefix) :]
    return class_name


def _normalized_similarity(left: str, right: str) -> float:
    left = str(left or "")
    right = str(right or "")
    max_len = max(len(left), len(right))
    if max_len == 0:
        return 0.0
    return 1.0 - (_levenshtein(left, right) / max_len)


def _levenshtein(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, start=1):
        current = [i]
        for j, right_char in enumerate(right, start=1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (left_char != right_char),
                )
            )
        previous = current
    return previous[-1]


def _test_files(method_df: pd.DataFrame) -> list[str]:
    test_rows = method_df[method_df["artifact"].map(lambda value: has_tag(value, "test-case-method"))]
    return sorted(test_rows["file"].dropna().astype(str).unique())


def _method_candidates_by_file(method_file: Path) -> dict[str, dict[str, list[dict[str, str]]]]:
    if not method_file.exists():
        return {}
    method_df = pd.read_csv(method_file, dtype=str, keep_default_na=False)
    if not {"name", "file", "url"}.issubset(method_df.columns):
        return {}
    candidates: dict[str, dict[str, list[dict[str, str]]]] = {}
    for _, row in method_df.iterrows():
        file_name = str(row["file"]).replace(os.sep, "/")
        method_name = str(row["name"])
        candidates.setdefault(file_name, {}).setdefault(method_name, []).append(
            {
                "url": str(row["url"]),
                "start_line": str(row.get("start_line", "")),
                "end_line": str(row.get("end_line", "")),
            }
        )
    return candidates


def _split_smell_methods(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


def _split_smell_lines(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",")]


def _smell_line_range_for_index(begin_value: str, end_value: str, index: int) -> tuple[int, int] | None:
    begins = _split_smell_lines(begin_value)
    ends = _split_smell_lines(end_value)
    begin = _to_int(begins[index] if index < len(begins) else (begins[0] if begins else ""))
    end = _to_int(ends[index] if index < len(ends) else (ends[0] if ends else ""))
    if begin is None and end is None:
        return None
    if begin is None:
        begin = end
    if end is None:
        end = begin
    if begin is None or end is None:
        return None
    return (min(begin, end), max(begin, end))


def _resolve_candidates_by_range(
    candidates: list[dict[str, str]],
    smell_range: tuple[int, int] | None,
    start_column: str,
    end_column: str,
) -> list[dict[str, str]]:
    distinct = _deduplicate_dicts(candidates, ["url"])
    if len(distinct) <= 1:
        return distinct
    ranged = [
        candidate
        for candidate in distinct
        if _range_contains_smell(candidate.get(start_column, ""), candidate.get(end_column, ""), smell_range)
    ]
    return ranged or distinct


def _resolve_bridge_matches_by_range(matches: pd.DataFrame, smell_range: tuple[int, int] | None) -> pd.DataFrame:
    if len(matches) <= 1:
        return matches
    ranged = matches[
        matches.apply(
            lambda row: _range_contains_smell(row.get("from_old_start", ""), row.get("from_old_end", ""), smell_range),
            axis=1,
        )
    ]
    if not ranged.empty:
        return ranged.drop_duplicates(BRIDGE_FROM_METHOD_COLUMNS)
    return matches


def _range_contains_smell(start_value: str, end_value: str, smell_range: tuple[int, int] | None) -> bool:
    if smell_range is None:
        return False
    start = _to_int(start_value)
    end = _to_int(end_value)
    if start is None or end is None:
        return False
    smell_start, smell_end = smell_range
    return start <= smell_start and smell_end <= end


def _method_loc(start_value: str, end_value: str) -> str:
    start = _to_int(start_value)
    end = _to_int(end_value)
    if start is None or end is None or end < start:
        return ""
    return str(end - start + 1)


def _deduplicate_dicts(rows: list[dict[str, str]], keys: list[str]) -> list[dict[str, str]]:
    seen = set()
    result = []
    for row in rows:
        key = tuple(row.get(item, "") for item in keys)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _to_int(value) -> int | None:
    try:
        if value is None or value == "":
            return None
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _normalize_jnose_path(path: str, known_files) -> str:
    normalized = str(path or "").replace("\\", "/")
    known = {str(file).replace("\\", "/") for file in known_files}
    if normalized in known:
        return normalized
    for file in sorted(known, key=len, reverse=True):
        if normalized.endswith(file):
            return file
    for marker in ("/src/test/java/", "/src/test/kotlin/", "/src/test/scala/", "/src/test/groovy/", "/src/main/java/"):
        if marker in normalized:
            return normalized[normalized.index(marker) + 1 :]
    return normalized


def _normalize_strategy_jnose_path(path: str, known_files) -> str:
    normalized = _normalized_path(path)
    known = {_normalized_path(file) for file in known_files if str(file)}
    if normalized in known:
        return normalized
    for file in sorted(known, key=len, reverse=True):
        if normalized.endswith(file) or file.endswith(normalized):
            return file
    return normalized


def _normalized_path(path: str | Path) -> str:
    return os.fspath(path).replace("\\", "/")


def _file_url(repository: pd.Series, relative_file: str) -> str:
    repository_url = str(repository.get("url", "") or "").rstrip("/")
    commit_hash = str(repository.get("updated_hash", "") or repository.get("hash", "") or "")
    if repository_url and commit_hash and relative_file:
        return f"{repository_url}/blob/{commit_hash}/{relative_file}#L1"
    return relative_file


def _absolute_repo_path(repository_directory: str, project: str, relative_file: str) -> str:
    return os.fspath(Path(repository_directory) / project / relative_file)


def _deduplicate_adapter_input(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=PREPROCESS_COLUMNS)
    deduped = df.drop_duplicates(["from_url", "to_url"]).copy()
    rows = []
    for path_to_test_file, group in deduped.groupby("pathToTestFile", sort=False):
        production_files = sorted({str(value) for value in group["pathToProductionFile"].dropna() if str(value)})
        row = group.iloc[0].copy()
        if len(production_files) != 1:
            row["pathToProductionFile"] = ""
            row["to_url"] = ""
        rows.append(row.to_dict())
    return pd.DataFrame(rows, columns=PREPROCESS_COLUMNS)


def _deduplicate_bridge_by_from_method(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=BRIDGE_COLUMNS)
    return df.drop_duplicates(BRIDGE_FROM_METHOD_COLUMNS).copy()


def _load_history_index(data_directory: str, project: str) -> list[dict]:
    archive = Path(data_directory) / "method-history-gz" / HISTORY_TOOL / f"{project}.tar.gz"
    if not archive.exists():
        raise FileNotFoundError(f"Method history archive not found: {archive}")
    histories = []
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar.getmembers():
            if not member.isfile() or not member.name.endswith(".json"):
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            try:
                history = json.load(extracted)
            except json.JSONDecodeError:
                logging.warning("Skipping invalid history JSON member: %s", member.name)
                continue
            if isinstance(history, dict):
                history["_member_name"] = member.name
                histories.append(history)
    return histories


def _find_history(histories: list[dict], method_url: str, method_name: str) -> dict | None:
    target_file = _file_path_from_git_url(method_url)
    normalized_target = target_file.replace("\\", "/")
    for history in histories:
        history_name = str(history.get("functionName", "") or history.get("functionId", ""))
        history_file = str(history.get("sourceFilePath", "") or "").replace("\\", "/")
        if history_name == method_name and history_file and normalized_target.endswith(history_file):
            return history

    for history in histories:
        history_name = str(history.get("functionName", "") or history.get("functionId", ""))
        if history_name != method_name:
            continue
        for detail in _history_details(history):
            detail_file = str(
                detail.get("path", "")
                or detail.get("newPath", "")
                or detail.get("extendedDetails", {}).get("newPath", "")
                or ""
            ).replace("\\", "/")
            if detail_file and normalized_target.endswith(detail_file):
                return history
    return None


def _introduction_detail(history: dict) -> dict | None:
    details = _history_details_by_commit(history)
    for commit in _history_commits(history):
        detail = details.get(commit)
        if detail and str(detail.get("type", "")) == "Yintroduced":
            return detail
    for detail in details.values():
        if str(detail.get("type", "")) == "Yintroduced":
            return detail
    commits = _history_commits(history)
    if commits:
        return details.get(commits[-1])
    ordered_details = _history_details(history)
    return ordered_details[-1] if ordered_details else None


def _detail_for_commit(history: dict, commit_hash: str) -> dict | None:
    return _history_details_by_commit(history).get(commit_hash)


def _history_commits(history: dict) -> list[str]:
    commits = history.get("changeHistory", [])
    if isinstance(commits, list):
        return [str(commit) for commit in commits]
    return []


def _history_details(history: dict) -> list[dict]:
    details = history.get("changeHistoryDetails", {})
    if isinstance(details, dict):
        return [detail for detail in details.values() if isinstance(detail, dict)]
    if isinstance(details, list):
        return [detail for detail in details if isinstance(detail, dict)]
    return []


def _history_details_by_commit(history: dict) -> dict[str, dict]:
    details = history.get("changeHistoryDetails", {})
    if isinstance(details, dict):
        return {str(commit): detail for commit, detail in details.items() if isinstance(detail, dict)}
    by_commit = {}
    for detail in _history_details(history):
        commit = str(detail.get("commitName", "") or "")
        if commit:
            by_commit[commit] = detail
    return by_commit


def _detail_new_method_name(detail: dict) -> str:
    extended = detail.get("extendedDetails", {})
    if isinstance(extended, dict):
        return str(extended.get("newMethodName", "") or "")
    return ""


def _line_from_git_url(file_url: str) -> str:
    fragment = urlparse(str(file_url or "")).fragment
    match = re.match(r"L(\d+)", fragment)
    return match.group(1) if match else ""


def _old_end_from_detail(start_line: str, detail: dict) -> str:
    start = _to_int(start_line)
    diff_line_count = _new_side_diff_line_count(str(detail.get("diff", "") or ""))
    if start is None or diff_line_count <= 0:
        return ""
    return str(start + diff_line_count - 1)


def _new_side_diff_line_count(diff: str) -> int:
    count = 0
    for line in str(diff or "").splitlines():
        if not line:
            continue
        if line.startswith("@@") or line.startswith("---") or line.startswith("+++") or line.startswith("\\"):
            continue
        if line.startswith("+") or line.startswith(" "):
            count += 1
    return count


def _materialize_adapter_input_file(
    repository_directory: str,
    data_directory: str,
    strategy: str,
    project: str,
    file_url: str,
) -> Path:
    output_file = _adapter_input_file_path(repository_directory, strategy, project, file_url)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    if output_file.exists():
        return output_file
    try:
        output_file.write_bytes(_read_git_blob(repository_directory, project, file_url))
        return output_file
    except Exception as error:
        logging.warning(
            "Falling back to raw URL download for %s/%s input file %s: %s",
            strategy,
            project,
            file_url,
            error,
        )
    with urlopen(_raw_url(file_url), timeout=60) as response:
        output_file.write_bytes(response.read())
    return output_file


def _download_adapter_input_file(data_directory: str, strategy: str, project: str, file_url: str) -> Path:
    return _materialize_adapter_input_file(data_directory, data_directory, strategy, project, file_url)


def _read_git_blob(repository_directory: str, project: str, file_url: str) -> bytes:
    repository_path = Path(repository_directory) / project
    if not repository_path.exists():
        raise FileNotFoundError(f"repository not found: {repository_path}")
    commit_hash = _commit_from_git_url(file_url)
    relative_file = _file_path_from_git_url(file_url)
    if not commit_hash or not relative_file:
        raise ValueError(f"cannot parse commit or file path from URL: {file_url}")
    repository = git.Repo(repository_path)
    blob = repository.commit(commit_hash).tree / relative_file
    return blob.data_stream.read()


def _strategy_input_paths_by_url(data_directory: str, project: str, strategy: str) -> dict[str, str]:
    input_file = _input_file(data_directory, project, strategy)
    if not input_file.exists():
        return {}
    input_df = pd.read_csv(input_file, dtype=str, keep_default_na=False)
    if not {"from_url", "pathToTestFile"}.issubset(input_df.columns):
        return {}
    return {
        str(row["from_url"]): str(row["pathToTestFile"])
        for _, row in input_df.iterrows()
        if str(row.get("from_url", "")) and str(row.get("pathToTestFile", ""))
    }


def _adapter_input_file_path(repository_directory: str, strategy: str, project: str, file_url: str) -> Path:
    commit = _commit_from_git_url(file_url) or "unknown"
    relative_file = _file_path_from_git_url(file_url) or "unknown.java"
    return Path(repository_directory).parent / "jnose-adapter-input-file" / project / commit / relative_file


def _raw_url(file_url: str) -> str:
    parsed = urlparse(file_url)
    path = parsed.path
    if "/blob/" not in path:
        return file_url.split("#", 1)[0]
    owner_repo, blob_path = path.split("/blob/", 1)
    return f"https://raw.githubusercontent.com{owner_repo}/{blob_path}"


def _commit_from_git_url(file_url: str) -> str:
    parts = urlparse(file_url).path.strip("/").split("/")
    if "blob" not in parts:
        return ""
    blob_index = parts.index("blob")
    if blob_index + 1 >= len(parts):
        return ""
    return parts[blob_index + 1]


def _file_path_from_git_url(file_url: str) -> str:
    parts = urlparse(file_url).path.strip("/").split("/")
    if "blob" not in parts:
        return ""
    blob_index = parts.index("blob")
    if blob_index + 2 >= len(parts):
        return ""
    return "/".join(parts[blob_index + 2 :])


def _ensure_repository_checkout(repository: pd.Series, repository_directory: str) -> None:
    project = util.require_project_name(repository)
    repository_path = Path(util.format_git_project_directory(repository_directory, project))
    if repository_path.exists():
        return
    repository_url = str(repository.get("url", "") or "")
    commit_hash = str(repository.get("updated_hash", "") or repository.get("hash", "") or "")
    if not repository_url or not commit_hash:
        raise ValueError(f"Cannot checkout {project}: missing repository url or commit hash")
    clone_and_checkout_commit(repository_url, os.fspath(repository_path), commit_hash)


def _resolve_test_smell_jar(jar_file_map: dict[str, str]) -> str:
    jar_file = jar_file_map.get(TEST_SMELL_TOOL) or jar_file_map.get("JNose") or jar_file_map.get("jNose")
    if not jar_file:
        raise FileNotFoundError("No jNose jar found in jar directory")
    return jar_file


def _first_non_empty(values: pd.Series) -> str:
    for value in values.dropna().astype(str):
        if value:
            return value
    return ""


def _require_columns(df: pd.DataFrame, columns: set[str], file: Path) -> None:
    missing = sorted(columns - set(df.columns))
    if missing:
        raise ValueError(f"{file} is missing required columns: {', '.join(missing)}")


def _input_file(data_directory: str, project: str, variant: str = CALLGRAPH_VARIANT) -> Path:
    return Path(data_directory) / ".test-smell" / TEST_SMELL_TOOL / variant / "jnose-adapter-input" / f"{project}.csv"


def _raw_output_file(data_directory: str, project: str, variant: str = CALLGRAPH_VARIANT) -> Path:
    return Path(data_directory) / ".test-smell" / TEST_SMELL_TOOL / variant / "jnose-adapter-output" / f"{project}.csv"


def _postprocess_error_file(data_directory: str, project: str, variant: str = CALLGRAPH_VARIANT) -> Path:
    return Path(data_directory) / ".test-smell" / TEST_SMELL_TOOL / variant / "postprocess-error" / f"{project}.csv"


def _postprocess_file(data_directory: str, project: str, variant: str = CALLGRAPH_VARIANT) -> Path:
    return Path(data_directory) / "test-smell" / TEST_SMELL_TOOL / variant / f"{project}.csv"


def _bridge_file(data_directory: str, project: str, strategy: str) -> Path:
    return Path(data_directory) / ".test-smell" / TEST_SMELL_TOOL / strategy / "t2p-link-bridge" / f"{project}.csv"
