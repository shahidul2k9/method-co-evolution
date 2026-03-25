from __future__ import annotations

import csv
import datetime
import json
from pathlib import Path

from ptc.llm.models import LinkPrediction, PromptInput


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
        self.prediction_directory = self.model_directory / "prediction"
        self.request_directory = self.model_directory / "request"
        self.error_directory = self.model_directory / "error"

        for directory in (
            self.output_root,
            self.kind_directory,
            self.model_directory,
            self.prediction_directory,
            self.request_directory,
            self.error_directory,
        ):
            directory.mkdir(parents=True, exist_ok=True)

        self.predictions_file = self.prediction_directory / input_file_name
        self.requests_file = self.request_directory / input_file_name
        self.failures_file = self.error_directory / input_file_name

    def load_predictions(self) -> dict[str, LinkPrediction]:
        if not self.predictions_file.exists():
            return {}

        predictions: dict[str, LinkPrediction] = {}
        source_prefix = "from" if self.input_kind == "t2p" else "to"
        with self.predictions_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_id = row.get("llm_id", "")
                if not row_id:
                    continue
                if "llm_output" in row:
                    selected_candidate_names = _split_pipe(row.get("llm_names", ""))
                    llm_pred = _coerce_int(row.get("llm_pred", ""))
                    predictions[row_id] = LinkPrediction(
                        id=row_id,
                        fqs=row.get(f"{source_prefix}_fqs", ""),
                        name=row.get(f"{source_prefix}_name", ""),
                        url=row.get(f"{source_prefix}_url", ""),
                        label="match" if llm_pred == 1 and selected_candidate_names else "none",
                        raw_output_text=row.get("llm_output", ""),
                        confidence=None,
                        selected_candidate_ids=[f"c{index + 1}" for index, _ in enumerate(selected_candidate_names)],
                        selected_candidate_names=selected_candidate_names,
                        selected_candidate_sigs=[],
                        selected_candidate_urls=[],
                        rationale="",
                        metadata={},
                    )
                elif row.get("llm_label", ""):
                    predictions[row_id] = LinkPrediction(
                        id=row_id,
                        fqs=row.get(f"{source_prefix}_fqs", ""),
                        name=row.get(f"{source_prefix}_name", ""),
                        url=row.get("llm_url", ""),
                        label=row.get("llm_label", ""),
                        raw_output_text=row.get("llm_raw_output", ""),
                        confidence=_coerce_float(row.get("llm_confidence", "")),
                        selected_candidate_ids=_split_pipe(row.get("llm_predicted_candidate_ids", "")),
                        selected_candidate_names=_split_pipe(row.get("llm_predicted_names", "")),
                        selected_candidate_sigs=_split_pipe(row.get("llm_predicted_sigs", "")),
                        selected_candidate_urls=_split_pipe(row.get("llm_predicted_urls", "")),
                        rationale=row.get("llm_rationale", ""),
                        metadata={},
                    )
        return predictions

    def load_completed_example_ids(self) -> set[str]:
        return set(self.load_predictions().keys())

    def append_request(self, prompt_input: PromptInput) -> None:
        timestamp = _timestamp_now()
        self._append_csv_row(
            self.requests_file,
            [
                "id",
                "fqs",
                "url",
                "prompt_text",
                "messages_json",
                "metadata_json",
                "created_at",
                "updated_at",
            ],
            {
                "id": prompt_input.id,
                "fqs": prompt_input.fqs,
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
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )

    def append_failure(self, row_id: str, stage: str, error: str) -> None:
        timestamp = _timestamp_now()
        self._append_csv_row(
            self.failures_file,
            ["id", "stage", "error", "created_at", "updated_at"],
            {
                "id": row_id,
                "stage": stage,
                "error": error,
                "created_at": timestamp,
                "updated_at": timestamp,
            },
        )

    def write_prediction_snapshot(self, result_df) -> None:
        snapshot_df = result_df.copy()
        timestamp = _timestamp_now()
        existing_timestamps = self._load_prediction_timestamps()
        minimal_columns = [
            "project",
            "from_name",
            "to_name",
            "from_url",
            "to_url",
            "from_fqs",
            "to_fqs",
            "llm_id",
            "llm_pred",
            "llm_names",
            "llm_output",
            "created_at",
            "updated_at",
        ]
        defaults = {
            "project": Path(self.input_file_name).stem,
            "from_name": "",
            "to_name": "",
            "from_url": "",
            "to_url": "",
            "from_fqs": "",
            "to_fqs": "",
            "llm_id": "",
            "llm_pred": 0,
            "llm_names": "",
            "llm_output": "",
            "created_at": "",
            "updated_at": "",
        }
        for column_name, default_value in defaults.items():
            if column_name not in snapshot_df.columns:
                snapshot_df[column_name] = default_value
        snapshot_df.loc[:, "project"] = snapshot_df["project"].replace("", Path(self.input_file_name).stem)
        snapshot_df.loc[:, "created_at"] = [
            (existing_timestamps.get(str(row_id), {}).get("created_at", "") or timestamp)
            if str(row_id)
            else timestamp
            for row_id in snapshot_df["llm_id"].tolist()
        ]
        snapshot_df.loc[:, "updated_at"] = timestamp
        snapshot_df.loc[:, minimal_columns].to_csv(self.predictions_file, index=False)

    def _load_prediction_timestamps(self) -> dict[str, dict[str, str]]:
        if not self.predictions_file.exists():
            return {}

        timestamps_by_id: dict[str, dict[str, str]] = {}
        with self.predictions_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_id = row.get("llm_id", "")
                if not row_id:
                    continue
                timestamps_by_id[row_id] = {
                    "created_at": row.get("created_at", "") or "",
                    "updated_at": row.get("updated_at", "") or "",
                }
        return timestamps_by_id

    @staticmethod
    def _append_csv_row(file_path: Path, fieldnames: list[str], row: dict[str, object]) -> None:
        write_header = not file_path.exists()
        with file_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            if write_header:
                writer.writeheader()
            writer.writerow(row)


def _split_pipe(value: str) -> list[str]:
    if not value:
        return []
    return [item for item in value.split("|") if item]


def _coerce_float(value: str) -> float | None:
    if value == "":
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _coerce_int(value: str) -> int | None:
    if value == "":
        return None
    try:
        return int(value)
    except ValueError:
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
