import os
import argparse
import gc
from math import log
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd
from pytctracer.techniques.last_call_before_assert import LastCallBeforeAssert
from pytctracer.techniques.levenshtein_distance import *
from pytctracer.techniques.longest_common_subsequence import *
from pytctracer.techniques.naming_conventions import *
from pytctracer.techniques.tarantula import Tarantula
from pytctracer.techniques.technique import DISCOUNT_FACTOR
from pytctracer.techniques.tfidf import TFIDF

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)
from ptc.link_strategy import KEY_TO_STRATEGY, LinkStrategy, STRATEGY_KEYS
from ptc.generator.run_stats import GenerationStats, should_generate, unlink_stale_output

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
def llm_strategy_directory_names() -> list[str]:
    return [
        STRATEGY_KEYS[strategy]
        for strategy in STRATEGY_KEYS
        if strategy.name.startswith("LLM_")
    ]


def llm_strategy_column_name(directory_name: str) -> str:
    technique_name = directory_name if directory_name.startswith("llm_") else f"llm_{directory_name}"
    return f"tech_{technique_name}"


def build_parser():
    parser = build_experiment_parser(
        "Generate test-to-production technique scores.",
        include_tools=False,
        include_experiment=True,
        include_replace=True,
        projects_help="Comma-separated project names to process.",
        strategies_help="Comma-separated strategy names to compute. Defaults to ME_STRATEGIES.",
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
        dest="replace",
        action="store_false",
        help="Deprecated alias for --no-replace. Skip projects whose t2p-tech output CSV already exists.",
    )
    parser.add_argument(
        "--summary",
        dest="summary",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=argparse.SUPPRESS,
    )
    return parser


def apply_llm_techniques(
    t2p_candidate_df: pd.DataFrame,
    project: str,
    llm_directory_names: list[str],
    llm_prediction_root: Path,
) -> pd.DataFrame:
    enriched_df = t2p_candidate_df

    for directory_name in llm_directory_names:
        column_name = llm_strategy_column_name(directory_name)
        prediction_file = llm_prediction_root / directory_name / f"{project}.csv"

        if not prediction_file.exists():
            enriched_df[column_name] = pd.Series(pd.NA, index=enriched_df.index, dtype="Int64")
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
        )
        pair_index = pd.MultiIndex.from_frame(llm_match_df[["from_url", "to_url"]])
        prediction_map = pd.Series(
            pd.to_numeric(llm_match_df["label_pred"], errors="coerce").astype("Int64").array,
            index=pair_index,
        )
        candidate_index = pd.MultiIndex.from_frame(enriched_df[["from_url", "to_url"]])
        enriched_df[column_name] = candidate_index.map(prediction_map).astype("Int64")

    return enriched_df


def apply_testlinker_technique(
    t2p_candidate_df: pd.DataFrame,
    project: str,
    testlinker_prediction_root: Path,
    strategy_name: str = "testlinker",
) -> pd.DataFrame:
    enriched_df = t2p_candidate_df
    column_name = strategy_name if strategy_name.startswith("tech_") else f"tech_{strategy_name}"
    prediction_file = testlinker_prediction_root / f"{project}.csv"

    if not prediction_file.exists():
        enriched_df[column_name] = pd.Series(pd.NA, index=enriched_df.index, dtype="Int64")
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
    )
    pair_index = pd.MultiIndex.from_frame(testlinker_match_df[["from_url", "to_url"]])
    prediction_map = pd.Series(
        pd.to_numeric(testlinker_match_df["label_pred"], errors="coerce").astype("Int64").array,
        index=pair_index,
    )
    candidate_index = pd.MultiIndex.from_frame(enriched_df[["from_url", "to_url"]])
    enriched_df[column_name] = candidate_index.map(prediction_map).astype("Int64")
    return enriched_df


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
BASE_TRACEABILITY_COLUMNS = [
    column_name for column_name in TECHNIQUE_COLUMNS if column_name != "tech_combined"
]
NORMALISED_TRACEABILITY_COLUMNS = {
    "tech_lcs_b",
    "tech_lcs_u",
    "tech_leven",
    "tech_tarantula",
    "tech_tfidf",
}

TRACEABILITY_COLUMN_BY_STRATEGY = {
    LinkStrategy.NC: "tech_nc",
    LinkStrategy.NCC: "tech_ncc",
    LinkStrategy.LCS_B: "tech_lcs_b",
    LinkStrategy.LCS_U: "tech_lcs_u",
    LinkStrategy.LEVEN: "tech_leven",
    LinkStrategy.LCBA: "tech_lcba",
    LinkStrategy.TARANTULA: "tech_tarantula",
    LinkStrategy.TFIDF: "tech_tfidf",
    LinkStrategy.COMBINED: "tech_combined",
}
MAX_STRATEGY_COLUMNS = [
    "tech_nc",
    "tech_ncc",
    "tech_lcs_u",
    "tech_lcs_b",
    "tech_leven",
    "tech_lcba",
    "tech_tarantula",
    "tech_tfidf",
    "tech_combined",
]
def selected_strategy_mask(selected_strategies: list[str] | None) -> LinkStrategy:
    if selected_strategies is None:
        return LinkStrategy.ALL

    strategy_keys = list(STRATEGY_KEYS.values())
    selected_mask = LinkStrategy.NONE
    for strategy_name in selected_strategies:
        atomic_keys = [part for part in strategy_name.split("--") if part]
        selected_atomic_keys = select_named_items(
            strategy_keys,
            atomic_keys,
            item_label="strategy",
        )
        for strategy_key in selected_atomic_keys:
            selected_mask |= KEY_TO_STRATEGY[strategy_key]
    return selected_mask


def selected_traceability_columns(strategy_mask: LinkStrategy) -> list[str]:
    selected_columns = []
    if LinkStrategy.MAX in strategy_mask:
        selected_columns.extend(MAX_STRATEGY_COLUMNS)
    for strategy, column_name in TRACEABILITY_COLUMN_BY_STRATEGY.items():
        if strategy in strategy_mask and column_name not in selected_columns:
            selected_columns.append(column_name)
    return selected_columns


def set_null_columns(df: pd.DataFrame, columns: list[str], *, dtype: str = "Float64") -> pd.DataFrame:
    for column_name in columns:
        df[column_name] = pd.Series(pd.NA, index=df.index, dtype=dtype)
    return df


def _method_name(value: object) -> str:
    return str(value or "").lower()


def _call_depth_value(value: object) -> int:
    if value == "":
        return 1

    depth = pd.to_numeric(value, errors="coerce")
    if pd.isna(depth) or depth < 1:
        return 1

    return int(depth)


def _normalise_scores(scores: dict[str, float]) -> dict[str, float]:
    max_score = max(scores.values(), default=0)
    if max_score <= 0:
        return scores

    return {
        function_key: score / max_score
        for function_key, score in scores.items()
    }


def _name_match_score(function_name: str, test_name: str) -> int:
    return nc._compute_nc_score(function_name, test_name) if function_name else 0


def _name_contains_score(function_name: str, test_name: str) -> int:
    return ncc._compute_nc_score(function_name, test_name) if function_name else 0


def _lcs_b_score(function_name: str, test_name: str) -> float:
    stripped_test_name = lcsBoth._strip_test_name(test_name)
    if not function_name and not stripped_test_name:
        return 0

    return lcsBoth._compute_lcs_score(function_name, test_name)


def _lcs_u_score(function_name: str, test_name: str) -> float:
    if not function_name:
        return 0

    return lcsUnit._compute_lcs_score(function_name, test_name)


def _levenshtein_score(function_name: str, test_name: str) -> float:
    stripped_test_name = ld._strip_test_name(test_name)
    if not function_name and not stripped_test_name:
        return 0

    return ld._compute_levenshtein_score(function_name, test_name)


def build_traceability_inputs(t2p_candidate_df: pd.DataFrame):
    function_names = {}
    test_names = {}
    functions_called_by_tests = defaultdict(set)
    tests_that_call_functions = defaultdict(set)
    functions_called_by_test_depth = defaultdict(dict)
    functions_called_by_test_before_assert = defaultdict(set)

    has_lcba = "to_lcba" in t2p_candidate_df.columns
    has_call_depth = "to_call_depth" in t2p_candidate_df.columns

    for row in t2p_candidate_df.itertuples(index=False):
        test_key = row.from_url
        function_key = row.to_url
        test_names[test_key] = _method_name(row.from_name)
        function_names[function_key] = _method_name(row.to_name)
        functions_called_by_tests[test_key].add(function_key)
        tests_that_call_functions[function_key].add(test_key)

        if has_lcba and pd.to_numeric(row.to_lcba, errors="coerce") > 0:
            functions_called_by_test_before_assert[test_key].add(function_key)

        depth = _call_depth_value(row.to_call_depth) if has_call_depth else 1
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
        function_names,
        test_names,
    )


def compute_technique_scores(
    t2p_candidate_df: pd.DataFrame,
    selected_columns: list[str] | None = None,
) -> dict[str, dict[str, dict[str, float]]]:
    output_columns = list(selected_columns) if selected_columns is not None else list(TECHNIQUE_COLUMNS)
    output_column_set = set(output_columns)
    compute_combined = "tech_combined" in output_column_set
    base_columns = set(BASE_TRACEABILITY_COLUMNS) if compute_combined else output_column_set.intersection(
        BASE_TRACEABILITY_COLUMNS
    )

    (
        _function_names_tuple,
        test_names_tuple,
        functions_called_by_tests,
        tests_that_call_functions,
        functions_called_by_test_depth,
        functions_called_by_test_before_assert,
        function_names,
        test_names,
    ) = build_traceability_inputs(t2p_candidate_df)

    number_of_tests = len(test_names_tuple)
    idf_scores = {}
    if "tech_tfidf" in base_columns:
        idf_scores = {
            function_key: tfidf._compute_idf_score(function_key, tests_that_call_functions, number_of_tests)
            for function_key in tests_that_call_functions
        }

    scores = {column_name: defaultdict(dict) for column_name in output_columns}

    for test_key, test_name in test_names.items():
        functions_called_by_test = functions_called_by_tests[test_key]
        depths_by_function = functions_called_by_test_depth[test_key]
        tf_score = 0
        if "tech_tfidf" in base_columns:
            tf_score = (
                log(1 + 1 / len(functions_called_by_test))
                if functions_called_by_test
                else 0
            )
        per_test_scores = {column_name: {} for column_name in base_columns}

        for function_key in functions_called_by_test:
            function_name = function_names[function_key]
            depth = depths_by_function.get(function_key, 1)
            depth_discount = DISCOUNT_FACTOR ** (depth - 1)

            if "tech_nc" in base_columns:
                per_test_scores["tech_nc"][function_key] = _name_match_score(function_name, test_name)
            if "tech_ncc" in base_columns:
                per_test_scores["tech_ncc"][function_key] = _name_contains_score(function_name, test_name)
            if "tech_lcs_b" in base_columns:
                per_test_scores["tech_lcs_b"][function_key] = (
                    _lcs_b_score(function_name, test_name) * depth_discount
                )
            if "tech_lcs_u" in base_columns:
                per_test_scores["tech_lcs_u"][function_key] = (
                    _lcs_u_score(function_name, test_name) * depth_discount
                )
            if "tech_leven" in base_columns:
                per_test_scores["tech_leven"][function_key] = (
                    _levenshtein_score(function_name, test_name) * depth_discount
                )
            if "tech_lcba" in base_columns:
                per_test_scores["tech_lcba"][function_key] = lcba._compute_lcba_score(
                    function_key,
                    test_key,
                    functions_called_by_test_before_assert,
                )
            if "tech_tarantula" in base_columns:
                per_test_scores["tech_tarantula"][function_key] = (
                    tarantula._compute_tarantula_score(
                        function_key,
                        tests_that_call_functions,
                        number_of_tests,
                    ) * depth_discount
                    if number_of_tests > 1
                    else 0
                )
            if "tech_tfidf" in base_columns:
                per_test_scores["tech_tfidf"][function_key] = (
                    tf_score * idf_scores[function_key] * depth_discount
                )

        for column_name in NORMALISED_TRACEABILITY_COLUMNS.intersection(base_columns):
            per_test_scores[column_name] = _normalise_scores(per_test_scores[column_name])

        if compute_combined:
            combined_scores = {}
            for function_key in functions_called_by_test:
                combined_scores[function_key] = sum(
                    per_test_scores[column_name][function_key]
                    for column_name in BASE_TRACEABILITY_COLUMNS
                ) / len(BASE_TRACEABILITY_COLUMNS)
            per_test_scores["tech_combined"] = _normalise_scores(combined_scores)

        for column_name, function_scores in per_test_scores.items():
            if column_name in output_column_set:
                scores[column_name][test_key].update(function_scores)

    return scores


def apply_traceability_techniques(
    t2p_candidate_df: pd.DataFrame,
    selected_columns: list[str] | None = None,
) -> pd.DataFrame:
    scored_df = t2p_candidate_df
    output_columns = list(selected_columns) if selected_columns is not None else list(TECHNIQUE_COLUMNS)
    scores = compute_technique_scores(scored_df, output_columns)

    for column_name in output_columns:
        score_by_test = scores[column_name]
        scored_df[column_name] = [
            score_by_test.get(test_key, {}).get(function_key, 0)
            for test_key, function_key in zip(scored_df["from_url"], scored_df["to_url"])
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
            "ptc.generator.t2p_technique",
            "--projects",
            project,
            "--no-isolate-projects",
        ]
        if getattr(args, "workspace_directory", None):
            command.extend(["--workspace-directory", args.workspace_directory])
        if args.experiment_name:
            command.extend(["--experiment-name", args.experiment_name])
        if getattr(args, "strategies", None):
            command.extend(["--strategies", args.strategies])
        if args.replace:
            command.append("--replace")
        else:
            command.append("--no-replace")
        command.append("--no-summary")
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
    replace: bool,
    strategy_mask: LinkStrategy = LinkStrategy.ALL,
    stats: GenerationStats | None = None,
) -> None:
    stats = stats or GenerationStats("t2p_technique")
    t2p_candidate_file = t2p_candidate_dir / f"{project}.csv"
    output_file = output_dir / f"{project}.csv"

    if not os.path.exists(t2p_candidate_file):
        unlink_stale_output(
            output_file,
            reason=f"Skipping: {project} (missing t2p-candidate-filtered file)",
            stats=stats,
        )
        return
    if not should_generate(output_file, replace=replace, label=project, stats=stats):
        return

    print("Processing:", project, flush=True)

    t2p_candidate_df = pd.read_csv(t2p_candidate_file, na_filter=False, keep_default_na=False)

    # ---------------------------
    # Apply Techniques
    # ---------------------------

    traceability_columns = selected_traceability_columns(strategy_mask)
    if traceability_columns:
        t2p_candidate_df = apply_traceability_techniques(t2p_candidate_df, traceability_columns)
        t2p_candidate_df[traceability_columns] = t2p_candidate_df[traceability_columns].round(2)
        unselected_traceability_columns = [
            column_name for column_name in TECHNIQUE_COLUMNS if column_name not in traceability_columns
        ]
        t2p_candidate_df = set_null_columns(t2p_candidate_df, unselected_traceability_columns)
    else:
        t2p_candidate_df = set_null_columns(t2p_candidate_df, TECHNIQUE_COLUMNS)

    if LinkStrategy.LC in strategy_mask:
        t2p_candidate_df["tech_lc"] = (
            t2p_candidate_df.groupby("from_url").cumcount()
            == t2p_candidate_df.groupby("from_url")["from_url"].transform("size") - 1
        ).astype(int)
    else:
        t2p_candidate_df = set_null_columns(t2p_candidate_df, ["tech_lc"])

    selected_llm_directory_names = [
        directory_name
        for directory_name in llm_directory_names
        if KEY_TO_STRATEGY[directory_name] in strategy_mask
    ]
    if selected_llm_directory_names:
        t2p_candidate_df = apply_llm_techniques(
            t2p_candidate_df=t2p_candidate_df,
            project=project,
            llm_directory_names=selected_llm_directory_names,
            llm_prediction_root=llm_prediction_dir,
        )
    unselected_llm_columns = [
        llm_strategy_column_name(directory_name)
        for directory_name in llm_directory_names
        if directory_name not in selected_llm_directory_names
    ]
    t2p_candidate_df = set_null_columns(t2p_candidate_df, unselected_llm_columns, dtype="Int64")

    if LinkStrategy.TESTLINKER in strategy_mask:
        t2p_candidate_df = apply_testlinker_technique(
            t2p_candidate_df=t2p_candidate_df,
            project=project,
            testlinker_prediction_root=testlinker_output_dir / "testlinker",
        )
    else:
        t2p_candidate_df = set_null_columns(t2p_candidate_df, ["tech_testlinker"], dtype="Int64")
    if LinkStrategy.TESTLINKERV2 in strategy_mask:
        t2p_candidate_df = apply_testlinker_technique(
            t2p_candidate_df=t2p_candidate_df,
            project=project,
            testlinker_prediction_root=testlinker_output_dir / "testlinkerv2",
            strategy_name="tech_testlinkerv2",
        )
    else:
        t2p_candidate_df = set_null_columns(t2p_candidate_df, ["tech_testlinkerv2"], dtype="Int64")

    expanded_df = util.convert_float_int_columns_to_nullable_int(t2p_candidate_df)

    expanded_df.to_csv(output_file, index=False)
    stats.record_write(len(expanded_df))
    del t2p_candidate_df
    del expanded_df
    gc.collect()


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("t2p_technique")
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

    _, selected_projects, selected_strategies = resolve_experiment_filters(
        projects=args.projects,
        strategies=args.strategies,
    )
    strategy_mask = selected_strategy_mask(selected_strategies)
    repository_df = pd.read_csv(experiment_directory / "project.csv")
    projects = select_named_items(repository_df["project"].tolist(), selected_projects, item_label="project")
    repository_df = repository_df[repository_df["project"].isin(projects)]
    llm_directory_names = llm_strategy_directory_names()

    if args.isolate_projects and len(projects) > 1:
        for project in projects:
            t2p_candidate_file = t2p_candidate_dir / f"{project}.csv"
            output_file = output_dir / f"{project}.csv"
            if not t2p_candidate_file.exists():
                stats.skipped_missing_input += 1
                if output_file.exists():
                    stats.deleted_stale += 1
                else:
                    stats.missing_stale += 1
            elif output_file.exists() and not args.replace:
                stats.skipped_existing += 1
            else:
                stats.recreated += 1
        run_project_subprocesses(args, projects)
        stats.print_summary()
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
            replace=args.replace,
            strategy_mask=strategy_mask,
            stats=stats,
        )
    if args.summary:
        stats.print_summary()


if __name__ == "__main__":
    main()
