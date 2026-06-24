from __future__ import annotations

import os
import warnings
from pathlib import Path

import pandas as pd

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_smell_detector,
    select_named_items,
)
from ptc.generator.run_stats import GenerationStats, should_generate, unlink_stale_output
from ptc.generator.t2p_test_smell_revision import read_smell_file, smell_file_path, smell_summary

OUTPUT_DIRECTORY_NAME = "t2p-test-smell"
OUTPUT_COLUMNS = ["project", "from_url", "to_url", "smells"]


def build_parser():
    return build_experiment_parser(
        "Generate linked test-production rows with introduction-time test smells.",
        include_tools=True,
        include_smell_detector=True,
        include_replace=True,
        projects_help="Comma-separated project names to process. Defaults to ME_PROJECTS.",
        strategies_help="Comma-separated strategy names to process. Defaults to ME_STRATEGIES.",
    )


def build_project_frame(project_df: pd.DataFrame, smell_df: pd.DataFrame, *, project: str) -> pd.DataFrame:
    missing_base_columns = [column for column in ["from_url", "to_url"] if column not in project_df.columns]
    if missing_base_columns:
        raise ValueError(f"Missing required column(s): {', '.join(missing_base_columns)}")

    output_df = project_df[["from_url", "to_url"]].copy()
    output_df["project"] = project
    output_df = output_df.merge(smell_summary(smell_df), on="from_url", how="left")
    output_df["smells"] = output_df["smells"].fillna("")
    return output_df[OUTPUT_COLUMNS].copy()


def output_directory(experiment_directory: Path, strategy: str, tool: str, smell_detector: str) -> Path:
    if tool:
        return experiment_directory / OUTPUT_DIRECTORY_NAME / strategy / tool / smell_detector
    return experiment_directory / OUTPUT_DIRECTORY_NAME / strategy / smell_detector


def process_strategy(
    project_files: list[Path],
    *,
    experiment_directory: Path,
    output_dir: Path,
    tool: str,
    strategy: str,
    smell_detector: str,
    replace: bool,
    stats: GenerationStats,
) -> None:
    for project_file in project_files:
        project = project_file.stem
        output_file = output_dir / f"{project}.csv"
        smell_file = smell_file_path(experiment_directory, smell_detector, strategy, project)
        if not smell_file.exists():
            unlink_stale_output(
                output_file,
                reason=(
                    f"Skipping project={project}, tool={tool}, strategy={strategy}, "
                    f"smell_detector={smell_detector}: Test smell CSV not found: {smell_file}"
                ),
                stats=stats,
            )
            continue

        if not should_generate(
            output_file,
            replace=replace,
            label=f"{project} [{tool}/{strategy}/{smell_detector}]",
            stats=stats,
        ):
            continue

        project_df = pd.read_csv(project_file, keep_default_na=False, na_filter=False)
        smell_df = read_smell_file(experiment_directory, smell_detector, strategy, project)
        try:
            output_df = build_project_frame(project_df, smell_df, project=project)
        except ValueError as exc:
            unlink_stale_output(
                output_file,
                reason=f"Skipping project={project}, tool={tool}, strategy={strategy}: {exc}",
                stats=stats,
            )
            continue

        if output_df.empty:
            unlink_stale_output(
                output_file,
                reason=f"Skipping project={project}, tool={tool}, strategy={strategy}: generated frame is empty",
                stats=stats,
            )
            stats.record_empty_output()
            continue

        os.makedirs(output_file.parent, exist_ok=True)
        output_df.to_csv(output_file, index=False)
        stats.record_write(len(output_df))
        print(
            f"project={project}, tool={tool}, strategy={strategy}, smell_detector={smell_detector}: "
            f"rows={len(output_df)}, smelly_rows={(output_df['smells'].str.strip() != '').sum()}"
        )


def strategy_input_groups(
    strategy_dir: Path,
    selected_tools: list[str] | None,
) -> list[tuple[str, Path]]:
    direct_files = sorted(strategy_dir.glob("*.csv"))
    if direct_files:
        return [("", strategy_dir)]

    tools = select_named_items(
        util.sorted_directory_names(strategy_dir),
        selected_tools,
        item_label="tool",
    )
    return [(tool, strategy_dir / tool) for tool in tools]


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("t2p_test_smell")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    t2p_link_dir = experiment_directory / "t2p-link"
    if not t2p_link_dir.exists():
        warnings.warn(f"Directory not found, skipping: {t2p_link_dir}")
        stats.print_summary()
        return

    strategies = select_named_items(
        util.sorted_directory_names(t2p_link_dir),
        selected_strategies,
        item_label="strategy",
    )
    for strategy in strategies:
        strategy_dir = t2p_link_dir / strategy
        for tool, input_dir in strategy_input_groups(strategy_dir, selected_tools):
            project_files = list_csv_files(input_dir, selected_projects, strict=False)
            if not project_files:
                warnings.warn(f"No csv files found, skipping: {input_dir}")
                continue
            process_strategy(
                project_files,
                experiment_directory=experiment_directory,
                output_dir=output_directory(experiment_directory, strategy, tool, smell_detector),
                tool=tool,
                strategy=strategy,
                smell_detector=smell_detector,
                replace=args.replace,
                stats=stats,
            )
    stats.print_summary()


if __name__ == "__main__":
    main()
