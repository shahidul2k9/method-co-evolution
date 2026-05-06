from __future__ import annotations

import json
import re
from pathlib import Path


JAVA_CLASS_COMPATIBILITY = {
    "int": ["long"],
    "float": ["double"],
    "Integer": ["Long"],
}


def apply_signature_mapping(
    examples: list[dict[str, object]],
    *,
    class_map_dir: Path,
    projects_all_functions_dir: Path,
    project: str,
) -> list[dict[str, object]]:
    java_map = _read_json(class_map_dir / "java_class_list.json", default=JAVA_CLASS_COMPATIBILITY)
    class_map = _read_json(class_map_dir / f"{project}_class_list.json", default={})
    class_map.update(java_map)
    fqn_class_map = _read_json(class_map_dir / f"{project}_class_list_fqn.json", default={})
    fqn_class_map.update(java_map)
    function_map = _read_json(projects_all_functions_dir / f"{project}_all_functions_full.json", default={})

    mapped_examples = []
    for example in examples:
        mapped_example = dict(example)
        mapped_signatures = {}
        for signature, payload in dict(example.get("signature", {})).items():
            params = list(payload.get("params", [])) if isinstance(payload, dict) else []
            params_len = len(params)
            detail_sigs = _detail_signatures(
                signature=signature,
                params=params,
                params_len=params_len,
                class_map=class_map,
                fqn_class_map=fqn_class_map,
                function_map=function_map,
            )
            mapped_signatures[signature] = {
                "params_len": params_len,
                "params": params,
                "detail_sigs": detail_sigs or list(payload.get("detail_sigs", [])) or [signature],
            }
        mapped_example["signature"] = mapped_signatures
        mapped_examples.append(mapped_example)
    return mapped_examples


def _detail_signatures(
    *,
    signature: str,
    params: list[str],
    params_len: int,
    class_map: dict,
    fqn_class_map: dict,
    function_map: dict,
) -> list[str]:
    invo_name, prefix_name = _invo_name_and_prefix(signature)
    if not invo_name or not prefix_name:
        return []

    score_map: dict[str, float] = {}
    function_payload = function_map.get(invo_name, {})
    if not isinstance(function_payload, dict):
        return []

    constructor = f"{prefix_name}.{invo_name}"
    for lookup_prefix in _lookup_prefixes(prefix_name, constructor, function_payload, fqn_class_map):
        invocation_list = function_payload.get(lookup_prefix, [])
        if isinstance(invocation_list, list):
            score_map.update(_score_invocations(lookup_prefix, params, params_len, invocation_list, class_map))

    sorted_scores = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
    if not sorted_scores or sorted_scores[0][1] <= 0.5:
        return []

    top_score = sorted_scores[0][1]
    return [signature for signature, score in sorted_scores if score == top_score]


def _lookup_prefixes(prefix_name: str, constructor: str, function_payload: dict, fqn_class_map: dict) -> list[str]:
    prefixes = []
    if prefix_name in function_payload:
        prefixes.append(prefix_name)
    if constructor in function_payload:
        prefixes.append(constructor)
    simple_class_name = prefix_name.rsplit(".", maxsplit=1)[-1]
    for fqn in fqn_class_map.get(simple_class_name, []):
        if fqn in function_payload and fqn not in prefixes:
            prefixes.append(fqn)
    return prefixes


def _score_invocations(
    prefix_name: str,
    params: list[str],
    params_len: int,
    invocation_list: list[dict[str, list[str]]],
    class_map: dict,
) -> dict[str, float]:
    score_map = {}
    for invocation_payload in invocation_list:
        if not isinstance(invocation_payload, dict):
            continue
        for invocation_name, invocation_params in invocation_payload.items():
            invocation_params = list(invocation_params)
            if params_len != len(invocation_params):
                continue

            score = 0.6 if params_len == 0 else 0.0
            for param, invocation_param in zip(params, invocation_params):
                score += _parameter_score(_simple_type(param), _simple_type(invocation_param), class_map)
            score_map[f"{prefix_name}.{invocation_name}({', '.join(invocation_params)})"] = score
    return score_map


def _parameter_score(param: str, invocation_param: str, class_map: dict) -> float:
    if param == invocation_param:
        return 1.2
    if (
        invocation_param == "Object"
        or param == "null"
        or invocation_param == "null"
        or param == "Collection"
        or invocation_param == "Collection"
        or param == "T"
        or invocation_param == "T"
        or param == "Comparable"
        or invocation_param == "Comparable"
        or param == "Type"
        or invocation_param == "Type"
        or len(param) == 1
        or len(invocation_param) == 1
    ):
        return 1.0
    if _is_sub_class(param, invocation_param, class_map) or _is_sub_class(invocation_param, param, class_map):
        return 1.1
    return _longest_common_substring_length(param, invocation_param) / max(len(param), 1)


def _is_sub_class(sub_class: str, super_class: str, class_map: dict) -> bool:
    visited = set()

    def parents(name: str) -> list[str]:
        if name in visited:
            return []
        visited.add(name)
        found = []
        for parent in class_map.get(name, []):
            found.append(parent)
            found.extend(parents(parent))
        return found

    return super_class in parents(sub_class)


def _longest_common_substring_length(left: str, right: str) -> int:
    left = left.lower()
    right = right.lower()
    best = 0
    table = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]
    for left_index in range(1, len(left) + 1):
        for right_index in range(1, len(right) + 1):
            if left[left_index - 1] == right[right_index - 1]:
                table[left_index][right_index] = table[left_index - 1][right_index - 1] + 1
                best = max(best, table[left_index][right_index])
    return best


def _simple_type(value: str) -> str:
    match = re.search(r"(\w+)(?=\s*<)", value)
    if match:
        return match.group(1)
    return value.split(".")[-1].replace("[]", "")


def _invo_name_and_prefix(signature: str) -> tuple[str | None, str | None]:
    name_match = re.search(r"(?<=\.)([^.(]+)(?=\()", signature)
    prefix_match = re.search(r".*(?=\.)(?=[^(]*\()", signature)
    if name_match and prefix_match:
        return name_match.group(1), prefix_match.group()
    return None, None


def _read_json(path: Path, default):
    if not path.exists():
        return dict(default)
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return dict(default)
    return json.loads(text.splitlines()[0])
