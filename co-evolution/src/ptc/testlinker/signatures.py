from __future__ import annotations

import re


def invocation_name(signature: str) -> str:
    before_params = signature.split("(", maxsplit=1)[0]
    return before_params.rsplit(".", maxsplit=1)[-1]


def split_signature_params(signature: str) -> list[str]:
    match = re.search(r"\((.*)\)\s*$", str(signature))
    if not match:
        return []

    params_text = match.group(1).strip()
    if not params_text:
        return []

    params: list[str] = []
    current: list[str] = []
    generic_depth = 0
    array_depth = 0
    for char in params_text:
        if char == "<":
            generic_depth += 1
        elif char == ">" and generic_depth:
            generic_depth -= 1
        elif char == "[":
            array_depth += 1
        elif char == "]" and array_depth:
            array_depth -= 1

        if char == "," and generic_depth == 0 and array_depth == 0:
            param = "".join(current).strip()
            if param:
                params.append(param)
            current = []
            continue
        current.append(char)

    param = "".join(current).strip()
    if param:
        params.append(param)
    return params


def compact_signature(signature: str) -> str:
    return re.sub(r"\s+", " ", str(signature or "").strip())
