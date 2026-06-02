from __future__ import annotations

import logging
import os
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

from mhc.artifacts import has_tag
from mhc.method_scanner import clone_and_checkout_commit

TEST_SMELL_TOOL = "jnose"
PREPROCESS_COLUMNS = [
    "appName",
    "pathToTestFile",
    "pathToProductionFile",
    "from_url",
    "to_url",
    "candidateCount",
    "confidence",
]
POSTPROCESS_COLUMNS = ["project", "name", "smell", "smell_detector", "url", "smell_begin", "smell_end"]
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

SMELL_ACRONYMS = {
    "Abnormal UTF-Use": "AUU",
    "Anonymous Test": "AT",
    "Assertion Roulette": "AR",
    "Assertionless": "AL",
    "Assertionless Test": "ALT",
    "Brittle Assertion": "BA",
    "Comments Only Test": "COT",
    "Conditional Test Logic": "CTL",
    "Constructor Initialization": "CI",
    "Control Logic": "ConL",
    "Dead Field": "DF",
    "Default Test": "DT",
    "Dependent Test": "DepT",
    "Duplicate Assert": "DA",
    "Duplicated Code": "DC",
    "Eager Test": "ET",
    "Early Returning Test": "ERT",
    "Empty Method Category": "EMC",
    "Empty Shared-Fixture": "ESF",
    "Empty Test": "EmT",
    "EmptyTest": "EmT",
    "Empty Test-Method Category": "ETMC",
    "Exception Handling": "EH",
    "Exception Catching Throwing": "EH",
    "For Testers Only": "FTO",
    "General Fixture": "GF",
    "Guarded Test": "GT",
    "Ignored Test": "IgT",
    "IgnoredTest": "IgT",
    "Indirect Testing": "IT",
    "Indented Test": "InT",
    "Lack of Cohesion of Methods": "LCM",
    "Lazy Test": "LT",
    "Likely Ineffective Object-Comparison": "LIOC",
    "Long Test": "LoT",
    "Magic Number Test": "MNT",
    "Max Instance Variables": "MIV",
    "Mixed Selectors": "MS",
    "Mystery Guest": "MG",
    "Obscure In-line Setup": "OISS",
    "Overcommented Test": "OCT",
    "Overreferencing": "OF",
    "Proper Organization": "PO",
    "Print Statement": "RP",
    "Redundant Assertion": "RA",
    "Redundant Print": "RP",
    "Resource Optimism": "RO",
    "Returning Assertion": "RA",
    "Rotten Green Tests": "RT",
    "Sensitive Equality": "SE",
    "Sleepy Test": "ST",
    "Teardown Only Test": "TOT",
    "Test Code Duplication": "TCD",
    "Test Maverick": "TM",
    "Test Pollution": "TP",
    "Test Redundancy": "TR",
    "Test Run War": "TRW",
    "Test-Class Name": "TCN",
    "Test-Method Category Name": "TMC",
    "Transcripting Test": "TT",
    "TTCN-3 Smells": "TTCN",
    "Unclassified Method Category": "UMC",
    "Under-the-carpet Assertion": "UCA",
    "Under-the-carpet failing Assertion": "UCFA",
    "Unknown Test": "UT",
    "Unused Inputs": "UI",
    "Unused Shared-Fixture Variables": "USFV",
    "Unusual Test Order": "UTO",
    "Vague Header Setup": "VHS",
    "Verbose Test": "VT",
}


def run_test_smell(
    repository_df: pd.DataFrame,
    repository_directory: str,
    data_directory: str,
    jar_file_map: dict[str, str],
    repositories: list[str],
    tool_name: str,
    stage: str = "all",
    callgraph_dir: str = "callgraph",
    replace: bool = False,
    max_workers: int = 1,
) -> None:
    if tool_name != TEST_SMELL_TOOL:
        raise ValueError(f"Unsupported test-smell tool: {tool_name}")
    if stage not in {"preprocess", "execute", "postprocess", "all"}:
        raise ValueError("--stage must be one of: preprocess, execute, postprocess, all")

    selected = [repository for _, repository in repository_df[repository_df["project"].isin(repositories)].iterrows()]
    if max_workers == 1:
        for repository in selected:
            _run_test_smell_project(
                repository,
                repository_directory,
                data_directory,
                jar_file_map,
                stage,
                callgraph_dir,
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
                callgraph_dir,
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
    callgraph_dir: str,
    replace: bool,
) -> None:
    project = str(repository["project"])
    if not replace and _postprocess_file(data_directory, project).exists():
        logging.info("Skipping test-smell for %s; precomputed output already exists", project)
        return

    if stage in {"preprocess", "all"}:
        if preprocess_project(repository, repository_directory, data_directory, callgraph_dir) is None:
            return
    if stage in {"execute", "all"}:
        _ensure_repository_checkout(repository, repository_directory)
        execute_project(project, data_directory, jar_file_map)
    if stage in {"postprocess", "all"}:
        postprocess_project(repository, data_directory)


def preprocess_project(
    repository: pd.Series,
    repository_directory: str,
    data_directory: str,
    callgraph_dir: str = "callgraph",
) -> pd.DataFrame | None:
    project = str(repository["project"])
    method_file = Path(data_directory) / "method" / f"{project}.csv"
    callgraph_file = Path(data_directory) / callgraph_dir / f"{project}.csv"
    output_file = _input_file(data_directory, project)
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
    rows = callgraph_df.copy()
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
        test_path = _absolute_repo_path(repository_directory, project, test_file)
        production_path = (
            _absolute_repo_path(repository_directory, project, selected["to_file"])
            if selected["to_file"]
            else ""
        )
        output_rows.append(
            {
                "appName": project,
                "pathToTestFile": test_path,
                "pathToProductionFile": production_path,
                "from_url": _file_url(repository, test_file),
                "to_url": _file_url(repository, selected["to_file"]) if selected["to_file"] else "",
                "candidateCount": selected["candidate_count"],
                "confidence": f"{selected['confidence']:.6f}",
            }
        )

    output_df = pd.DataFrame(output_rows, columns=PREPROCESS_COLUMNS)
    output_df.to_csv(output_file, index=False)
    return output_df


def execute_project(
    project: str,
    data_directory: str,
    jar_file_map: dict[str, str],
) -> Path:
    input_file = _input_file(data_directory, project)
    output_file = _raw_output_file(data_directory, project)
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
    project = str(repository["project"])
    raw_file = _raw_output_file(data_directory, project)
    method_file = Path(data_directory) / "method" / f"{project}.csv"
    output_file = _postprocess_file(data_directory, project)
    error_file = _postprocess_error_file(data_directory, project)
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
        for method_name in _split_smell_methods(raw_row.get("testSmellMethod", "")):
            url = method_candidates.get(relative_file, {}).get(method_name, "")
            if url:
                rows.append(
                    {
                        "project": raw_project,
                        "name": method_name,
                        "smell": acronym,
                        "smell_detector": TEST_SMELL_TOOL,
                        "url": url,
                        "smell_begin": smell_begin,
                        "smell_end": smell_end,
                    }
                )
            else:
                error_rows.append(
                    {
                        "project": raw_project,
                        "name": raw_row.get("name", ""),
                        "pathFile": path_file,
                        "testSmellName": smell_name,
                        "testSmellMethod": method_name,
                        "testSmellLineBegin": smell_begin,
                        "testSmellLineEnd": smell_end,
                        "reason": f"No exact method match for {method_name} in {relative_file}",
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


def _method_candidates_by_file(method_file: Path) -> dict[str, dict[str, str]]:
    if not method_file.exists():
        return {}
    method_df = pd.read_csv(method_file, dtype=str, keep_default_na=False)
    if not {"name", "file", "url"}.issubset(method_df.columns):
        return {}
    candidates: dict[str, dict[str, str]] = {}
    for _, row in method_df.iterrows():
        file_name = str(row["file"]).replace(os.sep, "/")
        method_name = str(row["name"])
        candidates.setdefault(file_name, {}).setdefault(method_name, str(row["url"]))
    return candidates


def _split_smell_methods(value: str) -> list[str]:
    return [part.strip() for part in str(value or "").split(",") if part.strip()]


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


def _file_url(repository: pd.Series, relative_file: str) -> str:
    repository_url = str(repository.get("url", "") or "").rstrip("/")
    commit_hash = str(repository.get("updated_hash", "") or repository.get("hash", "") or "")
    if repository_url and commit_hash and relative_file:
        return f"{repository_url}/blob/{commit_hash}/{relative_file}#L1"
    return relative_file


def _absolute_repo_path(repository_directory: str, project: str, relative_file: str) -> str:
    return os.fspath(Path(repository_directory) / project / relative_file)


def _ensure_repository_checkout(repository: pd.Series, repository_directory: str) -> None:
    project = str(repository["project"])
    repository_path = Path(repository_directory) / project
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


def _input_file(data_directory: str, project: str) -> Path:
    return Path(data_directory) / ".test-smell" / TEST_SMELL_TOOL / "input" / f"{project}.csv"


def _raw_output_file(data_directory: str, project: str) -> Path:
    return Path(data_directory) / ".test-smell" / TEST_SMELL_TOOL / "output" / f"{project}.csv"


def _postprocess_error_file(data_directory: str, project: str) -> Path:
    return Path(data_directory) / ".test-smell" / TEST_SMELL_TOOL / "postprocess-error" / f"{project}.csv"


def _postprocess_file(data_directory: str, project: str) -> Path:
    return Path(data_directory) / "test-smell" / TEST_SMELL_TOOL / f"{project}.csv"
