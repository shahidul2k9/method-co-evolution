import os
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
from mhc.config import *
from ptc.experiment_util import build_experiment_parser, resolve_experiment_filters, select_named_items
from ptc.link_strategy import LinkStrategy, STRATEGY_KEYS

# ---------------------------
# Config
# ---------------------------

MAX_EXPANSION_DEPTH = 5

FANOUT_DIR = f"{DATA_DIRECTORY}/fan-out"
METHOD_DIR = f"{DATA_DIRECTORY}/method"
T2P_CANDIDATE_DIR = f"{DATA_DIRECTORY}/t2p-candidate"
OUTPUT_DIR = f"{DATA_DIRECTORY}/m2m-tech"
LLM_PREDICTION_DIR = Path(CACHE_DIRECTORY) / "data" / "llm" / "t2p-link"
TESTLINKER_PREDICTION_DIR = Path(CACHE_DIRECTORY) / "data" / "testlinker" / "t2p-link" / "codet5"

os.makedirs(T2P_CANDIDATE_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
    return build_experiment_parser(
        "Generate method-to-method technique scores.",
        include_tools=False,
        include_strategies=False,
        projects_help="Comma-separated project names to process.",
    )


def apply_llm_techniques(
    t2p_candidate_df: pd.DataFrame,
    project: str,
    llm_directory_names: list[str],
    llm_prediction_root: Path = LLM_PREDICTION_DIR,
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
    testlinker_prediction_root: Path = TESTLINKER_PREDICTION_DIR,
) -> pd.DataFrame:
    enriched_df = t2p_candidate_df.copy()
    column_name = "tech_testlinker"
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
        "tech_tarantula": tarantula.run(
            function_names_tuple=function_names_tuple,
            test_names_tuple=test_names_tuple,
            functions_called_by_tests=functions_called_by_tests,
            tests_that_call_functions=tests_that_call_functions,
            functions_called_by_test_depth=functions_called_by_test_depth,
        ),
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

def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    _, selected_projects, _ = resolve_experiment_filters(
        use_filters=args.use_filters,
        projects=args.projects,
    )
    repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")
    projects = select_named_items(repository_df["project"].tolist(), selected_projects, item_label="project")
    repository_df = repository_df[repository_df["project"].isin(projects)]
    llm_directory_names = llm_strategy_directory_names()

    for _, repo in repository_df.iterrows():
        project = repo["project"]
        commit_hash = repo["updated_hash"]

        t2p_candidate_file = f"{T2P_CANDIDATE_DIR}/{project}.csv"
        method_file = f"{METHOD_DIR}/{project}.csv"

        if os.path.exists(t2p_candidate_file):
            print("Processing:", project)

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
            )
            t2p_candidate_df = apply_testlinker_technique(
                t2p_candidate_df=t2p_candidate_df,
                project=project,
            )

            expanded_df = util.convert_float_int_columns_to_nullable_int(t2p_candidate_df)

            output_file = f"{OUTPUT_DIR}/{project}.csv"
            expanded_df.to_csv(output_file, index=False)

    print("Finished.")


if __name__ == "__main__":
    main()
