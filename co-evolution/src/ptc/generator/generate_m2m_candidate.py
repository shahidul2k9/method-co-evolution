from collections import defaultdict, deque

import pandas as pd
from pytctracer.techniques.levenshtein_distance import *
from pytctracer.techniques.longest_common_subsequence import *
from pytctracer.techniques.naming_conventions import *

import mhc.util as util
from mhc.config import *
from ptc.experiment_util import build_experiment_parser, resolve_experiment_filters, select_named_items

# ---------------------------
# Config
# ---------------------------

MAX_EXPANSION_DEPTH = 5

FANOUT_DIR = f"{DATA_DIRECTORY}/fan-out"
METHOD_DIR = f"{DATA_DIRECTORY}/method"
EXPANDED_FANOUT_DIR = f"{DATA_DIRECTORY}/t2p-candidate"
OUTPUT_DIR = f"{DATA_DIRECTORY}/m2m-tech"

os.makedirs(EXPANDED_FANOUT_DIR, exist_ok=True)
os.makedirs(OUTPUT_DIR, exist_ok=True)


def build_parser():
    return build_experiment_parser(
        "Generate method-to-method candidate links.",
        include_tools=False,
        include_strategies=False,
        projects_help="Comma-separated project names to process.",
    )



def expand_test_calls(row, from_url_graph, method_artifact_mapping, max_depth):
    results = []

    stack = deque()
    visited = set()

    stack.append((row, 1, row["to_url"]))

    while stack:
        current_row, depth, current_to_url = stack.pop()

        if depth <= max_depth and current_to_url not in visited:
            visited.add(current_to_url)

            artifact = method_artifact_mapping.get(current_to_url, "")

            # Stop if production reached
            if artifact == "production":
                new_row = row.copy()

                for col in current_row.index:
                    if col.startswith("to_"):
                        new_row[col] = current_row[col]

                new_row["to_caller_url"] = current_row["from_url"]
                new_row["to_call_depth"] = depth

                results.append(new_row)
            else:
                # otherwise expand
                for next_row in from_url_graph.get(current_to_url, []):
                    stack.append((next_row, depth + 1, next_row["to_url"]))

    return results


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

    # ---------------------------
    # Main Processing
    # ---------------------------

    for _, repo in repository_df.iterrows():

        project = repo["project"]
        commit_hash = repo["updated_hash"]

        fanout_file = f"{FANOUT_DIR}/{project}.csv"
        method_file = f"{METHOD_DIR}/{project}.csv"

        if os.path.exists(fanout_file) and os.path.exists(method_file):
            print("Processing:", project)

            fan_out_df = pd.read_csv(fanout_file, na_filter=False, keep_default_na=False)
            method_df = pd.read_csv(method_file, na_filter=False, keep_default_na=False)

            fan_out_df = fan_out_df[fan_out_df["to_url"].str.strip() != ""]

            # Build artifact lookup
            method_artifact = dict(zip(method_df["url"], method_df["artifact"]))

            # Build call graph
            from_url_graph = defaultdict(list)

            for _, row in fan_out_df.iterrows():
                from_url_graph[row["from_url"]].append(row)

            expanded_rows = []

            for _, row in fan_out_df.iterrows():

                from_artifact = method_artifact.get(row["from_url"], "")
                to_artifact = method_artifact.get(row["to_url"], "")

                # only expand test → test/test util
                if from_artifact == "test" and (to_artifact == "test" or to_artifact == "test_util"):
                    expansions = expand_test_calls(
                        row,
                        from_url_graph,
                        method_artifact,
                        MAX_EXPANSION_DEPTH
                    )
                    expanded_rows.extend(expansions)
                else:
                    expanded_rows.append(row)

            expanded_df = pd.DataFrame(expanded_rows)
            expanded_file = f"{EXPANDED_FANOUT_DIR}/{project}.csv"
            expanded_df.to_csv(expanded_file, index=False)

    print("Finished.")


if __name__ == "__main__":
    main()
