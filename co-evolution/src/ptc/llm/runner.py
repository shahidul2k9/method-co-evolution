from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import islice
from pathlib import Path
from typing import TYPE_CHECKING

from ptc.llm.models import GenerationConfig, LinkPrediction, PromptInput, ProviderGeneration
from ptc.llm.persistence import CsvRunStore, normalize_input_kind

if TYPE_CHECKING:
    import pandas as pd


class ModelProvider(ABC):
    @abstractmethod
    def prompt_mode(self) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_batch(
        self,
        prompts: list[PromptInput],
        generation_config: GenerationConfig,
    ) -> list[ProviderGeneration]:
        raise NotImplementedError


class DataFrameMethodLinker:
    def __init__(
        self,
        provider: ModelProvider,
        prompt_factory,
        parser,
        run_store: CsvRunStore | None = None,
        batch_size: int = 4,
        resume_mode: str = "none",
        prompt_format: str = "auto",
    ):
        self.provider = provider
        self.prompt_factory = prompt_factory
        self.parser = parser
        self.run_store = run_store
        self.batch_size = batch_size
        self.resume_mode = resume_mode
        self.prompt_format = prompt_format

    def link_dataframe(
        self,
        edge_df: "pd.DataFrame",
        input_kind: str,
        generation_config: GenerationConfig,
    ):
        self._require_pandas()
        normalized_input_kind = normalize_input_kind(input_kind)
        working_df = self._normalize_dataframe(edge_df.copy())
        source_prefix, candidate_prefix, group_column = _layout(normalized_input_kind)
        working_df["llm_id"] = working_df[group_column]
        grouped_cases = [case_df for _, case_df in working_df.groupby(group_column, sort=False)]
        resume_all = self.resume_mode == "all"
        resume_errors = self.resume_mode == "error"

        completed_predictions = (
            self.run_store.load_predictions()
            if self.run_store and (resume_all or resume_errors)
            else {}
        )
        error_example_ids = (
            self.run_store.load_error_example_ids()
            if self.run_store and resume_errors
            else set()
        )
        pending_cases = []
        for case_df in grouped_cases:
            row_id = case_df.iloc[0][group_column]
            if resume_errors:
                if row_id in error_example_ids:
                    pending_cases.append(case_df)
            elif row_id not in completed_predictions:
                pending_cases.append(case_df)

        for batch_cases in _chunked(pending_cases, self.batch_size):
            prompts: list[PromptInput] = []
            for case_df in batch_cases:
                prompt_format = self.provider.prompt_mode() if self.prompt_format == "auto" else self.prompt_format
                prompt = self.prompt_factory.build_prompt(
                    case_df,
                    normalized_input_kind,
                    prompt_format=prompt_format,
                )
                prompt.metadata["batch_size"] = self.batch_size
                prompt.metadata["max_new_tokens"] = generation_config.max_new_tokens
                if prompt.candidate_lookup:
                    prompts.append(prompt)
                    if self.run_store:
                        self.run_store.upsert_request(
                            prompt,
                            overwrite_existing=(self.resume_mode == "none") or resume_errors,
                        )
                    continue

                prediction = LinkPrediction(
                    id=prompt.id,
                    fqs=prompt.fqs,
                    name=prompt.name,
                    url=prompt.url,
                    label="none",
                    raw_output_text="",
                    confidence=1.0,
                    selected_candidate_ids=[],
                    selected_candidate_names=[],
                    selected_candidate_sigs=[],
                    selected_candidate_urls=[],
                    rationale="No candidate methods were present in this grouped case.",
                    metadata={"generated_without_model": True},
                )
                completed_predictions[prompt.id] = prediction
                if self.run_store:
                    self.run_store.upsert_request(
                        prompt,
                        overwrite_existing=(self.resume_mode == "none") or resume_errors,
                    )
                    self.run_store.upsert_result(
                        prompt_input=prompt,
                        output_raw="",
                        output_json={"methods": [], "overall_rationale": prediction.rationale},
                        error="",
                    )

            if not prompts:
                continue

            try:
                outputs = self.provider.generate_batch(prompts, generation_config)
            except Exception as exc:
                if self.run_store:
                    for prompt in prompts:
                        self.run_store.upsert_result(
                            prompt_input=prompt,
                            output_raw="",
                            output_json=None,
                            error=f"provider: {exc}",
                        )
                continue

            outputs_by_id = {output.id: output for output in outputs}
            for prompt in prompts:
                output = outputs_by_id.get(prompt.id)
                if output is None:
                    if self.run_store:
                        self.run_store.upsert_result(
                            prompt_input=prompt,
                            output_raw="",
                            output_json=None,
                            error="provider: Missing provider output",
                        )
                    continue

                extracted_payload = self.parser.extract_payload_or_none(output.output_text)
                try:
                    prediction = self.parser.parse(prompt, output.output_text)
                except Exception as exc:
                    if self.run_store:
                        self.run_store.upsert_result(
                            prompt_input=prompt,
                            output_raw=output.output_text,
                            output_json=extracted_payload,
                            error=f"parser: {exc}",
                        )
                    continue

                completed_predictions[prompt.id] = prediction
                if self.run_store:
                    self.run_store.upsert_result(
                        prompt_input=prompt,
                        output_raw=output.output_text,
                        output_json=prediction.metadata.get("raw_json"),
                        error="",
                    )

        return self._merge_predictions_into_dataframe(
            working_df=working_df,
            completed_predictions=completed_predictions,
            source_prefix=source_prefix,
            candidate_prefix=candidate_prefix,
        )

    @staticmethod
    def _normalize_dataframe(edge_df):
        column_aliases = {
            "project": ["project"],
            "from_name": ["from_name", "from_fqs_alt", "from_fqs", "from_sig", "from_fqn"],
            "to_name": ["to_name", "to_fqs_alt", "to_fqs", "to_sig", "to_fqn"],
            "from_fqs": ["from_fqs", "from_fqn", "from_name"],
            "to_fqs": ["to_fqs", "to_fqn", "to_name"],
            "from_fqs_alt": ["from_fqs_alt", "from_fqs", "from_sig", "from_fqn", "from_name"],
            "to_fqs_alt": ["to_fqs_alt", "to_fqs", "to_sig", "to_fqn", "to_name"],
            "from_sig": ["from_sig", "from_fqs", "from_fqs_alt", "from_fqn"],
            "to_sig": ["to_sig", "to_fqs", "to_fqs_alt", "to_fqn"],
        }
        for canonical_column, aliases in column_aliases.items():
            if canonical_column in edge_df.columns:
                continue
            for alias in aliases:
                if alias in edge_df.columns:
                    edge_df[canonical_column] = edge_df[alias]
                    break
            else:
                edge_df[canonical_column] = ""

        required_columns = ["from_url", "to_url", "from_file", "to_file", "from_fqs", "to_fqs", "from_sig", "to_sig"]
        missing = [column for column in required_columns if column not in edge_df.columns]
        if missing:
            raise ValueError(f"Input dataframe is missing required columns: {missing}")

        return edge_df.fillna("")

    @staticmethod
    def _predictions_to_dataframe(predictions_by_id):
        import pandas as pd

        rows = []
        for prediction in predictions_by_id.values():
            rows.append(
                {
                    "llm_id": prediction.id,
                    "llm_label": prediction.label,
                    "llm_names": "|".join(prediction.selected_candidate_names),
                    "llm_output": prediction.raw_output_text,
                    "llm_predicted_sigs": "|".join(prediction.selected_candidate_sigs),
                    "llm_predicted_urls": "|".join(prediction.selected_candidate_urls),
                }
            )
        return pd.DataFrame(rows)

    def _merge_predictions_into_dataframe(
        self,
        working_df,
        completed_predictions: dict[str, LinkPrediction],
        source_prefix: str,
        candidate_prefix: str,
    ):
        prediction_df = self._predictions_to_dataframe(completed_predictions)
        if prediction_df.empty:
            merged_df = working_df.copy()
            for column in [
                "llm_label",
                "llm_names",
                "llm_output",
                "llm_predicted_sigs",
                "llm_predicted_urls",
            ]:
                merged_df[column] = ""
        else:
            merged_df = working_df.merge(
                prediction_df,
                on="llm_id",
                how="left",
            )

        row_candidate_sig_column = f"{candidate_prefix}_sig"
        row_candidate_name_column = f"{candidate_prefix}_name"
        row_candidate_url_column = f"{candidate_prefix}_url"
        merged_df["llm_predicted_match"] = (
            (
                (merged_df[row_candidate_sig_column] != "")
                | (merged_df[row_candidate_name_column] != "")
            )
            & (
                merged_df.apply(
                    lambda row: row[row_candidate_name_column] in _split_pipe_value(row.get("llm_names", ""))
                    or row[row_candidate_sig_column] in _split_pipe_value(row["llm_predicted_sigs"])
                    or row[row_candidate_url_column] in _split_pipe_value(row["llm_predicted_urls"]),
                    axis=1,
                )
            )
        ).astype(int)
        merged_df["llm_pred"] = merged_df["llm_predicted_match"].astype(int)
        if "project" in merged_df.columns:
            merged_df["project"] = merged_df["project"].replace("", Path(self.run_store.input_file_name).stem if self.run_store else "")
        elif self.run_store:
            merged_df["project"] = Path(self.run_store.input_file_name).stem
        return merged_df

    @staticmethod
    def _require_pandas() -> None:
        try:
            import pandas  # noqa: F401
        except ImportError as exc:
            raise ImportError("pandas is required for dataframe-based LLM linking.") from exc


def _layout(input_kind: str) -> tuple[str, str, str]:
    if input_kind in {"fan-out", "t2p"}:
        return "from", "to", "from_url"
    if input_kind in {"fan-in", "p2t"}:
        return "to", "from", "to_url"
    raise ValueError(f"Unsupported input_kind: {input_kind}")


def _chunked(items: list, batch_size: int):
    iterator = iter(items)
    while True:
        chunk = list(islice(iterator, batch_size))
        if not chunk:
            return
        yield chunk


def _split_pipe_value(value) -> list[str]:
    if value is None or value == "":
        return []
    return [item for item in str(value).split("|") if item]
