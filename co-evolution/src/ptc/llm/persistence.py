from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

from ptc.llm.models import LinkPrediction, PromptInput


RUN_FIELDNAMES = [
    "project",
    "name",
    "url",
    "prompt_text",
    "messages_json",
    "metadata_json",
    "output_raw",
    "output_json",
    "error",
    "created_at",
    "updated_at",
]


class CsvRunStore:
    def __init__(
        self,
        output_root: str | Path,
        input_kind: str,
        model_name_or_path: str,
        input_file_name: str,
        short_model_name: str | None = None,
    ):
        self.output_root = Path(output_root)
        self.input_kind = normalize_input_kind(input_kind)
        self.model_directory_name = model_directory_name(model_name_or_path, short_model_name)
        self.input_file_name = input_file_name

        self.kind_directory = self.output_root / self.input_kind
        self.model_directory = self.kind_directory / self.model_directory_name
        for directory in (self.output_root, self.kind_directory, self.model_directory):
            directory.mkdir(parents=True, exist_ok=True)

        self.runs_file = self.model_directory / input_file_name

    def load_predictions(self) -> dict[str, LinkPrediction]:
        if not self.runs_file.exists():
            return {}

        predictions: dict[str, LinkPrediction] = {}
        with self.runs_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_url = row.get("url", "")
                output_json = row.get("output_json", "")
                error = row.get("error", "")
                if not row_url or error or output_json in {"", "null"}:
                    continue

                try:
                    payload = json.loads(output_json)
                except json.JSONDecodeError:
                    continue

                methods_payload = payload.get("methods", [])
                if not isinstance(methods_payload, list):
                    continue

                selected_candidate_names = [
                    method_payload.get("name", "")
                    for method_payload in methods_payload
                    if isinstance(method_payload, dict) and method_payload.get("name", "")
                ]
                confidence_values = [
                    _coerce_float(method_payload.get("confidence"))
                    for method_payload in methods_payload
                    if isinstance(method_payload, dict)
                ]
                confidence_values = [value for value in confidence_values if value is not None]

                predictions[row_url] = LinkPrediction(
                    id=row_url,
                    fqs="",
                    name=row.get("name", ""),
                    url=row_url,
                    label="match" if selected_candidate_names else "none",
                    raw_output_text=row.get("output_raw", ""),
                    confidence=max(confidence_values) if confidence_values else None,
                    selected_candidate_ids=[f"c{index + 1}" for index, _ in enumerate(selected_candidate_names)],
                    selected_candidate_names=selected_candidate_names,
                    selected_candidate_sigs=[],
                    selected_candidate_urls=[],
                    rationale=str(payload.get("overall_rationale", "")).strip(),
                    metadata={"raw_json": payload},
                )
        return predictions

    def load_completed_example_ids(self) -> set[str]:
        return set(self.load_predictions().keys())

    def upsert_request(self, prompt_input: PromptInput, overwrite_existing: bool = False) -> None:
        timestamp = _timestamp_now()
        rows_by_url = self._load_rows_by_url()
        existing_row = rows_by_url.get(prompt_input.url, {})

        row = {
            "project": Path(self.input_file_name).stem,
            "name": prompt_input.name,
            "url": prompt_input.url,
            "prompt_text": prompt_input.prompt_text,
            "messages_json": json.dumps(
                [
                    {
                        "role": message.role,
                        "content": [
                            {"type": block.type, "text": block.text}
                            for block in message.content
                        ],
                    }
                    for message in prompt_input.messages
                ],
                ensure_ascii=True,
            ),
            "metadata_json": json.dumps(prompt_input.metadata, ensure_ascii=True),
            "output_raw": existing_row.get("output_raw", ""),
            "output_json": existing_row.get("output_json", "null") or "null",
            "error": existing_row.get("error", ""),
            "created_at": existing_row.get("created_at", "") or timestamp,
            "updated_at": timestamp,
        }
        if overwrite_existing:
            row["output_raw"] = ""
            row["output_json"] = "null"
            row["error"] = ""

        rows_by_url[prompt_input.url] = row
        self._write_rows(rows_by_url)

    def upsert_result(
        self,
        prompt_input: PromptInput,
        output_raw: str,
        output_json: dict | None,
        error: str = "",
    ) -> None:
        timestamp = _timestamp_now()
        rows_by_url = self._load_rows_by_url()
        existing_row = rows_by_url.get(prompt_input.url, {})
        rows_by_url[prompt_input.url] = {
            "project": existing_row.get("project", "") or Path(self.input_file_name).stem,
            "name": prompt_input.name,
            "url": prompt_input.url,
            "prompt_text": existing_row.get("prompt_text", prompt_input.prompt_text),
            "messages_json": existing_row.get("messages_json", ""),
            "metadata_json": existing_row.get("metadata_json", ""),
            "output_raw": output_raw,
            "output_json": json.dumps(output_json, ensure_ascii=True) if output_json is not None else "null",
            "error": error,
            "created_at": existing_row.get("created_at", "") or timestamp,
            "updated_at": timestamp,
        }
        self._write_rows(rows_by_url)

    def _load_rows_by_url(self) -> dict[str, dict[str, str]]:
        if not self.runs_file.exists():
            return {}

        rows_by_url: dict[str, dict[str, str]] = {}
        with self.runs_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_url = row.get("url", "")
                if row_url:
                    rows_by_url[row_url] = row
        return rows_by_url

    def _write_rows(self, rows_by_url: dict[str, dict[str, str]]) -> None:
        with self.runs_file.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=RUN_FIELDNAMES)
            writer.writeheader()
            for row in rows_by_url.values():
                writer.writerow({field: row.get(field, "") for field in RUN_FIELDNAMES})


def _coerce_float(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def model_directory_name(model_name_or_path: str, short_model_name: str | None = None) -> str:
    if short_model_name:
        return short_model_name
    normalized = model_name_or_path.replace("\\", "/").rstrip("/")
    return normalized.split("/")[-1] or "model"


def normalize_input_kind(value: str) -> str:
    if value == "fan-out":
        return "t2p"
    if value == "fan-in":
        return "p2t"
    return value


def _timestamp_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
