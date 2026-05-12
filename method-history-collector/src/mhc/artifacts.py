from __future__ import annotations

from collections.abc import Iterable

TAG_ORDER = [
    "test-module",
    "test-code",
    "test-unit",
    "test-integration",
    "test-method",
    "test-fixture",
    "test-utility",
    "test-resource",
    "production-resource",
    "test-generated",
    "production-generated",
    "production-code",
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


def is_test_code(artifact: str | None) -> bool:
    return has_tag(artifact, "test-code")


def is_test_method(artifact: str | None) -> bool:
    return has_tag(artifact, "test-method")


def is_test_utility(artifact: str | None) -> bool:
    return has_tag(artifact, "test-utility")


def is_test_fixture(artifact: str | None) -> bool:
    return has_tag(artifact, "test-fixture")


def is_test_unit(artifact: str | None) -> bool:
    return has_tag(artifact, "test-unit")


def is_test_integration(artifact: str | None) -> bool:
    return has_tag(artifact, "test-integration")


def is_test_resource(artifact: str | None) -> bool:
    return has_tag(artifact, "test-resource")


def is_production_resource(artifact: str | None) -> bool:
    return has_tag(artifact, "production-resource")


def is_test_generated(artifact: str | None) -> bool:
    return has_tag(artifact, "test-generated")


def is_production_generated(artifact: str | None) -> bool:
    return has_tag(artifact, "production-generated")


def is_production_code(artifact: str | None) -> bool:
    return has_tag(artifact, "production-code")


def artifact_group(artifact: str | None) -> str:
    if is_test_method(artifact):
        return "test-method"
    if is_test_fixture(artifact):
        return "test-fixture"
    if is_test_utility(artifact):
        return "test-utility"
    if is_test_code(artifact):
        return "test-code"
    if is_production_code(artifact):
        return "production-code"
    if is_test_resource(artifact):
        return "test-resource"
    if is_production_resource(artifact):
        return "production-resource"
    return "unknown"


def _normalize_tag(tag: str | None) -> str:
    normalized = str(tag or "").strip()
    while normalized.startswith("#"):
        normalized = normalized[1:]
    return normalized
