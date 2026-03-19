from __future__ import annotations

import json

from ptc.llm.models import LinkPrediction, PromptInput
from ptc.llm.persistence import normalize_input_kind


class MethodLinkingPromptFactory:
    def build_prompt(self, case_df, input_kind: str) -> PromptInput:
        normalized_input_kind = normalize_input_kind(input_kind)
        source_prefix, candidate_prefix, group_column = _layout(normalized_input_kind)
        source_row = case_df.iloc[0]
        source_fqs = _display_method_text(source_row, source_prefix)
        source_url = source_row[f"{source_prefix}_url"]
        source_file = source_row[f"{source_prefix}_file"]

        candidate_lookup: dict[str, dict] = {}
        candidate_lines = []
        for index, row in enumerate(case_df.itertuples(index=False), start=1):
            candidate_fqs = _display_method_text(row, candidate_prefix)
            candidate_id = f"c{index}"
            candidate_sig = _row_value(row, f"{candidate_prefix}_sig")
            candidate_url = _row_value(row, f"{candidate_prefix}_url")
            candidate_file = getattr(row, f"{candidate_prefix}_file", "")

            if not any([candidate_fqs, candidate_sig, candidate_url, candidate_file]):
                continue

            candidate_lookup[candidate_id] = {
                "fqs": candidate_fqs,
                "sig": candidate_sig or candidate_fqs,
                "url": candidate_url,
            }
            candidate_lines.append(
                # f"{candidate_id}: fqs={candidate_fqs}; file={candidate_file}"
                f"{candidate_id}: fqs={candidate_fqs}"
            )

        prompt_text = self._build_prompt_text(
            input_kind=normalized_input_kind,
            source_fqs=source_fqs,
            source_file=source_file,
            candidate_lines=candidate_lines,
        )

        return PromptInput(
            id=source_url,
            fqs=source_fqs,
            url=source_url,
            prompt_text=prompt_text,
            candidate_lookup=candidate_lookup,
            metadata={"input_kind": normalized_input_kind, "candidate_count": len(candidate_lookup)},
        )

    @staticmethod
    def _build_prompt_text(
        input_kind: str,
        source_fqs: str,
        source_file: str,
        candidate_lines: list[str],
    ) -> str:
        schema = (
            '{"candidate_ids":[],"candidate_confidences":{},"confidence":0.0,'
            '"rationale":"short explanation"}'
        )
        candidate_block = "\n".join(candidate_lines) if candidate_lines else "- None"

        if input_kind == "t2p":
            return (
                "You are linking test methods to production methods in a Java codebase.\n"
                "This is a zero-shot test-to-production classification task.\n"
                "The production method is the method under test.\n"
                "The candidate methods are production methods called by the source method.\n"
                "Select zero, one, or multiple candidate production methods that are actually tested by or strongly linked to the test method.\n"
                "Respond with valid JSON only using this schema:\n"
                f"{schema}\n\n"
                "Only return candidate IDs such as c1, c2, c3. Do not return a label field.\n"
                "Do not repeat the prompt. Do not use markdown or code fences.\n"
                f"Test method FQS: {source_fqs}\n"
                "Candidate production methods called by the test method:\n"
                f"{candidate_block}\n\n"
                "JSON only:"
            )

        if input_kind == "p2t":
            return (
                "You are linking production methods to test methods in a Java codebase.\n"
                "This is a zero-shot production-to-test classification task.\n"
                "The production method is the method under test.\n"
                "The candidate methods are production methods that call that production method.\n"
                "Select zero, one, or multiple candidate production methods that actually call the production method.\n"
                "Respond with valid JSON only using this schema:\n"
                f"{schema}\n\n"
                "Only return candidate IDs such as c1, c2, c3. Do not return a label field.\n"
                "Do not repeat the prompt. Do not use markdown or code fences.\n"
                f"Production method FQS: {source_fqs}\n"
                "Candidate test methods that call this production method:\n"
                f"{candidate_block}\n\n"
                "JSON only:"
            )

        raise ValueError(f"Unsupported input_kind: {input_kind}")


class JsonPredictionParser:
    parser_name = "json_prediction_parser"

    def parse(self, prompt_input: PromptInput, output_text: str) -> LinkPrediction:
        payload = self._extract_or_fallback_payload(output_text)
        candidate_ids = self._normalize_candidate_ids(payload)
        candidate_confidences = self._normalize_candidate_confidences(payload, candidate_ids)
        selected_candidate_sigs: list[str] = []
        selected_candidate_urls: list[str] = []

        for candidate_id in candidate_ids:
            candidate = prompt_input.candidate_lookup.get(candidate_id)
            if candidate is None:
                continue
            selected_candidate_sigs.append(candidate["sig"])
            selected_candidate_urls.append(candidate["url"])

        return LinkPrediction(
            id=prompt_input.id,
            fqs=prompt_input.fqs,
            url=prompt_input.url,
            label="match" if candidate_ids else "none",
            raw_output_text=output_text,
            confidence=self._coerce_confidence(payload.get("confidence")),
            selected_candidate_ids=candidate_ids,
            selected_candidate_confidences=candidate_confidences,
            selected_candidate_sigs=selected_candidate_sigs,
            selected_candidate_urls=selected_candidate_urls,
            rationale=str(payload.get("rationale", "")).strip(),
            metadata={"raw_json": payload},
        )

    @classmethod
    def _extract_or_fallback_payload(cls, output_text: str) -> dict:
        try:
            return cls._extract_json(output_text)
        except ValueError:
            stripped_output = output_text.strip()
            return {
                "candidate_ids": [],
                "candidate_confidences": {},
                "confidence": None,
                "rationale": (
                    "Model did not return a JSON object."
                    if stripped_output
                    else "Model returned an empty response."
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

        for start_index, character in enumerate(output_text):
            if character not in {"{", "["}:
                continue
            try:
                raw_payload, _ = decoder.raw_decode(output_text[start_index:])
            except json.JSONDecodeError:
                continue
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
        if "candidate_ids" not in payload and "candidate_id" not in payload:
            return False

        rationale = str(payload.get("rationale", "")).strip().lower()
        if rationale == "short explanation":
            return False

        candidate_ids = payload.get("candidate_ids", payload.get("candidate_id", []))
        candidate_confidences = payload.get("candidate_confidences")
        if (
            isinstance(candidate_ids, list)
            and candidate_ids == ["c1", "c2"]
            and rationale == "short explanation"
            and candidate_confidences == {}
        ):
            return False

        return True

    @staticmethod
    def _normalize_payload_shape(raw_payload) -> dict | None:
        if isinstance(raw_payload, dict):
            return raw_payload
        if isinstance(raw_payload, list) and all(isinstance(item, str) for item in raw_payload):
            return {"candidate_ids": raw_payload}
        return None

    @staticmethod
    def _normalize_candidate_ids(payload: dict) -> list[str]:
        raw_value = payload.get("candidate_ids", payload.get("candidate_id", []))
        if raw_value in (None, "", "NONE"):
            return []
        if isinstance(raw_value, str):
            return [raw_value]
        if isinstance(raw_value, list):
            return [str(item) for item in raw_value if str(item).upper() != "NONE"]
        raise ValueError(f"Unsupported candidate_ids payload: {raw_value}")

    @classmethod
    def _normalize_candidate_confidences(
        cls,
        payload: dict,
        candidate_ids: list[str],
    ) -> list[float | None]:
        raw_value = payload.get("candidate_confidences", {})
        if raw_value in (None, ""):
            return [None] * len(candidate_ids)
        if isinstance(raw_value, dict):
            return [cls._coerce_confidence(raw_value.get(candidate_id)) for candidate_id in candidate_ids]
        if isinstance(raw_value, list):
            if all(isinstance(item, dict) for item in raw_value):
                confidence_by_id = {
                    str(item.get("candidate_id", "")): cls._coerce_confidence(item.get("confidence"))
                    for item in raw_value
                }
                return [confidence_by_id.get(candidate_id) for candidate_id in candidate_ids]
            confidences = [cls._coerce_confidence(item) for item in raw_value[: len(candidate_ids)]]
            while len(confidences) < len(candidate_ids):
                confidences.append(None)
            return confidences
        raise ValueError(f"Unsupported candidate_confidences payload: {raw_value}")

    @staticmethod
    def _coerce_confidence(value) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None


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
