from __future__ import annotations

import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from mhc.artifacts import is_main_code, is_test_case_method
from mhc.command_util import (
    build_experiment_parser,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)
from ptc.generator.run_stats import GenerationStats, should_generate


OUTPUT_FILE_NAME = "method-call-statistics.csv"
STAT_COLUMNS = ["project", "prod_methods", "tests", "unique_calls", "median_calls"]
METHOD_COLUMNS = {"url", "artifact"}
CALLGRAPH_COLUMNS = {"from_url", "to_url"}


def build_parser():
    return build_experiment_parser(
        "Aggregate production-method, test, and direct method-call statistics.",
        include_tools=False,
        include_strategies=False,
        include_replace=True,
        projects_help="Comma-separated project names to process.",
    )


def validate_columns(df: pd.DataFrame, required_columns: set[str], label: str) -> None:
    missing_columns = sorted(required_columns - set(df.columns))
    if missing_columns:
        raise ValueError(f"{label} CSV is missing required column(s): {', '.join(missing_columns)}")


def build_stat_row(project: str, method_df: pd.DataFrame, callgraph_df: pd.DataFrame) -> dict:
    validate_columns(method_df, METHOD_COLUMNS, "Method")
    validate_columns(callgraph_df, CALLGRAPH_COLUMNS, "Callgraph")

    methods = method_df[["url", "artifact"]].drop_duplicates(subset=["url"], keep="first")
    method_urls = set(methods["url"])
    prod_urls = set(methods.loc[methods["artifact"].map(is_main_code), "url"])
    test_urls = set(methods.loc[methods["artifact"].map(is_test_case_method), "url"])

    direct_calls = callgraph_df[
        callgraph_df["from_url"].isin(test_urls)
        & callgraph_df["to_url"].isin(method_urls)
    ][["from_url", "to_url"]].drop_duplicates()

    calls_per_test = (
        direct_calls.groupby("from_url")["to_url"]
        .nunique()
        .reindex(sorted(test_urls), fill_value=0)
    )
    median_calls = float(calls_per_test.median()) if not calls_per_test.empty else np.nan

    return {
        "project": project,
        "prod_methods": len(prod_urls),
        "tests": len(test_urls),
        "unique_calls": len(direct_calls),
        "median_calls": median_calls,
    }


def main(argv: list[str] | None = None) -> Path:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("method_call_statistics")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    output_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    if not should_generate(output_file, replace=args.replace, label=OUTPUT_FILE_NAME, stats=stats):
        stats.print_summary()
        return output_file

    project_file = experiment_directory / "project.csv"
    if not project_file.exists():
        raise FileNotFoundError(f"Experiment project CSV not found: {project_file}")

    _, selected_projects, _ = resolve_experiment_filters(projects=args.projects)
    project_df = pd.read_csv(project_file, keep_default_na=False, na_filter=False)
    if "project" not in project_df.columns:
        raise ValueError(f"Project CSV is missing required column: project")
    projects = select_named_items(
        list(dict.fromkeys(project_df["project"].astype(str))),
        selected_projects,
        item_label="project",
    )

    rows = []
    for project in projects:
        method_file = experiment_directory / "method" / f"{project}.csv"
        callgraph_file = experiment_directory / "callgraph" / f"{project}.csv"
        missing_inputs = [
            label
            for label, path in (("method", method_file), ("callgraph", callgraph_file))
            if not path.exists()
        ]
        if missing_inputs:
            stats.skipped_missing_input += 1
            warnings.warn(f"Skipping {project}: missing {', '.join(missing_inputs)} file.")
            continue

        method_df = pd.read_csv(method_file, keep_default_na=False, na_filter=False, low_memory=False)
        callgraph_df = pd.read_csv(callgraph_file, keep_default_na=False, na_filter=False, low_memory=False)
        rows.append(build_stat_row(project, method_df, callgraph_df))

    result_df = pd.DataFrame(rows, columns=STAT_COLUMNS)
    if not result_df.empty:
        result_df = result_df.sort_values("project").reset_index(drop=True)
    else:
        stats.record_empty_output()

    output_file.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(output_file, index=False)
    stats.record_write(len(result_df))
    stats.print_summary()
    return output_file


if __name__ == "__main__":
    main()
