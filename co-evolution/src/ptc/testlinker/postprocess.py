from __future__ import annotations

from pathlib import Path

import pandas as pd

from ptc.testlinker.paths import execute_csv_path, final_prediction_path, testlinker_root


FINAL_COLUMNS = [
    "project",
    "from_name",
    "to_name",
    "label",
    "label_pred",
    "pred_score",
    "recom_by",
    "testlinker_signature",
    "from_url",
    "to_url",
]


def postprocess_project(
    *,
    cache_directory: str | Path,
    project: str,
    testlinker_directory: str | Path | None = None,
) -> pd.DataFrame:
    root = testlinker_root(cache_directory, testlinker_directory)
    execute_file = execute_csv_path(root, project)
    if not execute_file.exists():
        raise FileNotFoundError(f"TestLinker execute CSV not found: {execute_file}")

    output_df = pd.read_csv(execute_file, keep_default_na=False, na_filter=False)
    for column in FINAL_COLUMNS:
        if column not in output_df.columns:
            output_df[column] = ""
    output_df = output_df[FINAL_COLUMNS]
    output_df["label"] = pd.to_numeric(output_df["label"], errors="coerce").fillna(0).astype(int)
    output_df["label_pred"] = pd.to_numeric(output_df["label_pred"], errors="coerce").fillna(0).astype(int)

    output_file = final_prediction_path(cache_directory, project)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_file, index=False)
    return output_df
