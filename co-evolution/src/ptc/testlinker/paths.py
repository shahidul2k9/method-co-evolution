from __future__ import annotations

from pathlib import Path


def testlinker_root(workspace_directory: str | Path, testlinker_directory: str | Path | None = None) -> Path:
    if testlinker_directory:
        return Path(testlinker_directory)
    return Path(workspace_directory) / "testlinker"


def input_csv_path(root: Path, project: str) -> Path:
    return root / "input" / "model-csv-input" / f"{project}.csv"


def raw_input_json_directory(root: Path, project: str) -> Path:
    return root / "input" / "model-input-json" / project


def model_output_json_path(root: Path, project: str) -> Path:
    return root / "output" / "model-output-json" / f"{project}.json"


def model_output_csv_path(root: Path, project: str) -> Path:
    return root / "output" / "model-output-csv" / f"{project}.csv"


def postprocess_output_path(root: Path, project: str, mode: str = "testlinker-original") -> Path:
    return root / "output" / mode / f"{project}.csv"


def class_map_directory(root: Path) -> Path:
    return root / "input" / "class-mapping"


def projects_all_functions_directory(root: Path) -> Path:
    return root / "input" / "method-mapping"


def t2p_ground_truth_updated_file(project_directory: str | Path, project: str) -> Path:
    return Path(project_directory) / "data" / "ground-truth" / f"{project}.csv"


def default_model_directory(root: Path) -> Path:
    return root / "pretrained-models" / "codet5-base"


def default_checkpoint_directory(root: Path, checkpoint: str) -> Path:
    return root / "finetuned-checkpoints" / "codet5-base" / f"checkpoint-{checkpoint}"
