from pathlib import Path

import pandas as pd

from mhc.command_util import build_experiment_parser, list_csv_files, resolve_experiment_filters, resolve_experiment_paths
from ptc.generator.run_stats import GenerationStats, should_generate, unlink_stale_output


UNNEEDED_CANDIDATE_COLUMNS = ["from_fqs_alt", "to_fqs_alt"]


def build_parser():
    parser = build_experiment_parser(
        "Filter expanded test-to-production candidates.",
        include_tools=False,
        include_strategies=False,
        include_replace=True,
        projects_help="Comma-separated project names to process.",
    )
    parser.add_argument(
        "--t2p-ground-truth-dir",
        type=Path,
        help="Directory of test-to-production ground-truth CSV files used to filter candidates.",
    )
    return parser


def filter_candidate_df(candidate_df: pd.DataFrame) -> pd.DataFrame:
    return candidate_df.drop(columns=UNNEEDED_CANDIDATE_COLUMNS, errors="ignore").copy()


def filter_candidate_df_by_ground_truth(candidate_df: pd.DataFrame, ground_truth_df: pd.DataFrame) -> pd.DataFrame:
    ground_truth_from_urls = set(ground_truth_df["from_url"])
    return candidate_df[candidate_df["from_url"].isin(ground_truth_from_urls)].copy()


def is_empty_file(csv_file: Path) -> bool:
    return csv_file.exists() and csv_file.stat().st_size == 0


def read_csv_or_unlink_stale(
    csv_file: Path,
    output_file: Path,
    *,
    input_label: str,
    required_columns: set[str],
    stats: GenerationStats,
    low_memory: bool = True,
) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(
            csv_file,
            keep_default_na=False,
            na_filter=False,
            low_memory=low_memory,
        )
    except pd.errors.EmptyDataError:
        stats.record_empty_output()
        unlink_stale_output(
            output_file,
            reason=f"Skipping {csv_file.stem}; empty {input_label} CSV: {csv_file}",
            stats=stats,
        )
        return None

    missing_columns = required_columns.difference(df.columns)
    if missing_columns:
        unlink_stale_output(
            output_file,
            reason=(
                f"Skipping {csv_file.stem}; {input_label} CSV missing required column(s): "
                f"{', '.join(sorted(missing_columns))}"
            ),
            stats=stats,
        )
        return None
    return df


def print_ground_truth_filter_summary(rows: list[dict[str, object]], filtered_t2p_candidate_dir: Path) -> None:
    if not rows:
        return

    all_filtered = pd.concat([
        pd.read_csv(filtered_t2p_candidate_dir / f"{r['project']}.csv", keep_default_na=False, na_filter=False)
        for r in rows
    ], ignore_index=True)
    total = {
        "project": "total",
        "rows_before": sum(int(r["rows_before"]) for r in rows),
        "rows_after": sum(int(r["rows_after"]) for r in rows),
        "test_urls": all_filtered["from_url"].nunique(),
        "prod_urls": all_filtered["to_url"].nunique(),
        "links": all_filtered[["from_url", "to_url"]].drop_duplicates().shape[0],
    }
    cols = ["project", "rows_before", "rows_after", "test_urls", "prod_urls", "links"]
    all_rows = [*rows, total]
    widths = {c: max(len(c), max(len(str(r[c])) for r in all_rows)) for c in cols}
    sep = "+-" + "-+-".join("-" * widths[c] for c in cols) + "-+"
    hdr = "| " + " | ".join(c.ljust(widths[c]) for c in cols) + " |"
    print(sep)
    print(hdr)
    print(sep)
    for row in rows:
        print("| " + " | ".join(str(row[c]).rjust(widths[c]) for c in cols) + " |")
    print(sep)
    print("| " + " | ".join(str(total[c]).rjust(widths[c]) for c in cols) + " |")
    print(sep)


def filter_expanded_candidate_files(
    expanded_t2p_candidate_dir: Path,
    filtered_t2p_candidate_dir: Path,
    selected_projects: list[str] | None,
    *,
    replace: bool,
    stats: GenerationStats,
) -> None:
    for candidate_file in list_csv_files(expanded_t2p_candidate_dir, selected_projects, strict=False):
        output_file = filtered_t2p_candidate_dir / candidate_file.name
        if is_empty_file(candidate_file):
            stats.record_empty_output()
            unlink_stale_output(
                output_file,
                reason=f"Skipping {candidate_file.stem}; empty candidate CSV: {candidate_file}",
                stats=stats,
            )
            continue
        if not should_generate(output_file, replace=replace, label=candidate_file.stem, stats=stats):
            continue

        print("Processing:", candidate_file.stem)
        candidate_df = read_csv_or_unlink_stale(
            candidate_file,
            output_file,
            input_label="candidate",
            required_columns={"from_url", "to_url"},
            stats=stats,
            low_memory=True,
        )
        if candidate_df is None:
            continue
        filtered_df = filter_candidate_df(candidate_df)
        filtered_df.to_csv(output_file, index=False)
        stats.record_write(len(filtered_df))


def filter_expanded_candidate_files_by_ground_truth(
    expanded_t2p_candidate_dir: Path,
    filtered_t2p_candidate_dir: Path,
    t2p_ground_truth_dir: Path,
    selected_projects: list[str] | None,
    *,
    replace: bool,
    stats: GenerationStats,
) -> None:
    rows = []
    print("Processing:", t2p_ground_truth_dir.name)
    for candidate_file in list_csv_files(expanded_t2p_candidate_dir, selected_projects, strict=False):
        ground_truth_file = t2p_ground_truth_dir / candidate_file.name
        output_file = filtered_t2p_candidate_dir / candidate_file.name
        if not ground_truth_file.exists():
            unlink_stale_output(
                output_file,
                reason=f"Skipping {candidate_file.stem}; no ground truth found",
                stats=stats,
            )
            continue
        if is_empty_file(candidate_file):
            stats.record_empty_output()
            unlink_stale_output(
                output_file,
                reason=f"Skipping {candidate_file.stem}; empty candidate CSV: {candidate_file}",
                stats=stats,
            )
            continue
        if is_empty_file(ground_truth_file):
            stats.record_empty_output()
            unlink_stale_output(
                output_file,
                reason=f"Skipping {candidate_file.stem}; empty ground-truth CSV: {ground_truth_file}",
                stats=stats,
            )
            continue
        if not should_generate(output_file, replace=replace, label=candidate_file.stem, stats=stats):
            continue

        print("Processing:", candidate_file.stem)
        candidate_df = read_csv_or_unlink_stale(
            candidate_file,
            output_file,
            input_label="candidate",
            required_columns={"from_url", "to_url"},
            stats=stats,
            low_memory=False,
        )
        if candidate_df is None:
            continue
        candidate_df = filter_candidate_df(candidate_df)
        ground_truth_df = read_csv_or_unlink_stale(
            ground_truth_file,
            output_file,
            input_label="ground-truth",
            required_columns={"from_url"},
            stats=stats,
            low_memory=True,
        )
        if ground_truth_df is None:
            continue
        filtered_df = filter_candidate_df_by_ground_truth(candidate_df, ground_truth_df)
        filtered_df.to_csv(output_file, index=False)
        stats.record_write(len(filtered_df))
        rows.append({
            "project": candidate_file.stem,
            "rows_before": len(candidate_df),
            "rows_after": len(filtered_df),
            "test_urls": filtered_df["from_url"].nunique(),
            "prod_urls": filtered_df["to_url"].nunique(),
            "links": filtered_df[["from_url", "to_url"]].drop_duplicates().shape[0],
        })

    print_ground_truth_filter_summary(rows, filtered_t2p_candidate_dir)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("filter_t2p_candidate")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    expanded_t2p_candidate_dir = experiment_directory / "t2p-candidate-expanded"
    filtered_t2p_candidate_dir = experiment_directory / "t2p-candidate-filtered"
    filtered_t2p_candidate_dir.mkdir(parents=True, exist_ok=True)
    _, selected_projects, _ = resolve_experiment_filters(
        projects=args.projects,
    )
    if args.t2p_ground_truth_dir:
        filter_expanded_candidate_files_by_ground_truth(
            expanded_t2p_candidate_dir,
            filtered_t2p_candidate_dir,
            args.t2p_ground_truth_dir,
            selected_projects,
            replace=args.replace,
            stats=stats,
        )
    else:
        filter_expanded_candidate_files(
            expanded_t2p_candidate_dir,
            filtered_t2p_candidate_dir,
            selected_projects,
            replace=args.replace,
            stats=stats,
        )
    stats.print_summary()

if __name__ == "__main__":
    main()
