from __future__ import annotations

from pathlib import Path

import pandas as pd

from ptc.testlinker.model import CodeT5InvocationRanker, ModelConfig
from ptc.testlinker.paths import (
    default_checkpoint_directory,
    default_model_directory,
    input_csv_path,
    model_name_from_name_or_path,
    model_output_csv_path,
    testlinker_root,
)


def execute_project(
    *,
    experiment_directory: str | Path,
    project: str,
    model_name_or_path: str | Path | None = None,
    checkpoint_directory: str | Path | None = None,
    checkpoint_workspace_directory: str | Path | None = None,
    checkpoint: str = "best-acc_and_f1",
    eval_batch_size: int = 16,
    max_source_length: int = 512,
    tokenizer_mode: str = "original",
    no_cuda: bool = False,
    replace: bool = False,
) -> pd.DataFrame:
    root = testlinker_root(experiment_directory)
    model_name = model_name_from_name_or_path(model_name_or_path)

    output_csv = model_output_csv_path(root, project, model_name)

    if not replace and output_csv.exists():
        return pd.read_csv(output_csv, keep_default_na=False, na_filter=False)

    input_csv = input_csv_path(root, project)
    if not input_csv.exists():
        raise FileNotFoundError(f"Model input CSV not found: {input_csv}. Run the preprocess stage first.")
    input_df = pd.read_csv(input_csv, keep_default_na=False, na_filter=False)

    ranker = _build_ranker(
        experiment_directory=experiment_directory,
        checkpoint_workspace_directory=checkpoint_workspace_directory,
        root=root,
        model_name_or_path=model_name_or_path,
        checkpoint_directory=checkpoint_directory,
        checkpoint=checkpoint,
        eval_batch_size=eval_batch_size,
        max_source_length=max_source_length,
        tokenizer_mode=tokenizer_mode,
        no_cuda=no_cuda,
    )

    output_df = input_df.copy()
    output_df["score"] = pd.NA
    output_df["rank"] = pd.NA

    for from_url, group_df in input_df.groupby("from_url", sort=False):
        invocations = list(dict.fromkeys(str(value) for value in group_df["to_name"].tolist() if str(value)))
        invocation_scores = ranker.score_invocations(
            body=str(group_df.iloc[0].get("body", "")),
            test_name=str(group_df.iloc[0].get("from_name", "")),
            invocations=invocations,
        )
        rank_by_invocation = {
            invocation: rank
            for rank, (invocation, _) in enumerate(
                sorted(invocation_scores.items(), key=lambda item: item[1], reverse=True),
                start=1,
            )
        }
        group_index = group_df.index
        output_df.loc[group_index, "score"] = group_df["to_name"].map(invocation_scores)
        output_df.loc[group_index, "rank"] = group_df["to_name"].map(rank_by_invocation)

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    output_df.to_csv(output_csv, index=False)

    return output_df


def _build_ranker(*, experiment_directory: str | Path, checkpoint_workspace_directory: str | Path | None = None,
                  root: Path, model_name_or_path: str | Path | None, checkpoint_directory: str | Path | None,
                  checkpoint: str, eval_batch_size: int, max_source_length: int, tokenizer_mode: str, no_cuda: bool):

    resolved_model = Path(model_name_or_path) if model_name_or_path else default_model_directory(root)
    resolved_checkpoint_directory = (
        Path(checkpoint_directory)
        if checkpoint_directory
        else default_checkpoint_directory(
            Path(checkpoint_workspace_directory or experiment_directory),
            checkpoint,
            model_name=model_name_from_name_or_path(model_name_or_path),
        )
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
