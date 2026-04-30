from __future__ import annotations

import json
import warnings
from pathlib import Path

import pandas as pd

from ptc.testlinker.heuristics import recommend_signatures_by_name
from ptc.testlinker.json_bridge import read_examples, write_mapped_json, write_project_json
from ptc.testlinker.mapping import apply_signature_mapping
from ptc.testlinker.model import CodeT5InvocationRanker, ModelConfig
from ptc.testlinker.paths import (
    class_map_directory,
    default_checkpoint_directory,
    default_model_directory,
    execute_csv_path,
    input_csv_path,
    projects_all_functions_directory,
    raw_detail_path,
    testlinker_root,
)
from ptc.testlinker.signatures import invocation_name


EXECUTE_OUTPUT_COLUMNS = [
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


def execute_project(
    *,
    cache_directory: str | Path,
    project: str,
    top_k: int,
    testlinker_directory: str | Path | None = None,
    model_name_or_path: str | Path | None = None,
    checkpoint_directory: str | Path | None = None,
    checkpoint: str = "best-acc_and_f1",
    model_mode: str = "codet5",
    eval_batch_size: int = 16,
    max_source_length: int = 512,
    tokenizer_mode: str = "original",
    only_model: bool = False,
    no_cuda: bool = False,
) -> pd.DataFrame:
    root = testlinker_root(cache_directory, testlinker_directory)
    input_file = input_csv_path(root, project)
    if not input_file.exists():
        raise FileNotFoundError(f"TestLinker input CSV not found: {input_file}")
    input_df = pd.read_csv(input_file, keep_default_na=False, na_filter=False, dtype=str)

    project_json_dir = write_project_json(input_df, root=root, project=project)
    examples = read_examples(project_json_dir)
    _warn_if_mapping_files_missing(root=root, project=project)
    mapped_examples = apply_signature_mapping(
        examples,
        class_map_dir=class_map_directory(root),
        projects_all_functions_dir=projects_all_functions_directory(root),
        project=project,
    )
    write_mapped_json(mapped_examples, root=root, project=project)

    ranker = _build_ranker(
        root=root,
        model_name_or_path=model_name_or_path,
        checkpoint_directory=checkpoint_directory,
        checkpoint=checkpoint,
        model_mode=model_mode,
        eval_batch_size=eval_batch_size,
        max_source_length=max_source_length,
        tokenizer_mode=tokenizer_mode,
        no_cuda=no_cuda,
    )

    detail_rows = []
    prediction_rows = []
    for example in mapped_examples:
        recom_by = "model"
        sorted_invocations = None
        invocation_scores: dict[str, float] = {}
        recommended_signatures = None if only_model else recommend_signatures_by_name(example)
        if recommended_signatures:
            recom_by = "rule"
        else:
            invocation_scores = ranker.score_invocations(
                body=str(example.get("body", "")),
                test_name=str(example.get("test_name", "")),
                invocations=list(example.get("invocations", [])),
            )
            sorted_invocations = [
                invocation
                for invocation, _ in sorted(invocation_scores.items(), key=lambda item: item[1], reverse=True)
            ]
            recommended_signatures = _signatures_for_invocations(example, sorted_invocations[:top_k])

        recommended_signatures = sorted(set(recommended_signatures))
        detail_rows.append(
            {
                "id": example["id"],
                "from_url": example.get("from_url", ""),
                "test_name": example.get("test_name", ""),
                "invocations": example.get("invocations", []),
                "sorted_invocations": sorted_invocations,
                "signatures": example.get("signature", {}),
                "recom_signatures": recommended_signatures,
                "labels": example.get("label", []),
                "recom_by": recom_by,
                "is_recom_all": False,
            }
        )
        prediction_rows.extend(_prediction_rows_for_example(example, recommended_signatures, recom_by, invocation_scores))

    raw_file = raw_detail_path(root, project)
    raw_file.parent.mkdir(parents=True, exist_ok=True)
    raw_file.write_text(
        "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in detail_rows),
        encoding="utf-8",
    )

    output_df = pd.DataFrame(prediction_rows, columns=EXECUTE_OUTPUT_COLUMNS)
    output_file = execute_csv_path(root, project)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_file, index=False)
    return output_df


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

    missing_display = ", ".join(str(path) for path in missing_files)
    warnings.warn(
        "TestLinker mapping files are missing for "
        f"{project}; signature mapping will fall back to unmapped candidate signatures. "
        f"Missing: {missing_display}",
        RuntimeWarning,
        stacklevel=2,
    )


class _HeuristicRanker:
    def score_invocations(self, *, body: str, test_name: str, invocations: list[str]) -> dict[str, float]:
        return {
            invocation: float(len(invocations) - index)
            for index, invocation in enumerate(invocations)
        }

    def rank_invocations(self, *, body: str, test_name: str, invocations: list[str]) -> list[str]:
        return list(invocations)


def _build_ranker(
    *,
    root: Path,
    model_name_or_path: str | Path | None,
    checkpoint_directory: str | Path | None,
    checkpoint: str,
    model_mode: str,
    eval_batch_size: int,
    max_source_length: int,
    tokenizer_mode: str,
    no_cuda: bool,
):
    if model_mode == "heuristic":
        return _HeuristicRanker()
    if model_mode != "codet5":
        raise ValueError(f"Unsupported model mode: {model_mode}")

    resolved_model = Path(model_name_or_path) if model_name_or_path else default_model_directory(root)
    resolved_checkpoint_directory = (
        Path(checkpoint_directory)
        if checkpoint_directory
        else default_checkpoint_directory(root, checkpoint)
    )
    checkpoint_file = resolved_checkpoint_directory / "pytorch_model.bin"
    if _looks_like_local_model_path(resolved_model) and not resolved_model.exists():
        raise FileNotFoundError(f"CodeT5 model directory not found: {resolved_model}")
    if not checkpoint_file.exists():
        raise FileNotFoundError(f"CodeT5 checkpoint file not found: {checkpoint_file}")
    return CodeT5InvocationRanker(
        ModelConfig(
            model_name_or_path=str(resolved_model),
            checkpoint_file=str(checkpoint_file),
            max_source_length=max_source_length,
            eval_batch_size=eval_batch_size,
            no_cuda=no_cuda,
            tokenizer_mode=tokenizer_mode,
        )
    )


def _looks_like_local_model_path(model_name_or_path: Path) -> bool:
    value = str(model_name_or_path)
    return (
        value.startswith(".")
        or value.startswith("/")
        or value.startswith("~")
        or len(model_name_or_path.parts) > 2
    )


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


def _prediction_rows_for_example(
    example: dict[str, object],
    recommended_signatures: list[str],
    recom_by: str,
    invocation_scores: dict[str, float],
) -> list[dict[str, object]]:
    candidate_urls = dict(example.get("candidate_urls", {}))
    candidate_names = dict(example.get("candidate_names", {}))
    signature_to_urls = _expanded_signature_to_urls(example, candidate_urls)
    recommended_url_to_signature = {}
    for signature in recommended_signatures:
        for to_url in signature_to_urls.get(signature, []):
            recommended_url_to_signature[to_url] = signature

    rows = []
    for original_signature, urls in candidate_urls.items():
        for to_url in urls:
            rows.append(
                {
                    "project": example.get("project", ""),
                    "from_name": example.get("test_name", ""),
                    "to_name": candidate_names.get(original_signature, ""),
                    "from_url": example.get("from_url", ""),
                    "to_url": to_url,
                    "label": 1 if _is_labeled_candidate(original_signature, to_url, example) else 0,
                    "label_pred": 1 if to_url in recommended_url_to_signature else 0,
                    "pred_score": _prediction_score_for_signature(original_signature, invocation_scores),
                    "recom_by": recom_by if to_url in recommended_url_to_signature else "",
                    "testlinker_signature": recommended_url_to_signature.get(to_url, ""),
                }
            )
    return rows


def _prediction_score_for_signature(signature: str, invocation_scores: dict[str, float]):
    if not invocation_scores:
        return ""
    score = invocation_scores.get(invocation_name(signature))
    return "" if score is None else score


def _is_labeled_candidate(signature: str, to_url: str, example: dict[str, object]) -> bool:
    label_urls = example.get("label_urls", [])
    if isinstance(label_urls, list) and to_url in {str(url) for url in label_urls}:
        return True
    return _signature_matches_label(signature, example, example.get("label", []))


def _signature_matches_label(signature: str, example: dict[str, object], labels: object) -> bool:
    if not isinstance(labels, list):
        return False
    label_set = {str(label) for label in labels}
    if signature in label_set:
        return True
    signature_payload = dict(example.get("signature", {})).get(signature, {})
    if isinstance(signature_payload, dict):
        return any(detail_signature in label_set for detail_signature in signature_payload.get("detail_sigs", []))
    return False


def _expanded_signature_to_urls(example: dict[str, object], candidate_urls: dict[str, list[str]]) -> dict[str, list[str]]:
    signature_to_urls = {}
    for original_signature, urls in candidate_urls.items():
        signature_to_urls.setdefault(original_signature, []).extend(urls)
        payload = dict(example.get("signature", {})).get(original_signature, {})
        if isinstance(payload, dict):
            for detail_signature in payload.get("detail_sigs", []):
                signature_to_urls.setdefault(detail_signature, []).extend(urls)
    return signature_to_urls
