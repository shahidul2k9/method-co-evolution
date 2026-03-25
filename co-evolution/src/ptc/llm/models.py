from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PromptContentText:
    type: str
    text: str


@dataclass(slots=True)
class PromptMessage:
    role: str
    content: list[PromptContentText] = field(default_factory=list)


@dataclass(slots=True)
class PromptInput:
    id: str
    fqs: str
    name: str
    code: str
    url: str
    prompt_text: str
    messages: list[PromptMessage] = field(default_factory=list)
    candidate_lookup: dict[str, dict[str, Any]] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    response_format: dict[str, Any] | None = None


@dataclass(slots=True)
class GenerationConfig:
    max_new_tokens: int = 256
    temperature: float = 0.0
    top_p: float = 1.0
    do_sample: bool = False


@dataclass(slots=True)
class ProviderGeneration:
    id: str
    output_text: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class LinkPrediction:
    id: str
    fqs: str
    name: str
    url: str
    label: str
    raw_output_text: str
    confidence: float | None = None
    selected_candidate_ids: list[str] = field(default_factory=list)
    selected_candidate_names: list[str] = field(default_factory=list)
    selected_candidate_sigs: list[str] = field(default_factory=list)
    selected_candidate_urls: list[str] = field(default_factory=list)
    rationale: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
