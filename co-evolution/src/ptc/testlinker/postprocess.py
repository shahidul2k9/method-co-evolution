from __future__ import annotations

from pathlib import Path

import pandas as pd

from ptc.testlinker.paths import execute_csv_path, final_prediction_path, testlinker_root


POSTPROCESS_MODES = ["testlinker-heuristics", "javaparser-symbolsolver"]

_HEURISTICS_COLUMNS = [
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

_SYMBOLSOLVER_COLUMNS = [
    "project",
    "from_name",
    "to_name",
    "label",
    "testlinker_symbolsolver",
    "from_url",
    "to_url",
]

_MODE_COLUMNS = {
    "testlinker-heuristics": _HEURISTICS_COLUMNS,
    "javaparser-symbolsolver": _SYMBOLSOLVER_COLUMNS,
}


def postprocess_project(
    *,
    cache_directory: str | Path,
    project: str,
    testlinker_directory: str | Path | None = None,
    modes: list[str] | None = None,
    replace: bool = False,
) -> dict[str, pd.DataFrame]:
    if modes is None:
        modes = ["testlinker-heuristics"]

    if not replace:
        results = {}
        pending_modes = []
        for mode in modes:
            output_file = final_prediction_path(cache_directory, project, mode)
            if output_file.exists():
                results[mode] = pd.read_csv(output_file, keep_default_na=False, na_filter=False)
            else:
                pending_modes.append(mode)
        if not pending_modes:
            return results
        modes = pending_modes
    else:
        results = {}

    root = testlinker_root(cache_directory, testlinker_directory)

    sig_url_pairs: set[tuple[str, str]] | None = None

    for mode in modes:
        execute_file = execute_csv_path(root, project, mode)
        if not execute_file.exists():
            raise FileNotFoundError(f"TestLinker execute CSV not found: {execute_file}")

        execute_df = pd.read_csv(execute_file, keep_default_na=False, na_filter=False)
        execute_df["label"] = pd.to_numeric(execute_df.get("label", 0), errors="coerce").fillna(0).astype(int)
        execute_df["label_pred"] = pd.to_numeric(execute_df.get("label_pred", 0), errors="coerce").fillna(0).astype(int)

        if mode == "javaparser-symbolsolver":
            if sig_url_pairs is None:
                method_file = Path(cache_directory) / "data" / "method" / f"{project}.csv"
                sig_url_pairs = _build_sig_url_pairs(method_file)
            testlinker_sigs = execute_df.get("testlinker_signature", pd.Series(dtype=str)).fillna("").tolist()
            to_urls = execute_df.get("to_url", pd.Series(dtype=str)).fillna("").tolist()
            execute_df["testlinker_symbolsolver"] = [
                1 if (sig, url) in sig_url_pairs else 0
                for sig, url in zip(testlinker_sigs, to_urls)
            ]

        columns = _MODE_COLUMNS[mode]
        mode_df = execute_df.copy()
        for col in columns:
            if col not in mode_df.columns:
                mode_df[col] = ""
        mode_df = mode_df[columns]

        output_file = final_prediction_path(cache_directory, project, mode)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        mode_df.to_csv(output_file, index=False)
        results[mode] = mode_df

    return results


def _build_sig_url_pairs(method_file: Path) -> set[tuple[str, str]]:
    """Build (sig_without_params, url) pairs from method scan data."""
    if not method_file.exists():
        return set()
    try:
        method_df = pd.read_csv(method_file, keep_default_na=False, na_filter=False)
    except Exception:
        return set()

    pairs: set[tuple[str, str]] = set()
    for row in method_df.to_dict(orient="records"):
        url = str(row.get("url", "") or "").strip()
        if not url:
            continue
        for col in ("testlinker_fqs", "tctracer_fqs", "fqs", "fqn"):
            val = str(row.get(col, "") or "").strip()
            if not val:
                continue
            sig_no_params = val[:val.index("(")] if "(" in val else val
            if sig_no_params:
                pairs.add((sig_no_params, url))
    return pairs
