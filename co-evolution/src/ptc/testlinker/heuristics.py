from __future__ import annotations

import re


class CupTokenizer:
    @classmethod
    def camel_case_split(cls, identifier: str) -> list[str]:
        return re.sub(r"([A-Z][a-z])", r" \1", re.sub(r"([A-Z]+)", r" \1", identifier)).strip().split()

    @classmethod
    def tokenize_identifier_raw(cls, token: str, keep_underscore: bool = False) -> list[str]:
        regex = r"(_+)" if keep_underscore else r"_+"
        identifier_tokens = []
        for part in re.split(regex, token):
            if part:
                identifier_tokens.extend(cls.camel_case_split(part))
        return [token.lower() for token in identifier_tokens if token]


PREFIXES = [
    "testCases",
    "TestCases",
    "testcases",
    "testCase",
    "TestCase",
    "testcase",
    "tests",
    "Tests",
    "test_",
    "test",
    "Test",
]


def recommend_signatures_by_name(example: dict[str, object]) -> list[str] | None:
    test_name = _test_name_without_prefix(str(example.get("test_name", "")))
    if test_name is None:
        return None

    test_name_tokens = CupTokenizer.tokenize_identifier_raw(test_name)
    signatures = dict(example.get("signature", {}))
    recommendations = []
    for signature, payload in signatures.items():
        production_name = _production_name(signature)
        if CupTokenizer.tokenize_identifier_raw(production_name) != test_name_tokens:
            continue
        detail_sigs = list(payload.get("detail_sigs", [])) if isinstance(payload, dict) else []
        recommendations.extend(detail_sigs or [signature])
    return sorted(set(recommendations)) or None


def _test_name_without_prefix(name: str) -> str | None:
    for prefix in PREFIXES:
        if prefix in name:
            return name.replace(prefix, "", 1)
    return None


def _production_name(signature: str) -> str:
    match = re.search(r"(\w+)(?=\s*\()", signature)
    return match.group(1) if match else ""
