from __future__ import annotations

import json
from pathlib import Path
import re

from ptc.llm.models import (
    LinkPrediction,
    PromptContentText,
    PromptInput,
    PromptMessage,
)
from ptc.llm.persistence import normalize_input_kind

_RESPONSE_FORMAT_PATH = (
    Path(__file__).resolve().parents[4] / "config" / "method_link_prediction_response_format.json"
)
with _RESPONSE_FORMAT_PATH.open("r", encoding="utf-8") as _handle:
    METHOD_LINK_PREDICTION_RESPONSE_FORMAT = json.load(_handle)


class MethodLinkingPromptFactory:
    def build_prompt(self, case_df, input_kind: str, prompt_format: str = "json") -> PromptInput:
        normalized_input_kind = normalize_input_kind(input_kind)
        source_prefix, candidate_prefix, _ = _layout(normalized_input_kind)
        row = case_df.iloc[0]
        fqs = _display_method_text(row, source_prefix)
        url = row[f"{source_prefix}_url"]

        candidate_lookup: dict[str, dict] = {}
        candidate_lines: list[str] = []
        seen_candidate_urls: set[str] = set()

        for row in case_df.itertuples(index=False):
            candidate_fqs = _display_method_text(row, candidate_prefix)
            candidate_sig = _row_value(row, f"{candidate_prefix}_sig")
            candidate_url = _row_value(row, f"{candidate_prefix}_url")

            if any([candidate_fqs, candidate_sig, candidate_url]):
                if not candidate_url or candidate_url not in seen_candidate_urls:
                    candidate_id = f"c{len(candidate_lookup) + 1}"
                    candidate_lookup[candidate_id] = {
                        "fqs": candidate_fqs,
                        "sig": candidate_sig or candidate_fqs,
                        "url": candidate_url,
                    }
                    candidate_lines.append(candidate_fqs)
                    if candidate_url:
                        seen_candidate_urls.add(candidate_url)

        messages = self._build_messages(
            input_kind=normalized_input_kind,
            fqs=fqs,
            candidate_lines=candidate_lines,
            prompt_format=prompt_format,
        )

        return PromptInput(
            id=url,
            fqs=fqs,
            url=url,
            prompt_text=render_messages_as_text(messages),
            messages=messages,
            candidate_lookup=candidate_lookup,
            metadata={
                "input_kind": normalized_input_kind,
                "candidate_count": len(candidate_lookup),
                "prompt_format": prompt_format,
            },
            response_format=METHOD_LINK_PREDICTION_RESPONSE_FORMAT if prompt_format == "json" else None,
        )

    @staticmethod
    def _build_messages(
        input_kind: str,
        fqs: str,
        candidate_lines: list[str],
        prompt_format: str,
    ) -> list[PromptMessage]:
        candidate_block = "\n".join(candidate_lines) if candidate_lines else "- None"

        if input_kind == "t2p":
            system_text = _t2p_system_text(prompt_format)
            user_text = (
                f"Fully qualified signature (FQS) of test method: {fqs}\n"
                "Candidate production methods called by the test method:\n"
                f"{candidate_block}\n"
                f"{_output_instruction(prompt_format)}"
            )
        elif input_kind == "p2t":
            system_text = _p2t_system_text(prompt_format)
            user_text = (
                f"Fully qualified signature (FQS) of production method: {fqs}\n"
                "Candidate test methods that call this production method:\n"
                f"{candidate_block}\n"
                f"{_output_instruction(prompt_format)}"
            )
        else:
            raise ValueError(f"Unsupported input_kind: {input_kind}")

        return [
            PromptMessage(role="system", content=[PromptContentText(type="text", text=system_text)]),
            PromptMessage(role="user", content=[PromptContentText(type="text", text=user_text)]),
        ]


def render_messages_as_text(messages: list[PromptMessage]) -> str:
    rendered_messages: list[str] = []
    for message in messages:
        content_text = "\n".join(block.text for block in message.content if block.type == "text").strip()
        rendered_messages.append(f"{message.role.upper()}:\n{content_text}")
    return "\n\n".join(rendered_messages).strip()


def _t2p_system_text(prompt_format: str) -> str:
    return (
        "You are an expert in identifying which production method is being tested by a given test method in a Java codebase. "
        "You will be given a test method and a list of candidate production methods that are called within the test method. "
        "Your task is to choose exactly one candidate production method from the list, or NONE if no candidate is under test. "
        f"{_return_requirement(prompt_format)}"
    )


def _p2t_system_text(prompt_format: str) -> str:
    return (
        "You are an expert in identifying which test method exercises a given production method in a Java codebase. "
        "You will be given a production method and a list of candidate test methods that call it. "
        "Your task is to choose exactly one candidate test method from the list, or NONE if no candidate is the right answer. "
        f"{_return_requirement(prompt_format)}"
    )


def _output_instruction(prompt_format: str) -> str:
    if prompt_format == "json":
        return (
            "Return valid JSON only with the answer field set to the exact candidate FQS from the list above or NONE. "
            "Do not repeat the prompt. Do not use markdown or code fences."
        )
    return "Return exactly this format:\nAnswer: <exact candidate FQS from the list above or NONE>"


def _return_requirement(prompt_format: str) -> str:
    if prompt_format == "json":
        return "Return valid JSON only that follows the provided schema. Use the exact candidate FQS from the list or NONE."
    return (
        "Return only the requested answer line. Start immediately with Answer:. "
        "Do not include analysis, chain-of-thought, restatements, bullet points, markdown, or any extra text. "
        "Use the exact candidate FQS from the list or NONE."
    )


class JsonPredictionParser:
    parser_name = "json_prediction_parser"

    def parse(self, prompt_input: PromptInput, output_text: str) -> LinkPrediction:
        payload = self._extract_or_fallback_payload(output_text)
        candidate_ids = self._resolve_candidate_ids(prompt_input, payload)
        selected_candidate_fqs = ""
        selected_candidate_sig = ""
        selected_candidate_url = ""

        if candidate_ids:
            candidate = prompt_input.candidate_lookup.get(candidate_ids[0])
            if candidate is not None:
                selected_candidate_fqs = candidate["fqs"]
                selected_candidate_sig = candidate["sig"]
                selected_candidate_url = candidate["url"]

        return LinkPrediction(
            id=prompt_input.id,
            fqs=prompt_input.fqs,
            url=prompt_input.url,
            label="match" if candidate_ids else "none",
            raw_output_text=output_text,
            confidence=None,
            selected_candidate_ids=candidate_ids,
            selected_candidate_fqs=selected_candidate_fqs,
            selected_candidate_sig=selected_candidate_sig,
            selected_candidate_url=selected_candidate_url,
            rationale=str(payload.get("rationale", "")).strip(),
            metadata={"raw_json": payload},
        )

    @classmethod
    def _extract_or_fallback_payload(cls, output_text: str) -> dict:
        try:
            return cls._extract_json(output_text)
        except ValueError:
            conventional_payload = cls._extract_conventional_payload(output_text)
            if conventional_payload is not None:
                return conventional_payload
            stripped_output = output_text.strip()
            return {
                "answer": "NONE",
                "rationale": (
                    "Model did not return a usable answer."
                    if stripped_output
                    else "Model returned an empty response."
                ),
            }

    @staticmethod
    def _extract_conventional_payload(output_text: str) -> dict | None:
        stripped_output = output_text.strip()
        if not stripped_output:
            return None
        answer_matches = re.findall(r"(?is)(?:^|[\s\"'])answer\s*:\s*([^\n\r\"']+)", stripped_output)
        if not answer_matches:
            return None
        for raw_answer in reversed(answer_matches):
            cleaned_answer = JsonPredictionParser._clean_answer_value(raw_answer)
            if cleaned_answer:
                return {"answer": cleaned_answer}
        return None

    @staticmethod
    def _extract_json(output_text: str) -> dict:
        decoder = json.JSONDecoder()
        stripped_output = output_text.strip()
        standalone_payload = JsonPredictionParser._try_decode_standalone_json(decoder, stripped_output)
        normalized_payload = JsonPredictionParser._normalize_payload_shape(standalone_payload)
        if normalized_payload is not None and JsonPredictionParser._looks_like_prediction_payload(normalized_payload):
            return normalized_payload

        for start_index, character in enumerate(output_text):
            if character in {"{", "\""}:
                try:
                    raw_payload, _ = decoder.raw_decode(output_text[start_index:])
                except json.JSONDecodeError:
                    raw_payload = None
                if raw_payload is not None:
                    payload = JsonPredictionParser._normalize_payload_shape(raw_payload)
                    if payload is not None and JsonPredictionParser._looks_like_prediction_payload(payload):
                        return payload
        raise ValueError(f"Could not find JSON object in model output: {output_text}")

    @staticmethod
    def _try_decode_standalone_json(decoder: json.JSONDecoder, output_text: str):
        if not output_text:
            return None
        try:
            payload, end_index = decoder.raw_decode(output_text)
        except json.JSONDecodeError:
            return None
        if output_text[end_index:].strip():
            return None
        return payload

    @staticmethod
    def _looks_like_prediction_payload(payload: dict) -> bool:
        if "answer" not in payload:
            return False
        return bool(JsonPredictionParser._clean_answer_value(payload.get("answer", "")))

    @staticmethod
    def _normalize_payload_shape(raw_payload) -> dict | None:
        if isinstance(raw_payload, dict):
            return raw_payload
        if isinstance(raw_payload, str):
            return {"answer": raw_payload}
        return None

    @classmethod
    def _resolve_candidate_ids(cls, prompt_input: PromptInput, payload: dict) -> list[str]:
        answer = cls._clean_answer_value(payload.get("answer", ""))
        if answer.upper() in {"", "NONE", "[]"}:
            return []

        normalized_answer = cls._normalize_method_text(answer)
        normalized_lookup = {
            candidate_id: {
                cls._normalize_method_text(candidate["fqs"]),
                cls._normalize_method_text(candidate["sig"]),
            }
            for candidate_id, candidate in prompt_input.candidate_lookup.items()
        }

        for candidate_id, candidate_texts in normalized_lookup.items():
            if normalized_answer in candidate_texts:
                return [candidate_id]

        prefix_matches = [
            candidate_id
            for candidate_id, candidate_texts in normalized_lookup.items()
            if any(
                candidate_text.startswith(normalized_answer)
                or normalized_answer.startswith(candidate_text)
                for candidate_text in candidate_texts
                if candidate_text
            )
        ]
        if len(prefix_matches) == 1:
            return [prefix_matches[0]]
        return []

    @staticmethod
    def _normalize_method_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value).strip()).lower()

    @staticmethod
    def _clean_answer_value(value: str) -> str:
        cleaned = str(value).strip().strip("`'\"")
        cleaned = re.split(r"(?i)\bassistantfinalanswer\s*:", cleaned, maxsplit=1)[0].strip()
        cleaned = re.sub(r"(?is)^answer\s*:\s*", "", cleaned).strip()
        return re.sub(r"[\s\.;:,]+$", "", cleaned)


def _layout(input_kind: str) -> tuple[str, str, str]:
    if input_kind in {"fan-out", "t2p"}:
        return "from", "to", "from_url"
    if input_kind in {"fan-in", "p2t"}:
        return "to", "from", "to_url"
    raise ValueError(f"Unsupported input_kind: {input_kind}")


def _display_method_text(row, prefix: str) -> str:
    for field_name in (
        f"{prefix}_fqs_alt",
        f"{prefix}_fqs",
        f"{prefix}_sig",
        f"{prefix}_fqn",
        f"{prefix}_name",
    ):
        value = _row_value(row, field_name)
        if value:
            return str(value)
    return ""


def _row_value(row, field_name: str) -> str:
    if hasattr(row, "get"):
        return row.get(field_name, "")
    return getattr(row, field_name, "")
