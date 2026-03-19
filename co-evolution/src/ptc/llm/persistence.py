from __future__ import annotations

import csv
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
        with self.predictions_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                row_id = row.get("llm_id", "")
                if not row_id or not row.get("llm_label", ""):
                    continue
                predictions[row_id] = LinkPrediction(
                    id=row_id,
                    fqs=row.get("llm_fqs", ""),
                    url=row.get("llm_url", ""),
                    label=row.get("llm_label", ""),
                    raw_output_text=row.get("llm_raw_output", ""),
                    confidence=_coerce_float(row.get("llm_confidence", "")),
                    selected_candidate_ids=_split_pipe(row.get("llm_predicted_candidate_ids", "")),
                    selected_candidate_confidences=_coerce_float_list(
                        row.get("llm_predicted_candidate_confidences", "")
                    ),
                    selected_candidate_sigs=_split_pipe(row.get("llm_predicted_sigs", "")),
                    selected_candidate_urls=_split_pipe(row.get("llm_predicted_urls", "")),
                    rationale=row.get("llm_rationale", ""),
                    metadata={},
                )
        return predictions

    def load_completed_example_ids(self) -> set[str]:
        return set(self.load_predictions().keys())

    def append_request(self, prompt_input: PromptInput) -> None:
        self._append_csv_row(
            self.requests_file,
            [
                "id",
                "fqs",
                "url",
                "prompt_text",
                "metadata_json",
            ],
            {
                "id": prompt_input.id,
                "fqs": prompt_input.fqs,
                "url": prompt_input.url,
                "prompt_text": prompt_input.prompt_text,
                "metadata_json": json.dumps(prompt_input.metadata, ensure_ascii=True),
            },
        )

    def append_failure(self, row_id: str, stage: str, error: str) -> None:
        self._append_csv_row(
            self.failures_file,
            ["id", "stage", "error"],
            {"id": row_id, "stage": stage, "error": error},
        )

    def write_prediction_snapshot(self, result_df) -> None:
        result_df.to_csv(self.predictions_file, index=False)

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


def _coerce_float_list(value: str) -> list[float | None]:
    if not value:
        return []
    try:
        raw_values = json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    if not isinstance(raw_values, list):
        return []
    return [_coerce_float("" if item is None else str(item)) for item in raw_values]


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
