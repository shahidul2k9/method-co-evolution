from pathlib import Path

import pandas as pd

from mhc.config import DATA_DIRECTORY, PROJECT_DIRECTORY
from ptc.experiment_util import build_experiment_parser, list_csv_files, resolve_experiment_filters


T2P_CANDIDATE_DIR = Path(DATA_DIRECTORY) / "t2p-candidate-filtered"
GROUND_TRUTH_DIR = Path(PROJECT_DIRECTORY) / "data" / "ground-truth" / "testlinker-t2p-ground-truth"


def filter_candidate_df(candidate_df: pd.DataFrame, ground_truth_df: pd.DataFrame) -> pd.DataFrame:
    ground_truth_from_urls = set(ground_truth_df["from_url"])
    return candidate_df[candidate_df["from_url"].isin(ground_truth_from_urls)].copy()


def build_parser():
    return build_experiment_parser(
        "Filter method-to-method candidates to tests present in updated ground truth.",
        include_tools=False,
        include_strategies=False,
        projects_help="Comma-separated project names to process.",
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    _, selected_projects, _ = resolve_experiment_filters(
        use_filters=args.use_filters,
        projects=args.projects,
    )
    candidate_files = list_csv_files(T2P_CANDIDATE_DIR, selected_projects, strict=False)

    rows = []
    skipped = []
    for candidate_file in candidate_files:
        ground_truth_file = GROUND_TRUTH_DIR / candidate_file.name
        if not ground_truth_file.exists():
            skipped.append(candidate_file.stem)
            continue

        candidate_df = pd.read_csv(candidate_file, keep_default_na=False, na_filter=False)
        ground_truth_df = pd.read_csv(ground_truth_file, keep_default_na=False, na_filter=False)
        filtered_df = filter_candidate_df(candidate_df, ground_truth_df)
        filtered_df.to_csv(candidate_file, index=False)
        rows.append({
            "project":      candidate_file.stem,
            "rows_before":  len(candidate_df),
            "rows_after":   len(filtered_df),
            "test_urls":    filtered_df["from_url"].nunique(),
            "prod_urls":    filtered_df["to_url"].nunique(),
            "links":        filtered_df[["from_url", "to_url"]].drop_duplicates().shape[0],
        })

    for stem in skipped:
        print(f"Skipping {stem}; no ground truth found.")

    if rows:
        all_filtered = pd.concat([
            pd.read_csv(T2P_CANDIDATE_DIR / (r["project"] + ".csv"), keep_default_na=False, na_filter=False)
            for r in rows
        ], ignore_index=True)
        total = {
            "project":     "total",
            "rows_before": sum(r["rows_before"] for r in rows),
            "rows_after":  sum(r["rows_after"] for r in rows),
            "test_urls":   all_filtered["from_url"].nunique(),
            "prod_urls":   all_filtered["to_url"].nunique(),
            "links":       all_filtered[["from_url", "to_url"]].drop_duplicates().shape[0],
        }
        cols    = ["project", "rows_before", "rows_after", "test_urls", "prod_urls", "links"]
        all_rows = rows + [total]
        widths  = {c: max(len(c), max(len(str(r[c])) for r in all_rows)) for c in cols}
        sep     = "+-" + "-+-".join("-" * widths[c] for c in cols) + "-+"
        hdr     = "| " + " | ".join(c.ljust(widths[c]) for c in cols) + " |"
        print(sep)
        print(hdr)
        print(sep)
        for r in rows:
            print("| " + " | ".join(str(r[c]).rjust(widths[c]) for c in cols) + " |")
        print(sep)
        print("| " + " | ".join(str(total[c]).rjust(widths[c]) for c in cols) + " |")
        print(sep)

    print("Finished.")


if __name__ == "__main__":
    main()
