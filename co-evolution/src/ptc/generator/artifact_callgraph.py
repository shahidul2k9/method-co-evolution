import os.path

import pandas as pd

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    filter_artifact_dataframe,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)
from ptc.generator.run_stats import GenerationStats, should_generate, unlink_stale_output


def build_parser():
    return build_experiment_parser(
        "Generate fanin/callgraph counts.",
        include_tools=False,
        include_strategies=False,
        include_replace=True,
        projects_help="Comma-separated project names to process.",
    )


def read_fan_count_if_exists(fan_file: str, url_column: str, fan_column: str):
    if os.path.exists(fan_file):
        raw_fan_df = pd.read_csv(fan_file, na_filter=False, keep_default_na=False, low_memory=False)
        fan_count_df = (
            raw_fan_df[url_column]
            .value_counts()
            .reset_index(name=fan_column)
            .rename(columns={url_column: "url", "index": "url"})
        )
        return fan_count_df
    return None


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("artifact_callgraph")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    _, selected_projects, _ = resolve_experiment_filters(
        projects=args.projects,
    )

    repository_df = pd.read_csv(experiment_directory / "project.csv")
    projects = select_named_items(repository_df["project"].tolist(), selected_projects, item_label="project")
    repository_df = repository_df[repository_df["project"].isin(projects)]

    for _, repo in repository_df.iterrows():
        repository_name = repo["project"]
        fanout_file = experiment_directory / "callgraph" / f"{repository_name}.csv"
        fanin_file = experiment_directory / "fanin" / f"{repository_name}.csv"
        method_file = util.format_method_list_file(str(experiment_directory), repository_name)
        fan_in_count_file = experiment_directory / "callgraph-degree" / f"{repository_name}.csv"
        missing = []
        if not fanout_file.exists():
            missing.append("callgraph")
        if not fanin_file.exists():
            missing.append("fanin")
        if not os.path.exists(method_file):
            missing.append("method")
        if missing:
            unlink_stale_output(
                fan_in_count_file,
                reason=f"Skipping: {repository_name} (missing {', '.join(missing)} file)",
                stats=stats,
            )
            continue
        if not should_generate(fan_in_count_file, replace=args.replace, label=repository_name, stats=stats):
            continue

        print(f"Processing: {repository_name}")
        fan_out_df = read_fan_count_if_exists(str(fanout_file), "from_url", "fan_out")
        fan_in_df = read_fan_count_if_exists(str(fanin_file), "to_url", "fan_in")
        in_out_df = pd.merge(fan_out_df, fan_in_df, on="url", how="outer")
        in_out_df[["fan_out", "fan_in"]] = in_out_df[["fan_out", "fan_in"]].fillna(0).astype(int)
        method_df = pd.read_csv(
            method_file,
            keep_default_na=False,
            na_filter=False,
            low_memory=False,
        )
        output_df = pd.merge(method_df, in_out_df, on="url", how="inner").pipe(filter_artifact_dataframe)
        os.makedirs(fan_in_count_file.parent, exist_ok=True)
        output_df.to_csv(fan_in_count_file, index=False)
        stats.record_write(len(output_df))

    stats.print_summary()


if __name__ == "__main__":
    main()
