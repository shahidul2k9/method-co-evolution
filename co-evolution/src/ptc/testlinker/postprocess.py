from __future__ import annotations

import json
import warnings
from pathlib import Path

import pandas as pd

from ptc.testlinker.json_bridge import read_examples
from ptc.testlinker.mapping import apply_signature_mapping
from ptc.testlinker.paths import (
    class_map_directory,
    model_output_json_path,
    postprocess_output_path,
    projects_all_functions_directory,
    raw_input_json_directory,
    testlinker_root,
)
from ptc.testlinker.signatures import invocation_name


POSTPROCESS_MODES = ["testlinker-original", "testlinker-symbolsolver"]

POSTPROCESS_OUTPUT_COLUMNS = [
    "project",
    "from_name",
    "to_name",
    "label",
    "label_pred",
    "pred_score",
    "recom_by",
    "testlinker_signature",
    "from_url",
    "to_url",
]


def postprocess_project(
    *,
    cache_directory: str | Path,
    project: str,
    top_k: int,
    testlinker_directory: str | Path | None = None,
    modes: list[str] | None = None,
    replace: bool = False,
) -> dict[str, pd.DataFrame]:
    if modes is None:
        modes = ["testlinker-original"]

    root = testlinker_root(cache_directory, testlinker_directory)

    if not replace:
        results = {}
        pending_modes = []
        for mode in modes:
            output_file = postprocess_output_path(root, project, mode)
            if output_file.exists():
                results[mode] = pd.read_csv(output_file, keep_default_na=False, na_filter=False)
            else:
                pending_modes.append(mode)
        if not pending_modes:
            return results
        modes = pending_modes
    else:
        results = {}

    model_json = model_output_json_path(root, project)
    if not model_json.exists():
        raise FileNotFoundError(
            f"Model output not found: {model_json}. Run the execute stage first."
        )
    model_output: dict[str, dict[str, object]] = {
        entry["id"]: entry
        for entry in (
            json.loads(line)
            for line in model_json.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    input_json_dir = raw_input_json_directory(root, project)
    if not input_json_dir.exists():
        raise FileNotFoundError(
            f"Model input JSON not found: {input_json_dir}. Run the preprocess stage first."
        )
    original_examples = read_examples(input_json_dir)

    for mode in modes:
        if mode == "testlinker-original":
            _warn_if_mapping_files_missing(root=root, project=project)
            examples = apply_signature_mapping(
                original_examples,
                class_map_dir=class_map_directory(root),
                projects_all_functions_dir=projects_all_functions_directory(root),
                project=project,
            )
            prediction_rows = _predict_with_mapping(examples, model_output, top_k)
        else:
            prediction_rows = _predict_with_url_match(original_examples, model_output, top_k)

        output_df = pd.DataFrame(prediction_rows, columns=POSTPROCESS_OUTPUT_COLUMNS)
        output_file = postprocess_output_path(root, project, mode)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_df.to_csv(output_file, index=False)
        results[mode] = output_df

    return results


def _predict_with_mapping(
    examples: list[dict[str, object]],
    model_output: dict[str, dict[str, object]],
    top_k: int,
) -> list[dict[str, object]]:
    """testlinker-original: resolve top-k invocations through signature mapping → to_urls."""
    rows = []
    for example in examples:
        model_entry = model_output.get(str(example["id"]), {})
        sorted_invocations: list[str] = list(model_entry.get("sorted_invocations", []))
        invocation_scores: dict[str, float] = dict(model_entry.get("invocation_scores", {}))

        recommended_sigs = sorted(
            set(_signatures_for_invocations(example, sorted_invocations[:top_k]))
        )
        rows.extend(
            _build_prediction_rows(example, recommended_sigs, "model", invocation_scores)
        )
    return rows


def _predict_with_url_match(
    examples: list[dict[str, object]],
    model_output: dict[str, dict[str, object]],
    top_k: int,
) -> list[dict[str, object]]:
    """testlinker-symbolsolver: direct URL match — top-k invocations → candidate_urls."""
    rows = []
    for example in examples:
        model_entry = model_output.get(str(example["id"]), {})
        sorted_invocations: list[str] = list(model_entry.get("sorted_invocations", []))
        invocation_scores: dict[str, float] = dict(model_entry.get("invocation_scores", {}))

        top_k_invocations = set(sorted_invocations[:top_k])
        candidate_urls = dict(example.get("candidate_urls", {}))
        candidate_names = dict(example.get("candidate_names", {}))
        label_urls = {str(u) for u in example.get("label_urls", [])}

        predicted_urls: set[str] = {
            url
            for sig, urls in candidate_urls.items()
            if invocation_name(sig) in top_k_invocations
            for url in urls
        }

        for sig, urls in candidate_urls.items():
            score = invocation_scores.get(invocation_name(sig), "")
            for to_url in urls:
                rows.append({
                    "project": example.get("project", ""),
                    "from_name": example.get("test_name", ""),
                    "to_name": candidate_names.get(sig, ""),
                    "from_url": example.get("from_url", ""),
                    "to_url": to_url,
                    "label": 1 if to_url in label_urls else 0,
                    "label_pred": 1 if to_url in predicted_urls else 0,
                    "pred_score": score,
                    "recom_by": "symbolsolver" if to_url in predicted_urls else "",
                    "testlinker_signature": sig if to_url in predicted_urls else "",
                })
    return rows


def _signatures_for_invocations(example: dict[str, object], invocations: list[str]) -> list[str]:
    signature_payload = dict(example.get("signature", {}))
    recommendations = []
    for invocation in invocations:
        for signature, payload in signature_payload.items():
            if invocation != invocation_name(signature):
                continue
            detail_sigs = list(payload.get("detail_sigs", [])) if isinstance(payload, dict) else []
            recommendations.extend(detail_sigs or [signature])
    return recommendations


def _build_prediction_rows(
    example: dict[str, object],
    recommended_signatures: list[str],
    recom_by: str,
    invocation_scores: dict[str, float],
) -> list[dict[str, object]]:
    candidate_urls = dict(example.get("candidate_urls", {}))
    candidate_names = dict(example.get("candidate_names", {}))
    label_urls = {str(u) for u in example.get("label_urls", [])}
    signature_to_urls = _expanded_signature_to_urls(example, candidate_urls)

    recommended_url_to_sig: dict[str, str] = {}
    for sig in recommended_signatures:
        for to_url in signature_to_urls.get(sig, []):
            recommended_url_to_sig[to_url] = sig

    rows = []
    for original_sig, urls in candidate_urls.items():
        score = invocation_scores.get(invocation_name(original_sig), "")
        for to_url in urls:
            rows.append({
                "project": example.get("project", ""),
                "from_name": example.get("test_name", ""),
                "to_name": candidate_names.get(original_sig, ""),
                "from_url": example.get("from_url", ""),
                "to_url": to_url,
                "label": 1 if to_url in label_urls else 0,
                "label_pred": 1 if to_url in recommended_url_to_sig else 0,
                "pred_score": score,
                "recom_by": recom_by if to_url in recommended_url_to_sig else "",
                "testlinker_signature": recommended_url_to_sig.get(to_url, ""),
            })
    return rows


def _expanded_signature_to_urls(
    example: dict[str, object],
    candidate_urls: dict[str, list[str]],
) -> dict[str, list[str]]:
    sig_to_urls: dict[str, list[str]] = {}
    for original_sig, urls in candidate_urls.items():
        sig_to_urls.setdefault(original_sig, []).extend(urls)
        payload = dict(example.get("signature", {})).get(original_sig, {})
        if isinstance(payload, dict):
            for detail_sig in payload.get("detail_sigs", []):
                sig_to_urls.setdefault(detail_sig, []).extend(urls)
    return sig_to_urls


def _warn_if_mapping_files_missing(*, root: Path, project: str) -> None:
    required_files = [
        class_map_directory(root) / "java_class_list.json",
        class_map_directory(root) / f"{project}_class_list.json",
        class_map_directory(root) / f"{project}_class_list_fqn.json",
        projects_all_functions_directory(root) / f"{project}_all_functions_full.json",
    ]
    missing_files = [path for path in required_files if not path.exists()]
    if not missing_files:
        return
    warnings.warn(
        f"TestLinker mapping files are missing for {project}; "
        "signature mapping will fall back to unmapped candidate signatures. "
        f"Missing: {', '.join(str(p) for p in missing_files)}",
        RuntimeWarning,
        stacklevel=2,
    )
