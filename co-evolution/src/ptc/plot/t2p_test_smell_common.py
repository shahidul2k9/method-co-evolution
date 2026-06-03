from __future__ import annotations

import warnings
from pathlib import Path

import pandas as pd

from mhc.command_util import list_csv_files

REVISION_TYPE = "ch_diff"
RECURRENT_TEST_DELTA_THRESHOLD = 10

PRODUCTION_RECURRENT = "production_recurrent"
TEST_RECURRENT = "test_recurrent"
COMPARABLE_CHANGE = "comparable_change"
CHANGE_GROUP_ORDER = [PRODUCTION_RECURRENT, COMPARABLE_CHANGE, TEST_RECURRENT]
CHANGE_GROUP_LABELS = {
    PRODUCTION_RECURRENT: "Production recurrent",
    COMPARABLE_CHANGE: "Comparable change",
    TEST_RECURRENT: "Test recurrent",
}

SMELL_PRESENCE_LABELS = {
    False: "No smell",
    True: "Has smell",
}


def format_count(value: int) -> str:
    return f"{value:,}"


def format_percent(value: float) -> str:
    return f"{value:.1f}%"


def assign_change_group(test_revision: int | float, production_revision: int | float) -> str:
    revision_delta = test_revision - production_revision
    if test_revision < production_revision:
        return PRODUCTION_RECURRENT
    if revision_delta >= RECURRENT_TEST_DELTA_THRESHOLD:
        return TEST_RECURRENT
    return COMPARABLE_CHANGE


def _smell_summary(smell_df: pd.DataFrame) -> pd.DataFrame:
    if smell_df.empty:
        return pd.DataFrame(columns=["from_url", "smell_count", "smell_types"])

    if "url" not in smell_df.columns or "smell" not in smell_df.columns:
        raise ValueError("Test smell CSV must include 'url' and 'smell' columns.")

    rows = []
    for url, group in smell_df.groupby("url", sort=False):
        smells = [str(smell) for smell in group["smell"].dropna() if str(smell)]
        unique_smells = sorted(set(smells))
        rows.append(
            {
                "from_url": url,
                "smell_count": len(smells),
                "smell_types": ";".join(unique_smells),
            }
        )
    return pd.DataFrame(rows, columns=["from_url", "smell_count", "smell_types"])


def _read_smell_file(experiment_directory: Path, smell_detector: str, project: str) -> pd.DataFrame:
    smell_file = experiment_directory / "test-smell" / smell_detector / f"{project}.csv"
    if not smell_file.exists():
        return pd.DataFrame(columns=["url", "smell"])
    return pd.read_csv(smell_file, keep_default_na=False, na_filter=False)


def load_recurrent_change_frame(
    experiment_directory: Path,
    tool: str,
    strategy: str,
    smell_detector: str,
    selected_projects: list[str] | None,
    *,
    min_t2p_links: int,
) -> pd.DataFrame:
    input_directory = experiment_directory / "t2p-change" / tool / strategy
    csv_files = list_csv_files(input_directory, selected_projects, strict=False)
    frames = []
    from_column = f"from_{REVISION_TYPE}"
    to_column = f"to_{REVISION_TYPE}"

    for csv_file in csv_files:
        project_df = pd.read_csv(csv_file, keep_default_na=False, na_filter=False)
        if len(project_df) < min_t2p_links:
            warnings.warn(
                f"Skipping project={csv_file.stem}, tool={tool}, strategy={strategy}: "
                f"t2p_links={len(project_df)} is below min_t2p_links={min_t2p_links}."
            )
            continue
        missing_columns = [column for column in [from_column, to_column, "from_url"] if column not in project_df]
        if missing_columns:
            warnings.warn(
                f"Skipping project={csv_file.stem}, tool={tool}, strategy={strategy}: "
                f"missing required columns {', '.join(missing_columns)}."
            )
            continue

        project = str(project_df["project"].iloc[0]) if "project" in project_df and not project_df.empty else csv_file.stem
        pair_df = project_df.copy()
        pair_df["test_revision"] = pd.to_numeric(pair_df[from_column], errors="coerce")
        pair_df["production_revision"] = pd.to_numeric(pair_df[to_column], errors="coerce")
        pair_df = pair_df[pair_df["test_revision"].notna() & pair_df["production_revision"].notna()].copy()
        if pair_df.empty:
            continue

        smell_df = _read_smell_file(experiment_directory, smell_detector, csv_file.stem)
        summary_df = _smell_summary(smell_df)
        pair_df = pair_df.merge(summary_df, on="from_url", how="left")
        pair_df["project"] = project
        pair_df["smell_count"] = pd.to_numeric(pair_df["smell_count"], errors="coerce").fillna(0).astype(int)
        pair_df["smell_types"] = pair_df["smell_types"].fillna("")
        pair_df["has_smell"] = pair_df["smell_count"] > 0
        pair_df["revision_delta"] = pair_df["test_revision"] - pair_df["production_revision"]
        pair_df["change_group"] = pair_df.apply(
            lambda row: assign_change_group(row["test_revision"], row["production_revision"]),
            axis=1,
        )
        frames.append(pair_df)

    if not frames:
        return pd.DataFrame(
            columns=[
                "project",
                "from_url",
                "test_revision",
                "production_revision",
                "revision_delta",
                "has_smell",
                "smell_count",
                "smell_types",
                "change_group",
            ]
        )

    return pd.concat(frames, ignore_index=True)


def expand_smell_types(frame: pd.DataFrame, smell_names: dict[str, str]) -> pd.DataFrame:
    rows = []
    for _, row in frame[frame["smell_types"].astype(bool)].iterrows():
        for acronym in str(row["smell_types"]).split(";"):
            if not acronym:
                continue
            expanded = row.copy()
            expanded["smell"] = acronym
            expanded["smell_name"] = smell_names.get(acronym, acronym)
            rows.append(expanded)

    if not rows:
        return pd.DataFrame(columns=list(frame.columns) + ["smell", "smell_name"])
    return pd.DataFrame(rows)
