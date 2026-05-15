from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
import re
from re import Pattern

import pandas as pd
from mhc.artifacts import is_test_code, is_test_case_method
from mhc.util import parse_project_index

from mhc.config import DATA_DIRECTORY

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
    "from_artifact",
    "to_artifact",
    "to_call_depth",
    "label",
    "tags",
    "notes",
]
PROTECTED_UPDATE_COLUMNS = {"from_url", "to_url", "label", "tags", "notes"}
METHOD_TO_GT_COLUMNS = {
    "from_name": "name",
    "from_fqs": "fqs",
    "from_tctracer_fqs": "tctracer_fqs",
    "from_testlinker_fqs": "testlinker_fqs",
    "from_artifact": "artifact",
    "to_name": "name",
    "to_fqs": "fqs",
    "to_tctracer_fqs": "tctracer_fqs",
    "to_testlinker_fqs": "testlinker_fqs",
    "to_artifact": "artifact",
}

_DATA = Path(DATA_DIRECTORY)
REPOSITORY_FILE = _DATA / "repository" / "repository.csv"
T2P_CANDIDATE_DIR = _DATA / "t2p-candidate-expanded"
METHOD_DIR = _DATA / "method"

OUTPUT_DIR = _DATA / "t2p-ground-truth-labelling" / "t2plinker-t2p-ground-truth-labelling"
TEMP_DIR = _DATA / "t2p-ground-truth-labelling" / ".t2plinker-t2p-ground-truth-labelling"


@dataclass(frozen=True)
class GroundTruthProjectStats:
    project: str
    working_test_methods: int
    reused_test_methods: int
    added_test_methods: int
    excluded_test_methods: int
    selected_test_methods: int
    generated_rows: int
    manual_rows_preserved: int
    rows_refreshed: int
    rows_not_refreshed: int
    carried_label_rows: int
    new_or_unlabelled_rows: int
    output_file: Path


def _load_repository_projects() -> list[str]:
    repo_df = pd.read_csv(REPOSITORY_FILE, keep_default_na=False, na_filter=False)
    if "project" not in repo_df.columns:
        raise ValueError(f"repository index is missing project column: {REPOSITORY_FILE}")
    return repo_df["project"].dropna().astype(str).tolist()


def _test_caller_pool(
    project: str,
    *,
    exclude_test_artifact_pattern: Pattern[str] | None = None,
) -> tuple[pd.DataFrame, list[str], int, str | None]:
    """Return fresh callgraph rows, random-sampling pool, excluded count, and skip reason."""
    cg_file = T2P_CANDIDATE_DIR / f"{project}.csv"
    method_file = METHOD_DIR / f"{project}.csv"

    missing = [str(path) for path in (cg_file, method_file) if not path.exists()]
    if missing:
        return pd.DataFrame(), [], 0, f"missing input file(s): {', '.join(missing)}"

    method_df = pd.read_csv(method_file, keep_default_na=False, na_filter=False, usecols=["url", "artifact"])
    artifact_by_url = dict(zip(method_df["url"], method_df["artifact"]))
    test_method_df = method_df[method_df["artifact"].map(is_test_case_method)].copy()
    test_urls = set(test_method_df["url"])
    if not test_urls:
        return pd.DataFrame(), [], 0, "no methods marked artifact=#test-case-method"

    cg_df = pd.read_csv(cg_file, keep_default_na=False, na_filter=False)
    cg_test = cg_df[cg_df["from_url"].isin(test_urls)].copy()
    if cg_test.empty:
        return pd.DataFrame(), [], 0, "no candidate rows whose from_url matches an artifact=#test-case-method method"

    cg_test["from_artifact"] = cg_test["from_url"].map(artifact_by_url).fillna("")
    cg_test["to_artifact"] = cg_test["to_url"].map(artifact_by_url).fillna("")
    candidate_urls = list(cg_test["from_url"].drop_duplicates())

    excluded_urls: set[str] = set()
    if exclude_test_artifact_pattern is not None:
        excluded_urls = set(
            test_method_df[
                test_method_df["artifact"].map(lambda value: bool(exclude_test_artifact_pattern.search(str(value))))
            ]["url"]
        )

    fresh_pool_urls = [url for url in candidate_urls if url not in excluded_urls]
    excluded_candidate_count = len([url for url in candidate_urls if url in excluded_urls])
    return cg_test, fresh_pool_urls, excluded_candidate_count, None


def _build_output_df(cg_rows: pd.DataFrame, selected_urls: set[str]) -> pd.DataFrame:
    """Filter callgraph rows to selected test URLs and map to ground truth columns."""
    rows = cg_rows[cg_rows["from_url"].isin(selected_urls)].copy()
    rows["_to_call_depth_sort"] = pd.to_numeric(rows.get("to_call_depth", ""), errors="coerce")
    rows = (
        rows.sort_values(["from_url", "to_url", "_to_call_depth_sort"], na_position="last")
        .drop_duplicates(subset=["from_url", "to_url"], keep="first")
        .drop(columns=["_to_call_depth_sort"])
    )

    out = pd.DataFrame(index=rows.index)
    for gt_col in GROUND_TRUTH_COLUMNS:
        cg_col = gt_col  # column names align where present
        if cg_col in rows.columns:
            out[gt_col] = rows[cg_col].values
        else:
            out[gt_col] = pd.NA
    out.loc[out["to_artifact"].map(is_test_code), "label"] = 0
    return out[GROUND_TRUTH_COLUMNS].reset_index(drop=True)


def _read_working_ground_truth(project: str, working_dir: Path) -> pd.DataFrame:
    working_file = working_dir / f"{project}.csv"
    if not working_file.exists():
        return pd.DataFrame(columns=GROUND_TRUTH_COLUMNS)

    working_df = pd.read_csv(working_file, keep_default_na=False, na_filter=False)
    if "notes" not in working_df.columns and "note" in working_df.columns:
        working_df["notes"] = working_df["note"]
    for column in GROUND_TRUTH_COLUMNS:
        if column not in working_df.columns:
            working_df[column] = ""
    return working_df


def _load_method_rows_by_url(project: str) -> dict[str, dict[str, str]]:
    method_file = METHOD_DIR / f"{project}.csv"
    if not method_file.exists():
        return {}
    method_df = pd.read_csv(method_file, keep_default_na=False, na_filter=False)
    if "url" not in method_df.columns:
        return {}
    return {
        str(row.get("url", "")): {str(key): str(value) for key, value in row.items()}
        for row in method_df.to_dict(orient="records")
        if str(row.get("url", ""))
    }


def parse_update_columns(value: str | None) -> list[str]:
    if not value:
        return []

    columns = list(dict.fromkeys(column.strip() for column in value.split(",") if column.strip()))
    unknown_columns = [column for column in columns if column not in GROUND_TRUTH_COLUMNS]
    if unknown_columns:
        raise ValueError(f"unknown update column(s): {', '.join(unknown_columns)}")

    protected_columns = [column for column in columns if column in PROTECTED_UPDATE_COLUMNS]
    if protected_columns:
        raise ValueError(f"protected update column(s) cannot be refreshed: {', '.join(protected_columns)}")

    return columns


def _working_labels_by_pair(working_df: pd.DataFrame) -> dict[tuple[str, str], dict[str, str]]:
    labels: dict[tuple[str, str], dict[str, str]] = {}
    if working_df.empty or not {"from_url", "to_url"}.issubset(working_df.columns):
        return labels

    for row in working_df.to_dict(orient="records"):
        key = (str(row.get("from_url", "")), str(row.get("to_url", "")))
        if not all(key):
            continue
        labels[key] = {
            "label": str(row.get("label", "")),
            "tags": str(row.get("tags", "")),
            "notes": str(row.get("notes", row.get("note", ""))),
        }
    return labels


def _select_test_methods(
    *,
    available_urls: list[str],
    working_urls: list[str],
    sample_count_per_project: int,
    random_state: int | None = None,
) -> tuple[set[str], int, int]:
    reused_unique = list(dict.fromkeys(url for url in working_urls if url))
    reused_set = set(reused_unique)

    remaining_needed = max(0, sample_count_per_project - len(reused_unique))
    candidate_urls = [url for url in available_urls if url not in reused_set]
    if remaining_needed >= len(candidate_urls):
        added_urls = candidate_urls
    elif remaining_needed == 0:
        added_urls = []
    else:
        added_urls = pd.Series(candidate_urls).sample(n=remaining_needed, random_state=random_state).tolist()

    selected_urls = set(reused_unique + added_urls)
    return selected_urls, len(reused_unique), len(added_urls)


def _merge_working_labels(
    output_df: pd.DataFrame,
    working_df: pd.DataFrame,
    *,
    update_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, int, int]:
    working_labels = _working_labels_by_pair(working_df)
    if not working_labels:
        return output_df, 0, 0

    merged_df = output_df.copy()
    carried_label_rows = 0
    refreshed_rows = 0
    for index, row in merged_df.iterrows():
        labels = working_labels.get((str(row["from_url"]), str(row["to_url"])))
        if labels is None:
            continue
        for column in ("label", "tags", "notes"):
            merged_df.at[index, column] = labels[column]
        if labels["label"].strip():
            carried_label_rows += 1
        if update_columns:
            refreshed_rows += 1
    return merged_df, carried_label_rows, refreshed_rows


def _append_missing_working_rows(
    output_df: pd.DataFrame,
    working_df: pd.DataFrame,
    selected_urls: set[str],
    *,
    method_rows_by_url: dict[str, dict[str, str]] | None = None,
    update_columns: list[str] | None = None,
) -> tuple[pd.DataFrame, int, int, int, int]:
    if working_df.empty:
        return output_df, 0, 0, 0, 0

    existing_pairs = {
        (str(row["from_url"]), str(row["to_url"]))
        for _, row in output_df.iterrows()
        if str(row.get("from_url", "")) and str(row.get("to_url", ""))
    }
    manual_rows: list[dict[str, str]] = []
    manual_labelled_rows = 0
    rows_refreshed = 0
    rows_not_refreshed = 0
    update_columns = update_columns or []
    method_rows_by_url = method_rows_by_url or {}
    for row in working_df.to_dict(orient="records"):
        from_url = str(row.get("from_url", ""))
        to_url = str(row.get("to_url", ""))
        if not from_url or not to_url or from_url not in selected_urls:
            continue
        pair = (from_url, to_url)
        if pair in existing_pairs:
            continue
        manual_row = {column: str(row.get(column, "")) for column in GROUND_TRUTH_COLUMNS}
        refreshed = _refresh_manual_row_from_method(
            manual_row,
            from_method_row=method_rows_by_url.get(from_url),
            to_method_row=method_rows_by_url.get(to_url),
            update_columns=update_columns,
        )
        if update_columns:
            if refreshed:
                rows_refreshed += 1
            else:
                rows_not_refreshed += 1
        manual_rows.append(manual_row)
        existing_pairs.add(pair)
        if manual_row["label"].strip():
            manual_labelled_rows += 1

    if not manual_rows:
        return output_df, 0, 0, 0, 0

    merged_df = pd.concat([output_df, pd.DataFrame(manual_rows)], ignore_index=True)
    return (
        merged_df[GROUND_TRUTH_COLUMNS],
        len(manual_rows),
        manual_labelled_rows,
        rows_refreshed,
        rows_not_refreshed,
    )


def _refresh_manual_row_from_method(
    manual_row: dict[str, str],
    *,
    from_method_row: dict[str, str] | None,
    to_method_row: dict[str, str] | None,
    update_columns: list[str],
) -> bool:
    if not update_columns:
        return False

    refreshed = False
    for column in update_columns:
        method_column = METHOD_TO_GT_COLUMNS.get(column)
        method_row = from_method_row if column.startswith("from_") else to_method_row
        if method_column is None or method_row is None or method_column not in method_row:
            continue
        manual_row[column] = method_row.get(method_column, "")
        refreshed = True
    return refreshed


def _write_output_atomic(output_df: pd.DataFrame, *, project: str, output_dir: Path, temp_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    temp_file = temp_dir / f"{project}.csv"
    output_file = output_dir / f"{project}.csv"
    output_df.to_csv(temp_file, index=False)
    temp_file.replace(output_file)
    return output_file


def regenerate_project(
    *,
    project: str,
    sample_count_per_project: int,
    working_dir: Path,
    output_dir: Path = OUTPUT_DIR,
    temp_dir: Path = TEMP_DIR,
    random_state: int | None = None,
    exclude_test_artifact_pattern: Pattern[str] | None = None,
    update_columns: list[str] | None = None,
) -> GroundTruthProjectStats | None:
    cg_df, fresh_pool_urls, excluded_count, skip_reason = _test_caller_pool(
        project,
        exclude_test_artifact_pattern=exclude_test_artifact_pattern,
    )
    if skip_reason:
        print(f"  {project}: {skip_reason} - skipped")
        return None

    working_df = _read_working_ground_truth(project, working_dir)
    working_urls = (
        working_df["from_url"].dropna().astype(str).tolist()
        if "from_url" in working_df.columns
        else []
    )
    selected_urls, reused_count, added_count = _select_test_methods(
        available_urls=fresh_pool_urls,
        working_urls=working_urls,
        sample_count_per_project=sample_count_per_project,
        random_state=random_state,
    )

    output_df = _build_output_df(cg_df, selected_urls)
    output_df, carried_label_rows, fresh_rows_refreshed = _merge_working_labels(
        output_df,
        working_df,
        update_columns=update_columns,
    )
    output_df, manual_rows_preserved, manual_labelled_rows, manual_rows_refreshed, manual_rows_not_refreshed = (
        _append_missing_working_rows(
            output_df,
            working_df,
            selected_urls,
            method_rows_by_url=_load_method_rows_by_url(project),
            update_columns=update_columns,
        )
    )
    carried_label_rows += manual_labelled_rows
    rows_refreshed = fresh_rows_refreshed + manual_rows_refreshed

    output_file = _write_output_atomic(output_df, project=project, output_dir=output_dir, temp_dir=temp_dir)

    new_or_unlabelled_rows = int((output_df["label"].astype(str).str.strip() == "").sum())
    return GroundTruthProjectStats(
        project=project,
        working_test_methods=working_df["from_url"].nunique() if "from_url" in working_df.columns else 0,
        reused_test_methods=reused_count,
        added_test_methods=added_count,
        excluded_test_methods=excluded_count,
        selected_test_methods=len(selected_urls),
        generated_rows=len(output_df),
        manual_rows_preserved=manual_rows_preserved,
        rows_refreshed=rows_refreshed,
        rows_not_refreshed=manual_rows_not_refreshed,
        carried_label_rows=carried_label_rows,
        new_or_unlabelled_rows=new_or_unlabelled_rows,
        output_file=output_file,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Regenerate sampled ground truth CSVs for labeling.")
    parser.add_argument(
        "--project-index",
        required=True,
        help="Python-style project index or slice from data/repository/repository.csv.",
    )
    parser.add_argument(
        "--sample-count-per-project",
        type=int,
        required=True,
        help="Number of test methods to sample per selected project.",
    )
    parser.add_argument(
        "--ground-truth-working-inprogress",
        type=Path,
        required=True,
        help="Directory containing in-progress per-project ground truth CSVs.",
    )
    parser.add_argument(
        "--exclude-test-artifact-regex",
        default=None,
        help="Regex matched against method artifact tags; matching test methods are excluded from fresh random additions.",
    )
    parser.add_argument(
        "--update-columns",
        default=None,
        help="Comma-separated ground-truth columns to refresh on reused rows when source data is available.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.sample_count_per_project <= 0:
        parser.error("--sample-count-per-project must be a positive integer")

    working_dir = args.ground_truth_working_inprogress.expanduser()
    if not working_dir.is_dir():
        parser.error(f"--ground-truth-working-inprogress does not exist: {working_dir}")

    exclude_test_artifact_pattern = None
    if args.exclude_test_artifact_regex:
        try:
            exclude_test_artifact_pattern = re.compile(args.exclude_test_artifact_regex)
        except re.error as exc:
            parser.error(f"--exclude-test-artifact-regex is invalid: {exc}")

    try:
        update_columns = parse_update_columns(args.update_columns)
    except ValueError as exc:
        parser.error(str(exc))

    try:
        projects = parse_project_index(args.project_index, _load_repository_projects())
    except ValueError as exc:
        parser.error(str(exc))

    if not projects:
        print("No projects selected.")
        return 0

    print(f"Selected projects: {len(projects)}")
    print(f"Sample count per project: {args.sample_count_per_project}")
    print(f"Working in-progress directory: {working_dir}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Temporary output directory: {TEMP_DIR}")
    if args.exclude_test_artifact_regex:
        print(f"Exclude test artifact regex: {args.exclude_test_artifact_regex}")
    if update_columns:
        print(f"Update columns: {', '.join(update_columns)}")
    print()

    stats: list[GroundTruthProjectStats] = []
    for project in projects:
        project_stats = regenerate_project(
            project=project,
            sample_count_per_project=args.sample_count_per_project,
            working_dir=working_dir,
            output_dir=OUTPUT_DIR,
            temp_dir=TEMP_DIR,
            exclude_test_artifact_pattern=exclude_test_artifact_pattern,
            update_columns=update_columns,
        )
        if project_stats is None:
            continue
        stats.append(project_stats)
        print(
            f"  {project}: reused {project_stats.reused_test_methods}/"
            f"{project_stats.working_test_methods} working test methods, "
            f"added {project_stats.added_test_methods}, "
            f"excluded {project_stats.excluded_test_methods}, "
            f"rows {project_stats.generated_rows}, "
            f"manual rows {project_stats.manual_rows_preserved}, "
            f"refreshed {project_stats.rows_refreshed}, "
            f"not refreshed {project_stats.rows_not_refreshed}, "
            f"carried labels {project_stats.carried_label_rows}, "
            f"unlabelled {project_stats.new_or_unlabelled_rows} -> "
            f"{project_stats.output_file}"
        )

    print(
        "\nTotal: "
        f"{len(stats)} projects, "
        f"{sum(item.reused_test_methods for item in stats)} reused test methods, "
        f"{sum(item.added_test_methods for item in stats)} added test methods, "
        f"{sum(item.excluded_test_methods for item in stats)} excluded test methods, "
        f"{sum(item.generated_rows for item in stats)} rows, "
        f"{sum(item.manual_rows_preserved for item in stats)} manual rows preserved, "
        f"{sum(item.rows_refreshed for item in stats)} rows refreshed, "
        f"{sum(item.rows_not_refreshed for item in stats)} rows not refreshed, "
        f"{sum(item.carried_label_rows for item in stats)} carried labels, "
        f"{sum(item.new_or_unlabelled_rows for item in stats)} unlabelled rows"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
