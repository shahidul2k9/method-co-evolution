from pathlib import Path

import pandas as pd

from mhc.config import PROJECT_DIRECTORY
from ptc.experiment_util import build_experiment_parser, list_csv_files, resolve_experiment_filters, resolve_experiment_paths, resolve_experiment_name


UNNEEDED_CANDIDATE_COLUMNS = ["from_fqs_alt", "to_fqs_alt"]


def build_parser():
    parser = build_experiment_parser(
        "Filter expanded test-to-production candidates.",
        include_tools=False,
        include_strategies=False,
        projects_help="Comma-separated project names to process.",
    )
    parser.add_argument(
        "--ground-truth",
        action="store_true",
        help="Filter existing candidate files to tests present in the ground-truth files.",
    )
    return parser


def filter_candidate_df(candidate_df: pd.DataFrame) -> pd.DataFrame:
    return candidate_df.drop(columns=UNNEEDED_CANDIDATE_COLUMNS, errors="ignore").copy()


def filter_candidate_df_by_ground_truth(candidate_df: pd.DataFrame, ground_truth_df: pd.DataFrame) -> pd.DataFrame:
    ground_truth_from_urls = set(ground_truth_df["from_url"])
    return candidate_df[candidate_df["from_url"].isin(ground_truth_from_urls)].copy()


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
) -> None:
    for candidate_file in list_csv_files(expanded_t2p_candidate_dir, selected_projects, strict=False):
        print("Processing:", candidate_file.stem)
        candidate_df = pd.read_csv(candidate_file, keep_default_na=False, na_filter=False)
        filtered_df = filter_candidate_df(candidate_df)
        output_file = filtered_t2p_candidate_dir / candidate_file.name
        filtered_df.to_csv(output_file, index=False)


def filter_candidate_files_by_ground_truth(t2p_ground_truth_dir:Path, filtered_t2p_candidate_dir: Path, selected_projects: list[str] | None) -> None:
    rows = []
    skipped = []
    for candidate_file in list_csv_files(filtered_t2p_candidate_dir, selected_projects, strict=False):
        ground_truth_file = t2p_ground_truth_dir / candidate_file.name
        if not ground_truth_file.exists():
            skipped.append(candidate_file.stem)
            continue

        candidate_df = pd.read_csv(candidate_file, keep_default_na=False, na_filter=False)
        ground_truth_df = pd.read_csv(ground_truth_file, keep_default_na=False, na_filter=False)
        filtered_df = filter_candidate_df_by_ground_truth(candidate_df, ground_truth_df)
        filtered_df.to_csv(candidate_file, index=False)
        rows.append({
            "project": candidate_file.stem,
            "rows_before": len(candidate_df),
            "rows_after": len(filtered_df),
            "test_urls": filtered_df["from_url"].nunique(),
            "prod_urls": filtered_df["to_url"].nunique(),
            "links": filtered_df[["from_url", "to_url"]].drop_duplicates().shape[0],
        })

    for stem in skipped:
        print(f"Skipping {stem}; no ground truth found.")

    print_ground_truth_filter_summary(rows, filtered_t2p_candidate_dir)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    expanded_t2p_candidate_dir = experiment_directory / "t2p-candidate-expanded"
    filtered_t2p_candidate_dir = experiment_directory / "t2p-candidate-filtered"
    filtered_t2p_candidate_dir.mkdir(parents=True, exist_ok=True)
    _, selected_projects, _ = resolve_experiment_filters(
        use_filters=args.use_filters,
        projects=args.projects,
    )
    t2p_ground_truth_dir = Path(PROJECT_DIRECTORY) / "data" / resolve_experiment_name(args.experiment_name) / "t2p-ground-truth"

    if args.ground_truth:
        filter_candidate_files_by_ground_truth(t2p_ground_truth_dir, filtered_t2p_candidate_dir, selected_projects)
    else:
        filter_expanded_candidate_files(expanded_t2p_candidate_dir, filtered_t2p_candidate_dir, selected_projects)

    print("Finished.")


if __name__ == "__main__":
    main()
