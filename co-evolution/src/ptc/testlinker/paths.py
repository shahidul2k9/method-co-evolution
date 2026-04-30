from __future__ import annotations

from pathlib import Path


def testlinker_root(cache_directory: str | Path, testlinker_directory: str | Path | None = None) -> Path:
    if testlinker_directory:
        return Path(testlinker_directory)
    return Path(cache_directory) / "testlinker"


def input_csv_path(root: Path, project: str) -> Path:
    return root / "input" / "project-csv" / f"{project}.csv"


def raw_input_json_directory(root: Path, project: str) -> Path:
    return root / "input" / "raw-json" / project


def mapped_input_json_directory(root: Path, project: str) -> Path:
    return root / "input" / "mapped-json" / project


def raw_detail_path(root: Path, project: str) -> Path:
    return root / "output" / "codet5" / "raw" / f"{project}_detail.json"


def execute_csv_path(root: Path, project: str) -> Path:
    return root / "output" / "codet5" / f"{project}.csv"


def final_prediction_path(cache_directory: str | Path, project: str) -> Path:
    return Path(cache_directory) / "data" / "testlinker" / "t2p-link" / "codet5" / f"{project}.csv"


def class_map_directory(root: Path) -> Path:
    return root / "class_map"


def projects_all_functions_directory(root: Path) -> Path:
    return root / "projects_all_functions"


def t2p_ground_truth_updated_file(cache_directory: str | Path, project: str) -> Path:
    return Path(cache_directory) / "data" / "t2p-ground-truth-updated" / f"{project}.csv"


def default_model_directory(root: Path) -> Path:
    return root / "pretrained-models" / "codet5-base"


def default_checkpoint_directory(root: Path, checkpoint: str) -> Path:
    return root / "finetuned-checkpoints" / "codet5-base" / f"checkpoint-{checkpoint}"
