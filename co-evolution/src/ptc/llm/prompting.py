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
    def __init__(self, method_code_lookup: dict[str, dict[str, str]] | None = None):
        self.method_code_lookup = method_code_lookup or {}

    def build_prompt(self, case_df, input_kind: str, prompt_format: str = "json") -> PromptInput:
        normalized_input_kind = normalize_input_kind(input_kind)
        source_prefix, candidate_prefix, _ = _layout(normalized_input_kind)
        row = case_df.iloc[0]
        fqs = _display_method_text(row, source_prefix)
        name = _row_value(row, f"{source_prefix}_name") or fqs
        url = row[f"{source_prefix}_url"]
        code = self._lookup_method_code(url, fqs)

        candidate_lookup: dict[str, dict] = {}
        candidate_lines: list[str] = []
        seen_candidate_urls: set[str] = set()

        for row in case_df.itertuples(index=False):
            candidate_name = _row_value(row, f"{candidate_prefix}_name") or _display_method_text(row, candidate_prefix)
            candidate_fqs = _display_method_text(row, candidate_prefix)
            candidate_sig = _row_value(row, f"{candidate_prefix}_sig")
            candidate_url = _row_value(row, f"{candidate_prefix}_url")

            if any([candidate_name, candidate_fqs, candidate_sig, candidate_url]):
                if not candidate_url or candidate_url not in seen_candidate_urls:
                    candidate_id = f"c{len(candidate_lookup) + 1}"
                    candidate_lookup[candidate_id] = {
                        "name": candidate_name,
                        "fqs": candidate_fqs,
                        "sig": candidate_sig or candidate_fqs,
                        "url": candidate_url,
                    }
                    candidate_lines.append(candidate_name)
                    if candidate_url:
                        seen_candidate_urls.add(candidate_url)

        messages = self._build_messages(
            input_kind=normalized_input_kind,
            code=code,
            candidate_lines=candidate_lines,
            prompt_format=prompt_format,
        )

        return PromptInput(
            id=url,
            fqs=fqs,
            name=name,
            code=code,
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
        code: str,
        candidate_lines: list[str],
        prompt_format: str,
    ) -> list[PromptMessage]:
        candidate_block = "\n".join(candidate_lines) if candidate_lines else "- None"

        if input_kind == "t2p":
            system_text = _t2p_system_text(prompt_format)
            user_text = (
                "Test method code:\n"
                f"{code}\n"
                "Candidate production method names called by the test method:\n"
                f"{candidate_block}\n"
                f"{_output_instruction(prompt_format)}"
            )
        elif input_kind == "p2t":
            system_text = _p2t_system_text(prompt_format)
            user_text = (
                "Production method code:\n"
                f"{code}\n"
                "Candidate test method names that call the production method:\n"
                f"{candidate_block}\n"
                f"{_output_instruction(prompt_format)}"
            )
        else:
            raise ValueError(f"Unsupported input_kind: {input_kind}")

        return [
            PromptMessage(role="system", content=[PromptContentText(type="text", text=system_text)]),
            PromptMessage(role="user", content=[PromptContentText(type="text", text=user_text)]),
        ]

    def _lookup_method_code(self, url: str, fallback_text: str) -> str:
        method_code = self.method_code_lookup.get(url, {}).get("code", "")
        if method_code:
            return method_code
        return fallback_text


def render_messages_as_text(messages: list[PromptMessage]) -> str:
    rendered_messages: list[str] = []
    for message in messages:
        content_text = "\n".join(block.text for block in message.content if block.type == "text").strip()
        rendered_messages.append(f"{message.role.upper()}:\n{content_text}")
    return "\n\n".join(rendered_messages).strip()


def _t2p_system_text(prompt_format: str) -> str:
    return (
        "You are an expert in identifying which production method is being tested by a given test method in a Java codebase. "
        "You will be given the code of a test method and a list of candidate production method names called within the test method. "
        "Your task is to choose zero, one, or multiple candidate production method names from the list. "
        f"{_return_requirement(prompt_format)}"
    )


def _p2t_system_text(prompt_format: str) -> str:
    return (
        "You are an expert in identifying which test method exercises a given production method in a Java codebase. "
        "You will be given the code of a production method and a list of candidate test method names that call it. "
        "Your task is to choose zero, one, or multiple candidate test method names from the list. "
        f"{_return_requirement(prompt_format)}"
    )


def _output_instruction(prompt_format: str) -> str:
    if prompt_format == "json":
        return (
            "Return valid JSON only. Use the exact candidate method names from the list above. "
            'Expected JSON shape: {"methods":[{"name":"<candidate method name>","confidence":0.0,"rationale":"<short explanation>"}],"overall_rationale":"<short overall explanation>"}. '
            "Do not repeat the prompt. Do not use markdown or code fences."
        )
    return (
        "Return exactly this format:\n"
        "METHOD: <exact candidate method name>\n"
        "CONFIDENCE: <confidence between 0 and 1>\n"
        "RATIONALE: <short explanation>\n"
        "Repeat the METHOD/CONFIDENCE/RATIONALE block for each selected method.\n"
        "OVERALL_RATIONALE: <short overall explanation>"
    )


def _return_requirement(prompt_format: str) -> str:
    if prompt_format == "json":
        return "Return valid JSON only that follows the provided schema and uses only exact candidate method names from the list."
    return (
        "Return only the requested METHOD/CONFIDENCE/RATIONALE blocks plus one OVERALL_RATIONALE line. "
        "Do not include analysis, chain-of-thought, restatements, bullet points, markdown, or any extra text. "
    )


class JsonPredictionParser:
    parser_name = "json_prediction_parser"

    def parse(self, prompt_input: PromptInput, output_text: str) -> LinkPrediction:
        payload = self.extract_payload_or_none(output_text)
        if payload is None:
            raise ValueError("Model did not return a usable JSON or text payload.")
        candidate_ids = self._resolve_candidate_ids(prompt_input, payload)
        selected_candidate_names: list[str] = []
        selected_candidate_sigs: list[str] = []
        selected_candidate_urls: list[str] = []

        for candidate_id in candidate_ids:
            candidate = prompt_input.candidate_lookup.get(candidate_id)
            if candidate is not None:
                selected_candidate_names.append(candidate["name"])
                selected_candidate_sigs.append(candidate["sig"])
                selected_candidate_urls.append(candidate["url"])

        confidence_values = [
            _coerce_float(method_payload.get("confidence"))
            for method_payload in payload.get("methods", [])
            if isinstance(method_payload, dict)
        ]
        confidence_values = [value for value in confidence_values if value is not None]

        return LinkPrediction(
            id=prompt_input.id,
            fqs=prompt_input.fqs,
            name=prompt_input.name,
            url=prompt_input.url,
            label="match" if candidate_ids else "none",
            raw_output_text=output_text,
            confidence=max(confidence_values) if confidence_values else None,
            selected_candidate_ids=candidate_ids,
            selected_candidate_names=selected_candidate_names,
            selected_candidate_sigs=selected_candidate_sigs,
            selected_candidate_urls=selected_candidate_urls,
            rationale=str(payload.get("overall_rationale", "")).strip(),
            metadata={"raw_json": payload},
        )

    @classmethod
    def extract_payload_or_none(cls, output_text: str) -> dict | None:
        try:
            return cls._extract_json(output_text)
        except ValueError:
            conventional_payload = cls._extract_conventional_payload(output_text)
            return conventional_payload

    @staticmethod
    def _extract_conventional_payload(output_text: str) -> dict | None:
        stripped_output = output_text.strip()
        if not stripped_output:
            return None
        method_blocks = JsonPredictionParser._extract_method_blocks(stripped_output)
        overall_rationale_match = re.search(r"(?im)^\s*overall_rationale\s*:\s*(.+?)\s*$", stripped_output)
        if not method_blocks and overall_rationale_match is None:
            return None
        return {
            "methods": method_blocks,
            "overall_rationale": (
                overall_rationale_match.group(1).strip()
                if overall_rationale_match is not None
                else ""
            ),
        }

    @staticmethod
    def _extract_json(output_text: str) -> dict:
        decoder = json.JSONDecoder()
        stripped_output = output_text.strip()
        standalone_payload = JsonPredictionParser._try_decode_standalone_json(decoder, stripped_output)
        normalized_payload = JsonPredictionParser._normalize_payload_shape(standalone_payload)
        if normalized_payload is not None and JsonPredictionParser._looks_like_prediction_payload(normalized_payload):
            return normalized_payload

        valid_payloads: list[dict] = []
        for start_index, character in enumerate(output_text):
            if character in {"{", "\""}:
                try:
                    raw_payload, _ = decoder.raw_decode(output_text[start_index:])
                except json.JSONDecodeError:
                    raw_payload = None
                if raw_payload is not None:
                    payload = JsonPredictionParser._normalize_payload_shape(raw_payload)
                    if payload is not None and JsonPredictionParser._looks_like_prediction_payload(payload):
                        valid_payloads.append(payload)
        if valid_payloads:
            return valid_payloads[-1]
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
        if "methods" not in payload:
            return False
        return isinstance(payload.get("methods"), list)

    @staticmethod
    def _normalize_payload_shape(raw_payload) -> dict | None:
        if isinstance(raw_payload, dict):
            return raw_payload
        return None

    @classmethod
    def _resolve_candidate_ids(cls, prompt_input: PromptInput, payload: dict) -> list[str]:
        methods_payload = payload.get("methods", [])
        if not isinstance(methods_payload, list):
            return []

        normalized_lookup = {
            candidate_id: {
                cls._normalize_method_text(candidate["name"]),
                cls._normalize_method_text(candidate["sig"]),
            }
            for candidate_id, candidate in prompt_input.candidate_lookup.items()
        }

        candidate_ids: list[str] = []
        for method_payload in methods_payload:
            if not isinstance(method_payload, dict):
                continue
            answer = cls._clean_answer_value(method_payload.get("name", ""))
            if not answer:
                continue

            normalized_answer = cls._normalize_method_text(answer)
            matched_candidate_id = ""
            for candidate_id, candidate_texts in normalized_lookup.items():
                if normalized_answer in candidate_texts:
                    matched_candidate_id = candidate_id
                    break

            if not matched_candidate_id:
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
                    matched_candidate_id = prefix_matches[0]

            if matched_candidate_id and matched_candidate_id not in candidate_ids:
                candidate_ids.append(matched_candidate_id)
        return candidate_ids

    @classmethod
    def _extract_method_blocks(cls, output_text: str) -> list[dict]:
        lines = [line.strip() for line in output_text.splitlines() if line.strip()]
        methods: list[dict] = []
        current_method: dict | None = None

        for line in lines:
            inline_method_match = re.search(r"(?i)\bmethod\s*:", line)
            if inline_method_match is not None and not re.match(r"(?i)^method\s*:", line):
                line = line[inline_method_match.start():]
            method_match = re.match(r"(?i)^method\s*:\s*(.+)$", line)
            if method_match:
                method_name = cls._clean_answer_value(method_match.group(1))
                if method_name:
                    if current_method is not None:
                        methods.append(current_method)
                    current_method = {"name": method_name}
                continue

            if current_method is None:
                continue

            confidence_match = re.match(r"(?i)^confidence\s*:\s*(.+)$", line)
            if confidence_match:
                current_method["confidence"] = confidence_match.group(1).strip()
                continue

            rationale_match = re.match(r"(?i)^rationale\s*:\s*(.+)$", line)
            if rationale_match:
                current_method["rationale"] = rationale_match.group(1).strip()

        if current_method is not None:
            methods.append(current_method)

        normalized_methods: list[dict] = []
        for method_payload in methods:
            normalized_methods.append(
                {
                    "name": method_payload.get("name", ""),
                    "confidence": _coerce_float(method_payload.get("confidence")) or 0.0,
                    "rationale": method_payload.get("rationale", ""),
                }
            )
        return normalized_methods

    @staticmethod
    def _normalize_method_text(value: str) -> str:
        return re.sub(r"\s+", " ", str(value).strip()).lower()

    @staticmethod
    def _clean_answer_value(value: str) -> str:
        cleaned = str(value).strip().strip("`'\"")
        cleaned = re.split(r"(?i)\bassistantfinalanswer\s*:", cleaned, maxsplit=1)[0].strip()
        cleaned = re.sub(r"(?is)^answer\s*:\s*", "", cleaned).strip()
        return re.sub(r"[\s\.;:,]+$", "", cleaned)


def _coerce_float(value) -> float | None:
    if value in {None, ""}:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _layout(input_kind: str) -> tuple[str, str, str]:
    if input_kind in {"callgraph", "fan-out", "t2p"}:
        return "from", "to", "from_url"
    if input_kind in {"fanin", "fan-in", "p2t"}:
        return "to", "from", "to_url"
    raise ValueError(f"Unsupported input_kind: {input_kind}")


def _display_method_text(row, prefix: str) -> str:
    for field_name in (
        f"{prefix}_tctracer_fqs",
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
