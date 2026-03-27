from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ptc.llm.prompting import JsonPredictionParser


def project_t2p_links(
    *,
    candidate_file: Path,
    llm_run_file: Path,
    output_file: Path,
) -> pd.DataFrame:
    candidate_df = pd.read_csv(candidate_file, keep_default_na=False, na_filter=False)
    llm_run_df = pd.read_csv(llm_run_file, keep_default_na=False, na_filter=False) if llm_run_file.exists() else pd.DataFrame()

    parsed_rows: list[dict[str, object]] = []
    if not llm_run_df.empty:
        for row in llm_run_df.to_dict(orient="records"):
            payload = _load_output_payload(row)
            method_lookup = _method_lookup(payload)
            parsed_rows.append(
                {
                    "url": row.get("url", ""),
                    "llm_names": "|".join(method_lookup.keys()),
                    "llm_method_lookup_json": json.dumps(method_lookup, ensure_ascii=True),
                }
            )

    parsed_df = pd.DataFrame(parsed_rows)
    if parsed_df.empty:
        merged_df = candidate_df.copy()
        merged_df["llm_names"] = ""
        merged_df["llm_method_lookup_json"] = ""
    else:
        merged_df = candidate_df.merge(parsed_df, left_on="from_url", right_on="url", how="left").drop(columns=["url"])
        merged_df["llm_names"] = merged_df["llm_names"].fillna("")
        merged_df["llm_method_lookup_json"] = merged_df["llm_method_lookup_json"].fillna("")

    projected_rows: list[dict[str, object]] = []
    for row in merged_df.to_dict(orient="records"):
        method_lookup = json.loads(row["llm_method_lookup_json"]) if row["llm_method_lookup_json"] else {}
        method_payload = method_lookup.get(row.get("to_name", ""), {})
        projected_rows.append(
            {
                "project": row.get("project", output_file.stem),
                "from_name": row.get("from_name", ""),
                "to_name": row.get("to_name", ""),
                "from_url": row.get("from_url", ""),
                "to_url": row.get("to_url", ""),
                "label_pred": 1 if row.get("to_name", "") in method_lookup else 0,
                "confidence": method_payload.get("confidence", ""),
                "rationale": method_payload.get("rationale", ""),
            }
        )

    projected_df = pd.DataFrame(projected_rows)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    projected_df.to_csv(output_file, index=False)
    return projected_df


def _load_output_payload(row: dict[str, str]) -> dict | None:
    output_json = _nullable_value(row.get("output_json"))
    if output_json is not None:
        try:
            return json.loads(output_json)
        except json.JSONDecodeError:
            pass

    output_raw = _nullable_value(row.get("output_raw"))
    if output_raw is not None:
        return JsonPredictionParser.extract_payload_or_none(output_raw)
    return None


def _method_lookup(payload: dict | None) -> dict[str, dict[str, object]]:
    if payload is None:
        return {}

    method_lookup: dict[str, dict[str, object]] = {}
    methods_payload = payload.get("methods", [])
    if not isinstance(methods_payload, list):
        return method_lookup

    for method_payload in methods_payload:
        if not isinstance(method_payload, dict):
            continue
        method_name = method_payload.get("name", "")
        if not method_name:
            continue
        confidence = method_payload.get("confidence", "")
        rationale = method_payload.get("rationale", "")
        current_payload = method_lookup.get(method_name)
        current_confidence = current_payload.get("confidence", -1) if current_payload else -1
        if current_payload is None or (isinstance(confidence, (int, float)) and confidence >= current_confidence):
            method_lookup[method_name] = {
                "confidence": confidence,
                "rationale": rationale,
            }
    return method_lookup


def _nullable_value(value):
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str) and value.strip().lower() in {"", "null"}:
        return None
    return value
