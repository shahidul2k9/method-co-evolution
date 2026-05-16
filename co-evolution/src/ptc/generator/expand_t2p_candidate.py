import os
from collections import defaultdict, deque

import pandas as pd

from mhc.artifacts import is_test_case_method, is_test_code, is_main_code
from ptc.experiment_util import build_experiment_parser, resolve_experiment_filters, resolve_experiment_paths, select_named_items


MAX_EXPANSION_DEPTH = 5


def build_parser():
    return build_experiment_parser(
        "Expand test-to-production candidate links through test helper calls.",
        include_tools=False,
        include_strategies=False,
        projects_help="Comma-separated project names to process.",
    )


def build_callgraph_index(fan_out_df: pd.DataFrame) -> dict[str, list[pd.Series]]:
    from_url_graph = defaultdict(list)
    for _, row in fan_out_df.iterrows():
        from_url_graph[row["from_url"]].append(row)
    return from_url_graph


def build_method_artifact_index(method_df: pd.DataFrame) -> dict[str, str]:
    return dict(zip(method_df["url"], method_df["artifact"]))


def is_test_artifact(artifact: str) -> bool:
    return is_test_code(artifact)


def set_direct_call_depth(row: pd.Series) -> pd.Series:
    new_row = row.copy()
    new_row["to_call_depth"] = 1
    return new_row


def expand_transitive_test_calls(
    row: pd.Series,
    from_url_graph: dict[str, list[pd.Series]],
    method_artifact_mapping: dict[str, str],
    max_depth: int,
) -> list[pd.Series]:
    results = []
    stack = deque()
    visited = set()

    stack.append((row, 1, row["to_url"]))

    while stack:
        current_row, depth, current_to_url = stack.pop()

        if depth > max_depth or current_to_url in visited:
            continue

        visited.add(current_to_url)
        artifact = method_artifact_mapping.get(current_to_url, "")

        if is_main_code(artifact):
            new_row = row.copy()

            for col in current_row.index:
                if col.startswith("to_"):
                    new_row[col] = current_row[col]

            new_row["to_caller_url"] = current_row["from_url"]
            new_row["to_call_depth"] = depth
            results.append(new_row)
            continue

        for next_row in from_url_graph.get(current_to_url, []):
            stack.append((next_row, depth + 1, next_row["to_url"]))

    return results


def expand_candidate_df(
    fan_out_df: pd.DataFrame,
    method_df: pd.DataFrame,
    *,
    max_depth: int = MAX_EXPANSION_DEPTH,
) -> pd.DataFrame:
    fan_out_df = fan_out_df[fan_out_df["to_url"].str.strip() != ""]
    method_artifact = build_method_artifact_index(method_df)
    from_url_graph = build_callgraph_index(fan_out_df)

    expanded_rows = []
    for _, row in fan_out_df.iterrows():
        from_artifact = method_artifact.get(row["from_url"], "")
        to_artifact = method_artifact.get(row["to_url"], "")
        expanded_rows.append(set_direct_call_depth(row))
        if is_test_artifact(from_artifact) and is_test_artifact(to_artifact):
            expanded_rows.extend(
                expand_transitive_test_calls(
                    row,
                    from_url_graph,
                    method_artifact,
                    max_depth,
                )
            )

    return pd.DataFrame(expanded_rows)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    fanout_dir = experiment_directory / "callgraph"
    method_dir = experiment_directory / "method"
    expanded_t2p_candidate_dir = experiment_directory / "t2p-candidate-expanded"
    os.makedirs(expanded_t2p_candidate_dir, exist_ok=True)
    _, selected_projects, _ = resolve_experiment_filters(
        use_filters=args.use_filters,
        projects=args.projects,
    )
    repository_df = pd.read_csv(experiment_directory / "project.csv")
    projects = select_named_items(repository_df["project"].tolist(), selected_projects, item_label="project")
    repository_df = repository_df[repository_df["project"].isin(projects)]

    for _, repo in repository_df.iterrows():
        project = repo["project"]
        fanout_file = fanout_dir / f"{project}.csv"
        method_file = method_dir / f"{project}.csv"

        if os.path.exists(fanout_file) and os.path.exists(method_file):
            print("Processing:", project)
            fan_out_df = pd.read_csv(fanout_file, na_filter=False, keep_default_na=False)
            method_df = pd.read_csv(method_file, na_filter=False, keep_default_na=False)
            expanded_df = expand_candidate_df(fan_out_df, method_df)
            expanded_file = expanded_t2p_candidate_dir / f"{project}.csv"
            expanded_df.to_csv(expanded_file, index=False)

    print("Finished.")


if __name__ == "__main__":
    main()
