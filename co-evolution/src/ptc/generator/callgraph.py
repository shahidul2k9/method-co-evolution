import os.path

import pandas as pd

import mhc.util as util
from ptc.experiment_util import build_experiment_parser, resolve_experiment_filters, resolve_experiment_paths, select_named_items


def build_parser():
    return build_experiment_parser(
        "Generate fanin/callgraph counts.",
        include_tools=False,
        include_strategies=False,
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
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    _, selected_projects, _ = resolve_experiment_filters(
        use_filters=args.use_filters,
        projects=args.projects,
    )

    repository_df = pd.read_csv(experiment_directory / "project.csv")
    projects = select_named_items(repository_df["project"].tolist(), selected_projects, item_label="project")
    repository_df = repository_df[repository_df["project"].isin(projects)]

    for _, repo in repository_df.iterrows():
        repository_name = repo["project"]
        fan_dfs = []
        for url_column, fan, fan_column in [
            ("from_url", "callgraph", "fan_out"),
            ("to_url", "fanin", "fan_in"),
        ]:
            fan_file = str(experiment_directory / fan / f"{repository_name}.csv")
            fan_dfs.append(read_fan_count_if_exists(fan_file, url_column, fan_column))
        fan_out_df, fan_in_df = fan_dfs
        if fan_out_df is not None and fan_in_df is not None:
            print(f"Processing: {repository_name}")
            in_out_df = pd.merge(fan_out_df, fan_in_df, on="url", how="outer")
            in_out_df[["fan_out", "fan_in"]] = in_out_df[["fan_out", "fan_in"]].fillna(0).astype(int)
            method_df = pd.read_csv(
                util.format_method_list_file(str(experiment_directory), repository_name),
                keep_default_na=False,
                na_filter=False,
                low_memory=False,
            )
            fan_in_count_file = str(experiment_directory / "callgraph-degree" / f"{repository_name}.csv")
            os.makedirs(os.path.dirname(fan_in_count_file), exist_ok=True)
            pd.merge(method_df, in_out_df, on="url", how="inner").to_csv(
                fan_in_count_file, index=False)
        else:
            missing = []
            if fan_out_df is None:
                missing.append("callgraph")
            if fan_in_df is None:
                missing.append("fanin")
            print(f"Skipping: {repository_name} (missing {', '.join(missing)} file)")


if __name__ == "__main__":
    main()
