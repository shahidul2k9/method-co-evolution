from pathlib import Path

import pandas as pd

from mhc.config import DATA_DIRECTORY, PROJECT_DIRECTORY
from ptc.experiment_util import build_experiment_parser, list_csv_files, resolve_experiment_filters


T2P_CANDIDATE_DIR = Path(DATA_DIRECTORY) / "t2p-candidate"
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

    for candidate_file in candidate_files:
        ground_truth_file = GROUND_TRUTH_DIR / candidate_file.name
        if not ground_truth_file.exists():
            print(f"Skipping {candidate_file.stem}; no ground truth found.")
            continue

        candidate_df = pd.read_csv(candidate_file, keep_default_na=False, na_filter=False)
        ground_truth_df = pd.read_csv(ground_truth_file, keep_default_na=False, na_filter=False)
        filtered_df = filter_candidate_df(candidate_df, ground_truth_df)
        filtered_df.to_csv(candidate_file, index=False)
        print(f"Filtered {candidate_file.stem}: {len(candidate_df)} -> {len(filtered_df)} rows")

    print("Finished.")


if __name__ == "__main__":
    main()
