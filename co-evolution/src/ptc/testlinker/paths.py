from __future__ import annotations

from pathlib import Path


def testlinker_root(workspace_directory: str | Path) -> Path:
    return Path(workspace_directory) / "testlinker"


def input_csv_path(root: Path, project: str) -> Path:
    return root / "input" / "model-csv-input" / f"{project}.csv"


def model_output_csv_path(root: Path, project: str, model_name: str) -> Path:
    return root / "output" / model_name / "model-output-csv" / f"{project}.csv"


def postprocess_output_path(root: Path, project: str, method_resolver: str = "testlinker",
                            model_name: str = "codet5") -> Path:
    return root / "output" / model_name / method_resolver / f"{project}.csv"


def class_map_directory(root: Path) -> Path:
    return root / "input" / "class-mapping"


def projects_all_functions_directory(root: Path) -> Path:
    return root / "input" / "method-mapping"


def t2p_ground_truth_updated_file(project_directory: str | Path, experiment_name:str, project: str) -> Path:
    return Path(project_directory) / "data"/ experiment_name / "t2p-ground-truth" / f"{project}.csv"


def default_model_directory(root: Path) -> Path:
    return root / "pretrained-models" / "codet5-base"


def default_checkpoint_directory(workspace_directory: Path, checkpoint: str, model_name: str = "codet5") -> Path:
    return workspace_directory / "testlinker-finetuned-checkpoints" / f"{model_name}-base" / f"checkpoint-{checkpoint}"


def model_name_from_name_or_path(model_name_or_path: str | Path | None) -> str:
    if model_name_or_path is None:
        return "codet5"
    if "codet5" in str(model_name_or_path):
        return "codet5"
    return str(model_name_or_path)
