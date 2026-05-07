from __future__ import annotations

from pathlib import Path

import pandas as pd

from mhc.config import DATA_DIRECTORY, WORKSPACE_DIRECTORY

RANDOM_SEED = 42
SAMPLE_PER_PROJECT = 20
EXCLUDE_PROJECTS = {"okhttp"}
GROUND_TRUTH_COLUMNS = [
    "project",
    "from_name",
    "to_name",
    "from_url",
    "to_url",
    "from_fqs",
    "from_tctracer_fqs",
    "from_testlinker_fqs",
    "to_fqs",
    "to_tctracer_fqs",
    "to_testlinker_fqs",
    "to_call_depth",
    "label",
    "note",
]

# Mapping from callgraph columns to ground truth columns
_CALLGRAPH_TO_GT = {
    "project": "project",
    "from_name": "from_name",
    "to_name": "to_name",
    "from_url": "from_url",
    "to_url": "to_url",
    "from_fqs": "from_fqs",
    "to_fqs": "to_fqs",
}

_WORKSPACE = Path(WORKSPACE_DIRECTORY)
_DATA = Path(DATA_DIRECTORY)
REPOSITORY_FILE = _DATA / "repository" / "repository.csv"
T2P_CANDIDATE_DIR = _DATA / "t2p-candidate-expanded"
METHOD_DIR = _DATA / "method"

OUTPUT_DIR = _DATA / "ground-truth" / "t2plinker-t2p-ground-truth"


def _load_grund_projects() -> list[str]:
    repo_df = pd.read_csv(REPOSITORY_FILE, keep_default_na=False, na_filter=False)
    projects = (
        repo_df[repo_df["ref"].str.contains("grund", na=False)]["project"]
        .tolist()
    )
    return [p for p in projects if p not in EXCLUDE_PROJECTS]


def _test_caller_pool(project: str) -> tuple[set[str], pd.DataFrame, str | None]:
    """Return (unique test from_urls, matching callgraph df, skip reason) for a project."""
    cg_file = T2P_CANDIDATE_DIR / f"{project}.csv"
    method_file = METHOD_DIR / f"{project}.csv"

    empty = (set(), pd.DataFrame())
    missing = [str(path) for path in (cg_file, method_file) if not path.exists()]
    if missing:
        return (*empty, f"missing input file(s): {', '.join(missing)}")

    method_df = pd.read_csv(method_file, keep_default_na=False, na_filter=False, usecols=["url", "artifact"])
    test_urls = set(method_df[method_df["artifact"] == "test"]["url"])
    if not test_urls:
        return (*empty, "no methods marked artifact=test")

    cg_df = pd.read_csv(cg_file, keep_default_na=False, na_filter=False)
    cg_test = cg_df[cg_df["from_url"].isin(test_urls)].copy()
    if cg_test.empty:
        return (*empty, "no candidate rows whose from_url matches an artifact=test method")

    return test_urls, cg_test, None


def _build_output_df(cg_rows: pd.DataFrame, selected_urls: set[str]) -> pd.DataFrame:
    """Filter callgraph rows to selected test URLs and map to ground truth columns."""
    rows = cg_rows[cg_rows["from_url"].isin(selected_urls)].copy()
    out = pd.DataFrame(index=rows.index)
    for gt_col in GROUND_TRUTH_COLUMNS:
        cg_col = gt_col  # column names align where present
        if cg_col in rows.columns:
            out[gt_col] = rows[cg_col].values
        else:
            out[gt_col] = pd.NA
    return out[GROUND_TRUTH_COLUMNS].reset_index(drop=True)


def main(argv: list[str] | None = None) -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Sample test methods for ground truth labeling.")
    parser.add_argument("--replace", action="store_true", help="Replace existing output files (default: skip).")
    args = parser.parse_args(argv)

    projects = _load_grund_projects()
    print(f"grund projects (excl. okhttp): {len(projects)}")

    pools: list[tuple[str, set[str], pd.DataFrame]] = []
    for project in projects:
        test_urls, cg_df, skip_reason = _test_caller_pool(project)
        unique_callers = cg_df["from_url"].nunique() if not cg_df.empty else 0
        if skip_reason:
            print(f"  {project}: {skip_reason} — skipped")
        else:
            pools.append((project, test_urls, cg_df))
            print(f"  {project}: {unique_callers} unique test callers available")

    n_eligible = len(pools)
    if n_eligible == 0:
        print("No eligible projects found — check that T2P_CANDIDATE_DIR and METHOD_DIR exist and contain data.")
        return
    print(f"\nEligible projects: {n_eligible}")
    print(f"Sample per project: {SAMPLE_PER_PROJECT}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    total_methods = 0
    total_rows = 0

    for project, test_urls, cg_df in pools:
        out_file = OUTPUT_DIR / f"{project}.csv"
        if not args.replace and out_file.exists():
            print(f"  {project}: already exists — skipped (use --replace to overwrite)")
            continue

        n = SAMPLE_PER_PROJECT
        unique_urls = list(cg_df["from_url"].unique())

        if len(unique_urls) < n:
            print(f"  {project}: only {len(unique_urls)} available, wanted {n} — taking all")
            selected = set(unique_urls)
        else:
            selected = set(
                pd.Series(unique_urls).sample(n=n, random_state=RANDOM_SEED).tolist()
            )

        output_df = _build_output_df(cg_df, selected)
        output_df.to_csv(out_file, index=False)
        total_methods += len(selected)
        total_rows += len(output_df)
        print(f"  {project}: {len(selected)} test methods → {len(output_df)} candidate rows → {out_file.name}")

    print(f"\nTotal: {total_methods} test methods, {total_rows} candidate rows across {len(pools)} files → {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
