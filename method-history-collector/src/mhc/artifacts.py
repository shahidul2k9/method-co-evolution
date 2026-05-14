from __future__ import annotations

from collections.abc import Iterable

TAG_ORDER = [
    "test-module",
    "doc-module",
    "test-code",
    "main-code",
    "test-case-method",
    "test-fixture-method",
    "test-helper-method",
    "test-resource",
    "main-resource",
    "test-code-generated",
    "main-code-generated",
]


def encode_tags(tags: Iterable[str]) -> str:
    values = {_normalize_tag(tag) for tag in tags if tag}
    return " ".join(f"#{tag}" for tag in TAG_ORDER if tag in values)


def split_tags(artifact: str | None) -> set[str]:
    if not artifact:
        return set()
    tags: set[str] = set()
    for token in str(artifact).split():
        for part in token.split("#"):
            normalized = _normalize_tag(part)
            if normalized:
                tags.add(normalized)
    return tags


def has_tag(artifact: str | None, tag: str) -> bool:
    return _normalize_tag(tag) in split_tags(artifact)


def is_test_module(artifact: str | None) -> bool:
    return has_tag(artifact, "test-module")


def is_doc_module(artifact: str | None) -> bool:
    return has_tag(artifact, "doc-module")


def is_test_code(artifact: str | None) -> bool:
    return has_tag(artifact, "test-code")


def is_main_code(artifact: str | None) -> bool:
    return has_tag(artifact, "main-code")


def is_production(artifact: str | None) -> bool:
    tags = split_tags(artifact)
    return "main-code" in tags and not any(tag.startswith("test-") or tag.startswith("doc-") for tag in tags)


def is_test_case_method(artifact: str | None) -> bool:
    return has_tag(artifact, "test-case-method")


def is_test_helper_method(artifact: str | None) -> bool:
    return has_tag(artifact, "test-helper-method")


def is_test_fixture_method(artifact: str | None) -> bool:
    return has_tag(artifact, "test-fixture-method")


def is_test_resource(artifact: str | None) -> bool:
    return has_tag(artifact, "test-resource")


def is_main_resource(artifact: str | None) -> bool:
    return has_tag(artifact, "main-resource")


def is_test_code_generated(artifact: str | None) -> bool:
    return has_tag(artifact, "test-code-generated")


def is_main_code_generated(artifact: str | None) -> bool:
    return has_tag(artifact, "main-code-generated")


def artifact_group(artifact: str | None) -> str:
    if is_test_case_method(artifact):
        return "test-case-method"
    if is_test_fixture_method(artifact):
        return "test-fixture-method"
    if is_test_helper_method(artifact):
        return "test-helper-method"
    if is_test_code(artifact):
        return "test-code"
    if is_main_code(artifact):
        return "main-code"
    if is_test_resource(artifact):
        return "test-resource"
    if is_main_resource(artifact):
        return "main-resource"
    return "unknown"


def _normalize_tag(tag: str | None) -> str:
    normalized = str(tag or "").strip()
    while normalized.startswith("#"):
        normalized = normalized[1:]
    return normalized
