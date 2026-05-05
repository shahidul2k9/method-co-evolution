from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ptc.testlinker.paths import raw_input_json_directory


def write_project_json(input_df: pd.DataFrame, *, root: Path, project: str) -> Path:
    output_dir = raw_input_json_directory(root, project)
    _clear_json_directory(output_dir)
    for _, group_df in input_df.groupby("test_id", sort=False):
        payload = csv_rows_to_example(group_df.to_dict(orient="records"))
        (output_dir / f"{payload['id']}.json").write_text(
            json.dumps(payload, ensure_ascii=True),
            encoding="utf-8",
        )
    return output_dir



def read_examples(directory: Path) -> list[dict[str, object]]:
    examples = []
    for json_file in sorted(directory.glob("*.json")):
        examples.append(json.loads(json_file.read_text(encoding="utf-8")))
    return examples


def csv_rows_to_example(rows: list[dict[str, object]]) -> dict[str, object]:
    if not rows:
        raise ValueError("Cannot build a TestLinker example from zero rows.")

    first_row = rows[0]
    invocations: list[str] = []
    signatures: dict[str, dict[str, object]] = {}
    candidate_urls: dict[str, list[str]] = {}
    candidate_names: dict[str, str] = {}
    labels: list[str] = []
    label_urls: list[str] = []

    for row in rows:
        invocation = str(row.get("invocation", "") or "")
        if invocation and invocation not in invocations:
            invocations.append(invocation)

        signature = str(row.get("signature", "") or "")
        if signature:
            params = _load_json(row.get("params_json"), [])
            detail_sigs = _load_json(row.get("detail_sigs_json"), [signature])
            signatures[signature] = {
                "params_len": len(params),
                "params": params,
                "detail_sigs": detail_sigs,
            }
            candidate_url = str(row.get("candidate_url", "") or "")
            candidate_urls.setdefault(signature, [])
            if candidate_url and candidate_url not in candidate_urls[signature]:
                candidate_urls[signature].append(candidate_url)
            candidate_names[signature] = str(row.get("candidate_name", "") or "")
            if _is_positive_label(row.get("label")) and candidate_url and candidate_url not in label_urls:
                label_urls.append(candidate_url)

        for label in _load_json(row.get("label_json"), []):
            if label not in labels:
                labels.append(label)

    return {
        "id": str(first_row.get("test_id", "")),
        "project": str(first_row.get("project", "")),
        "from_url": str(first_row.get("from_url", "")),
        "test_path": str(first_row.get("test_path", "")),
        "test_name": str(first_row.get("test_name", "")),
        "body": str(first_row.get("body", "")),
        "invocations": invocations,
        "signature": signatures,
        "candidate_urls": candidate_urls,
        "candidate_names": candidate_names,
        "label": labels,
        "label_urls": label_urls,
    }


def _load_json(value: object, default):
    if value is None:
        return default
    try:
        if pd.isna(value):
            return default
    except Exception:
        pass
    if isinstance(value, str) and not value.strip():
        return default
    return json.loads(str(value))


def _is_positive_label(value: object) -> bool:
    try:
        return int(value) > 0
    except (TypeError, ValueError):
        return False


def _clear_json_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.glob("*.json"):
        path.unlink()
