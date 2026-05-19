import os
import argparse
import gc
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from pytctracer.techniques.combined import Combined
from pytctracer.techniques.last_call_before_assert import LastCallBeforeAssert
from pytctracer.techniques.levenshtein_distance import *
from pytctracer.techniques.longest_common_subsequence import *
from pytctracer.techniques.naming_conventions import *
from pytctracer.techniques.tarantula import Tarantula
from pytctracer.techniques.tfidf import TFIDF

import mhc.util as util
from ptc.experiment_util import build_experiment_parser, resolve_experiment_filters, resolve_experiment_paths, select_named_items
from ptc.link_strategy import STRATEGY_KEYS

# ---------------------------
# Techniques
# ---------------------------

nc = NamingConventions()
ncc = NamingConventionsContains()
ld = LevenshteinDistance()
lcsUnit = LongestCommonSubsequenceUnit()
lcsBoth = LongestCommonSubsequenceBoth()
lcba = LastCallBeforeAssert()
tarantula = Tarantula()
tfidf = TFIDF()
combined = Combined()

def llm_strategy_directory_names() -> list[str]:
    return [
        STRATEGY_KEYS[strategy]
        for strategy in STRATEGY_KEYS
        if strategy.name.startswith("LLM_")
    ]


def build_parser():
    parser = build_experiment_parser(
        "Generate test-to-production technique scores.",
        include_tools=False,
        include_strategies=False,
        include_experiment=True,
        projects_help="Comma-separated project names to process.",
    )
    parser.add_argument(
        "--isolate-projects",
        dest="isolate_projects",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Run each selected project in a fresh Python process to avoid cumulative memory growth.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip projects whose t2p-tech output CSV already exists.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Regenerate outputs even when t2p-tech output CSVs already exist.",
    )
    return parser


def apply_llm_techniques(
    t2p_candidate_df: pd.DataFrame,
    project: str,
    llm_directory_names: list[str],
    llm_prediction_root: Path,
) -> pd.DataFrame:
    enriched_df = t2p_candidate_df.copy()

    for directory_name in llm_directory_names:
        technique_name = directory_name if directory_name.startswith("llm_") else f"llm_{directory_name}"
        column_name = f"tech_{technique_name}"
        prediction_file = llm_prediction_root / directory_name / f"{project}.csv"

        if not prediction_file.exists():
            enriched_df[column_name] = pd.Series([pd.NA] * len(enriched_df), dtype="Int64")
            continue

        prediction_df = pd.read_csv(prediction_file, keep_default_na=False, na_filter=False)
        required_columns = {"from_url", "to_url", "label_pred"}
        missing_columns = required_columns.difference(prediction_df.columns)
        if missing_columns:
            raise ValueError(
                f"Prediction file {prediction_file} is missing required columns: {sorted(missing_columns)}"
            )

        llm_match_df = (
            prediction_df.loc[:, ["from_url", "to_url", "label_pred"]]
            .drop_duplicates(subset=["from_url", "to_url"], keep="last")
            .rename(columns={"label_pred": column_name})
        )
        llm_match_df[column_name] = pd.to_numeric(llm_match_df[column_name], errors="coerce").astype("Int64")
        enriched_df = enriched_df.merge(llm_match_df, on=["from_url", "to_url"], how="left")

    return enriched_df


def apply_testlinker_technique(
    t2p_candidate_df: pd.DataFrame,
    project: str,
    testlinker_prediction_root: Path,
    strategy_name: str = "testlinker",
) -> pd.DataFrame:
    enriched_df = t2p_candidate_df.copy()
    column_name = strategy_name if strategy_name.startswith("tech_") else f"tech_{strategy_name}"
    prediction_file = testlinker_prediction_root / f"{project}.csv"

    if not prediction_file.exists():
        enriched_df[column_name] = pd.Series([pd.NA] * len(enriched_df), dtype="Int64")
        return enriched_df

    prediction_df = pd.read_csv(prediction_file, keep_default_na=False, na_filter=False)
    required_columns = {"from_url", "to_url", "label_pred"}
    missing_columns = required_columns.difference(prediction_df.columns)
    if missing_columns:
        raise ValueError(
            f"Prediction file {prediction_file} is missing required columns: {sorted(missing_columns)}"
        )

    testlinker_match_df = (
        prediction_df.loc[:, ["from_url", "to_url", "label_pred"]]
        .drop_duplicates(subset=["from_url", "to_url"], keep="last")
        .rename(columns={"label_pred": column_name})
    )
    testlinker_match_df[column_name] = pd.to_numeric(testlinker_match_df[column_name], errors="coerce").astype("Int64")
    return enriched_df.merge(testlinker_match_df, on=["from_url", "to_url"], how="left")


# ---------------------------
# Confidence computation
# ---------------------------

TECHNIQUE_COLUMNS = [
    "tech_nc",
    "tech_ncc",
    "tech_lcs_b",
    "tech_lcs_u",
    "tech_leven",
    "tech_lcba",
    "tech_tarantula",
    "tech_tfidf",
    "tech_combined",
]


def empty_scores_for_tests(test_names_tuple: list[tuple[str, str]]) -> dict[str, dict[str, float]]:
    return {test_key: {} for test_key, _ in test_names_tuple}


def _method_name(value: object) -> str:
    return str(value or "").lower()


def _call_depth(row: pd.Series) -> int:
    if "to_call_depth" not in row or row["to_call_depth"] == "":
        return 1

    depth = pd.to_numeric(row["to_call_depth"], errors="coerce")
    if pd.isna(depth) or depth < 1:
        return 1

    return int(depth)


def build_traceability_inputs(t2p_candidate_df: pd.DataFrame):
    function_names = {}
    test_names = {}
    functions_called_by_tests = defaultdict(set)
    tests_that_call_functions = defaultdict(set)
    functions_called_by_test_depth = defaultdict(dict)
    functions_called_by_test_before_assert = defaultdict(set)

    for _, row in t2p_candidate_df.iterrows():
        test_key = row["from_url"]
        function_key = row["to_url"]
        test_names[test_key] = _method_name(row["from_name"])
        function_names[function_key] = _method_name(row["to_name"])
        functions_called_by_tests[test_key].add(function_key)
        tests_that_call_functions[function_key].add(test_key)

        if "to_lcba" in row and pd.to_numeric(row["to_lcba"], errors="coerce") > 0:
            functions_called_by_test_before_assert[test_key].add(function_key)

        depth = _call_depth(row)
        existing_depth = functions_called_by_test_depth[test_key].get(function_key)
        if existing_depth is None or depth < existing_depth:
            functions_called_by_test_depth[test_key][function_key] = depth

    function_names_tuple = list(function_names.items())
    test_names_tuple = list(test_names.items())

    return (
        function_names_tuple,
        test_names_tuple,
        functions_called_by_tests,
        tests_that_call_functions,
        functions_called_by_test_depth,
        functions_called_by_test_before_assert,
    )


def compute_technique_scores(t2p_candidate_df: pd.DataFrame) -> dict[str, dict[str, dict[str, float]]]:
    (
        function_names_tuple,
        test_names_tuple,
        functions_called_by_tests,
        tests_that_call_functions,
        functions_called_by_test_depth,
        functions_called_by_test_before_assert,
    ) = build_traceability_inputs(t2p_candidate_df)

    tarantula_scores = (
        tarantula.run(
            function_names_tuple=function_names_tuple,
            test_names_tuple=test_names_tuple,
            functions_called_by_tests=functions_called_by_tests,
            tests_that_call_functions=tests_that_call_functions,
            functions_called_by_test_depth=functions_called_by_test_depth,
        )
        if len(test_names_tuple) > 1
        else empty_scores_for_tests(test_names_tuple)
    )

    scores = {
        "tech_nc": nc.run(
            function_names_tuple=function_names_tuple,
            test_names_tuple=test_names_tuple,
            functions_called_by_tests=functions_called_by_tests,
        ),
        "tech_ncc": ncc.run(
            function_names_tuple=function_names_tuple,
            test_names_tuple=test_names_tuple,
            functions_called_by_tests=functions_called_by_tests,
        ),
        "tech_lcs_b": lcsBoth.run(
            function_names_tuple=function_names_tuple,
            test_names_tuple=test_names_tuple,
            functions_called_by_tests=functions_called_by_tests,
            functions_called_by_test_depth=functions_called_by_test_depth,
        ),
        "tech_lcs_u": lcsUnit.run(
            function_names_tuple=function_names_tuple,
            test_names_tuple=test_names_tuple,
            functions_called_by_tests=functions_called_by_tests,
            functions_called_by_test_depth=functions_called_by_test_depth,
        ),
        "tech_leven": ld.run(
            function_names_tuple=function_names_tuple,
            test_names_tuple=test_names_tuple,
            functions_called_by_tests=functions_called_by_tests,
            functions_called_by_test_depth=functions_called_by_test_depth,
        ),
        "tech_lcba": lcba.run(
            function_names_tuple=function_names_tuple,
            test_names_tuple=test_names_tuple,
            functions_called_by_tests=functions_called_by_tests,
            functions_called_by_test_before_assert=functions_called_by_test_before_assert,
        ),
        "tech_tarantula": tarantula_scores,
        "tech_tfidf": tfidf.run(
            function_names_tuple=function_names_tuple,
            test_names_tuple=test_names_tuple,
            functions_called_by_tests=functions_called_by_tests,
            tests_that_call_functions=tests_that_call_functions,
            functions_called_by_test_depth=functions_called_by_test_depth,
        ),
    }
    scores["tech_combined"] = combined.run(scores)

    return scores


def apply_traceability_techniques(t2p_candidate_df: pd.DataFrame) -> pd.DataFrame:
    scored_df = t2p_candidate_df.copy()
    scores = compute_technique_scores(scored_df)

    for column_name in TECHNIQUE_COLUMNS:
        scored_df[column_name] = [
            scores[column_name].get(row["from_url"], {}).get(row["to_url"], 0)
            for _, row in scored_df.iterrows()
        ]

    return scored_df


# ---------------------------
# Main Processing
# ---------------------------

def run_project_subprocesses(args, projects: list[str]) -> None:
    for project in projects:
        command = [
            sys.executable,
            "-m",
            "ptc.generator.generate_t2p_tech",
            "--projects",
            project,
            "--no-isolate-projects",
        ]
        if getattr(args, "workspace_directory", None):
            command.extend(["--workspace-directory", args.workspace_directory])
        if args.experiment_name:
            command.extend(["--experiment-name", args.experiment_name])
        if args.skip_existing:
            command.append("--skip-existing")
        if args.replace:
            command.append("--replace")
        subprocess.run(command, check=True)


def process_project(
    project: str,
    commit_hash: str,
    llm_directory_names: list[str],
    *,
    t2p_candidate_dir: Path,
    output_dir: Path,
    llm_prediction_dir: Path,
    testlinker_output_dir: Path,
    skip_existing: bool,
    replace: bool,
) -> None:
    t2p_candidate_file = t2p_candidate_dir / f"{project}.csv"
    output_file = output_dir / f"{project}.csv"

    if not os.path.exists(t2p_candidate_file):
        return
    if skip_existing and os.path.exists(output_file) and not replace:
        print("Skipping existing:", project)
        return

    print("Processing:", project, flush=True)

    t2p_candidate_df = pd.read_csv(t2p_candidate_file, na_filter=False, keep_default_na=False)

    # ---------------------------
    # Apply Techniques
    # ---------------------------

    t2p_candidate_df = apply_traceability_techniques(t2p_candidate_df)
    t2p_candidate_df[TECHNIQUE_COLUMNS] = t2p_candidate_df[TECHNIQUE_COLUMNS].round(2)

    t2p_candidate_df["tech_lc"] = (
            t2p_candidate_df.groupby("from_url").cumcount()
            == t2p_candidate_df.groupby("from_url")["from_url"].transform("size") - 1
    ).astype(int)

    t2p_candidate_df = apply_llm_techniques(
        t2p_candidate_df=t2p_candidate_df,
        project=project,
        llm_directory_names=llm_directory_names,
        llm_prediction_root=llm_prediction_dir,
    )
    t2p_candidate_df = apply_testlinker_technique(
        t2p_candidate_df=t2p_candidate_df,
        project=project,
        testlinker_prediction_root=testlinker_output_dir / "testlinker",
    )
    t2p_candidate_df = apply_testlinker_technique(
        t2p_candidate_df=t2p_candidate_df,
        project=project,
        testlinker_prediction_root=testlinker_output_dir / "testlinkerv2",
        strategy_name="tech_testlinkerv2",
    )

    expanded_df = util.convert_float_int_columns_to_nullable_int(t2p_candidate_df)

    expanded_df.to_csv(output_file, index=False)
    del t2p_candidate_df
    del expanded_df
    gc.collect()


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    t2p_candidate_dir = experiment_directory / "t2p-candidate-filtered"
    output_dir = experiment_directory / "t2p-tech"
    llm_prediction_dir = experiment_directory / "llm" / "t2p-link"
    testlinker_output_dir = experiment_directory / "testlinker" / "output" / "codet5"
    os.makedirs(t2p_candidate_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)
    if args.skip_existing and args.replace:
        raise ValueError("--skip-existing and --replace cannot be used together.")

    _, selected_projects, _ = resolve_experiment_filters(
        use_filters=args.use_filters,
        projects=args.projects,
    )
    repository_df = pd.read_csv(experiment_directory / "project.csv")
    projects = select_named_items(repository_df["project"].tolist(), selected_projects, item_label="project")
    repository_df = repository_df[repository_df["project"].isin(projects)]
    llm_directory_names = llm_strategy_directory_names()

    if args.isolate_projects and len(projects) > 1:
        run_project_subprocesses(args, projects)
        return

    for _, repo in repository_df.iterrows():
        project = repo["project"]
        commit_hash = repo["updated_hash"]
        process_project(
            project,
            commit_hash,
            llm_directory_names,
            t2p_candidate_dir=t2p_candidate_dir,
            output_dir=output_dir,
            llm_prediction_dir=llm_prediction_dir,
            testlinker_output_dir=testlinker_output_dir,
            skip_existing=args.skip_existing,
            replace=args.replace,
        )


if __name__ == "__main__":
    main()
