from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from ptc.testlinker.json_bridge import read_examples
from ptc.testlinker.model import CodeT5InvocationRanker, ModelConfig
from ptc.testlinker.paths import (
    default_checkpoint_directory,
    default_model_directory,
    model_output_csv_path,
    model_output_json_path,
    raw_input_json_directory,
    testlinker_root,
)


MODEL_OUTPUT_COLUMNS = ["project", "from_url", "test_name", "invocation", "score", "rank"]


def execute_project(
    *,
    cache_directory: str | Path,
    project: str,
    testlinker_directory: str | Path | None = None,
    model_name_or_path: str | Path | None = None,
    checkpoint_directory: str | Path | None = None,
    checkpoint: str = "best-acc_and_f1",
    model_mode: str = "codet5",
    eval_batch_size: int = 16,
    max_source_length: int = 512,
    tokenizer_mode: str = "original",
    no_cuda: bool = False,
    replace: bool = False,
) -> pd.DataFrame:
    root = testlinker_root(cache_directory, testlinker_directory)

    output_json = model_output_json_path(root, project)
    output_csv = model_output_csv_path(root, project)

    if not replace and output_json.exists() and output_csv.exists():
        return pd.read_csv(output_csv, keep_default_na=False, na_filter=False)

    input_json_dir = raw_input_json_directory(root, project)
    if not input_json_dir.exists():
        raise FileNotFoundError(
            f"Model input JSON not found: {input_json_dir}. Run the preprocess stage first."
        )
    examples = read_examples(input_json_dir)

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

    detail_rows: list[dict[str, object]] = []
    output_rows: list[dict[str, object]] = []

    for example in examples:
        invocations = list(example.get("invocations", []))
        invocation_scores = ranker.score_invocations(
            body=str(example.get("body", "")),
            test_name=str(example.get("test_name", "")),
            invocations=invocations,
        )
        sorted_invocations = [
            inv for inv, _ in sorted(invocation_scores.items(), key=lambda item: item[1], reverse=True)
        ]

        detail_rows.append({
            "id": example["id"],
            "from_url": example.get("from_url", ""),
            "test_name": example.get("test_name", ""),
            "invocation_scores": invocation_scores,
            "sorted_invocations": sorted_invocations,
        })

        for rank, inv in enumerate(sorted_invocations, start=1):
            output_rows.append({
                "project": example.get("project", ""),
                "from_url": example.get("from_url", ""),
                "test_name": example.get("test_name", ""),
                "invocation": inv,
                "score": invocation_scores.get(inv, ""),
                "rank": rank,
            })

    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(
        "".join(json.dumps(row, ensure_ascii=True) + "\n" for row in detail_rows),
        encoding="utf-8",
    )

    output_csv_df = pd.DataFrame(output_rows, columns=MODEL_OUTPUT_COLUMNS)
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_csv_df.to_csv(output_csv, index=False)

    return output_csv_df


class _HeuristicRanker:
    def score_invocations(self, *, body: str, test_name: str, invocations: list[str]) -> dict[str, float]:
        return {
            invocation: float(len(invocations) - index)
            for index, invocation in enumerate(invocations)
        }


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
