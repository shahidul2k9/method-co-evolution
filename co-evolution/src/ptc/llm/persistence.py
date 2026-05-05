from __future__ import annotations

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

        import pandas as pd

        predictions: dict[str, LinkPrediction] = {}
        run_df = pd.read_csv(self.runs_file)
        for row in run_df.to_dict(orient="records"):
            row_url = _nullable_value(row.get("url"))
            output_json = _nullable_value(row.get("output_json"))
            error = _nullable_value(row.get("error"))
            if not row_url or error is not None or output_json is None:
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
                name=_nullable_value(row.get("name")) or "",
                url=row_url,
                label="match" if selected_candidate_names else "none",
                raw_output_text=_nullable_value(row.get("output_raw")) or "",
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

    def load_error_example_ids(self) -> set[str]:
        if not self.runs_file.exists():
            return set()

        import pandas as pd

        run_df = pd.read_csv(self.runs_file)
        return {
            row_url
            for row in run_df.to_dict(orient="records")
            for row_url in [_nullable_value(row.get("url"))]
            if row_url and _nullable_value(row.get("error")) is not None
        }

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
            "output_raw": _nullable_value(existing_row.get("output_raw")),
            "output_json": _nullable_value(existing_row.get("output_json")),
            "error": _nullable_value(existing_row.get("error")) or "unknown",
            "created_at": existing_row.get("created_at", "") or timestamp,
            "updated_at": timestamp,
        }
        if overwrite_existing:
            row["output_raw"] = None
            row["output_json"] = None
            row["error"] = "unknown"

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
            "output_raw": output_raw or None,
            "output_json": json.dumps(output_json, ensure_ascii=True) if output_json is not None else None,
            "error": error or ("unknown" if output_json is None and not output_raw else None),
            "created_at": existing_row.get("created_at", "") or timestamp,
            "updated_at": timestamp,
        }
        self._write_rows(rows_by_url)

    def _load_rows_by_url(self) -> dict[str, dict[str, str]]:
        if not self.runs_file.exists():
            return {}

        import pandas as pd

        rows_by_url: dict[str, dict[str, str]] = {}
        run_df = pd.read_csv(self.runs_file)
        for row in run_df.to_dict(orient="records"):
            row_url = _nullable_value(row.get("url"))
            if row_url:
                rows_by_url[row_url] = row
        return rows_by_url

    def _write_rows(self, rows_by_url: dict[str, dict[str, str]]) -> None:
        import pandas as pd

        rows = [{field: row.get(field, "") for field in RUN_FIELDNAMES} for row in rows_by_url.values()]
        run_df = pd.DataFrame(rows, columns=RUN_FIELDNAMES)
        run_df.to_csv(self.runs_file, index=False)


def _coerce_float(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _nullable_value(value):
    try:
        import pandas as pd

        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str) and value.strip().lower() in {"", "null"}:
        return None
    return value


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
    if value == "callgraph":
        return "t2p"
    if value == "fanin":
        return "p2t"
    return value


def _timestamp_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()
