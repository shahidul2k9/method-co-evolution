"""Copy published artifacts between experiments for destination projects."""

from __future__ import annotations

import argparse
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pandas as pd


CSV_ARTIFACTS = ("class", "method", "callgraph", "fanin")


@dataclass(frozen=True)
class CopyOperation:
    artifact: str
    project: str
    source: Path
    destination: Path


@dataclass(frozen=True)
class CopyResult:
    operation: CopyOperation
    status: str


def load_destination_projects(destination_experiment: Path) -> list[str]:
    project_file = destination_experiment / "project.csv"
    if not project_file.is_file():
        raise FileNotFoundError(f"destination project index not found: {project_file}")

    try:
        project_df = pd.read_csv(project_file, dtype=str, keep_default_na=False, na_filter=False)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as exc:
        raise ValueError(f"destination project index is invalid: {project_file}") from exc
    if "project" not in project_df.columns:
        raise ValueError(f"destination project index is missing 'project' column: {project_file}")

    projects = [project.strip() for project in project_df["project"].tolist() if project.strip()]
    return list(dict.fromkeys(projects))


def collect_copy_operations(
    source_experiment: Path,
    destination_experiment: Path,
    projects: Iterable[str],
) -> list[CopyOperation]:
    project_names = set(projects)
    operations: list[CopyOperation] = []

    for project in sorted(project_names):
        for artifact in CSV_ARTIFACTS:
            operations.append(
                CopyOperation(
                    artifact=artifact,
                    project=project,
                    source=source_experiment / artifact / f"{project}.csv",
                    destination=destination_experiment / artifact / f"{project}.csv",
                )
            )

    history_root = source_experiment / "method-history-gz"
    if history_root.is_dir():
        tool_directories = {
            source_file.parent
            for source_file in history_root.rglob("*.tar.gz")
            if not any(part.startswith(".") for part in source_file.relative_to(history_root).parts)
        }
        for tool_directory in sorted(tool_directories):
            relative_tool_directory = tool_directory.relative_to(history_root)
            for project in sorted(project_names):
                relative_path = relative_tool_directory / f"{project}.tar.gz"
                operations.append(
                    CopyOperation(
                        artifact="method-history-gz",
                        project=project,
                        source=history_root / relative_path,
                        destination=destination_experiment / "method-history-gz" / relative_path,
                    )
                )

    return operations


def execute_copy_operations(
    operations: Iterable[CopyOperation],
    *,
    replace: bool = False,
    dry_run: bool = False,
) -> list[CopyResult]:
    results: list[CopyResult] = []
    for operation in operations:
        if not operation.source.is_file():
            status = "missing"
        elif operation.destination.exists() and not replace:
            status = "skipped"
        elif dry_run:
            status = "planned"
        else:
            operation.destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(operation.source, operation.destination)
            status = "copied"

        print(f"{status}: {operation.source} -> {operation.destination}")
        results.append(CopyResult(operation=operation, status=status))
    return results


def run_migration(
    workspace_directory: Path,
    source_experiment_name: str,
    destination_experiment_name: str,
    *,
    replace: bool = False,
    dry_run: bool = False,
) -> list[CopyResult]:
    source_name = source_experiment_name.strip()
    destination_name = destination_experiment_name.strip()
    if not source_name or not destination_name:
        raise ValueError("source and destination experiment names must be non-empty")
    if source_name == destination_name:
        raise ValueError("source and destination experiments must differ")

    experiment_root = workspace_directory.expanduser().resolve() / "experiment"
    source_experiment = experiment_root / source_name
    destination_experiment = experiment_root / destination_name
    if not source_experiment.is_dir():
        raise FileNotFoundError(f"source experiment does not exist: {source_experiment}")
    if not destination_experiment.is_dir():
        raise FileNotFoundError(f"destination experiment does not exist: {destination_experiment}")

    projects = load_destination_projects(destination_experiment)
    operations = collect_copy_operations(source_experiment, destination_experiment, projects)

    print(f"Source experiment: {source_experiment}")
    print(f"Destination experiment: {destination_experiment}")
    print(f"Destination projects: {len(projects)}")
    if replace:
        print("Replace: enabled")
    if dry_run:
        print("Dry-run: no files will be copied")
    print()

    results = execute_copy_operations(operations, replace=replace, dry_run=dry_run)
    counts = {
        status: sum(result.status == status for result in results)
        for status in ("copied", "planned", "skipped", "missing")
    }
    print(
        "\nTotal: "
        f"copied={counts['copied']}, planned={counts['planned']}, "
        f"skipped={counts['skipped']}, missing={counts['missing']}"
    )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Copy published artifacts for destination-listed projects between experiments.",
    )
    parser.add_argument(
        "--workspace-directory",
        default=os.environ.get("ME_WORKSPACE_DIRECTORY"),
        help="Workspace root containing experiment/. Defaults to ME_WORKSPACE_DIRECTORY.",
    )
    parser.add_argument("--source-experiment-name", required=True)
    parser.add_argument("--destination-experiment-name", required=True)
    parser.add_argument("--replace", action="store_true", help="Overwrite existing destination artifacts.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned copies without modifying files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.workspace_directory:
        parser.error("--workspace-directory is required when ME_WORKSPACE_DIRECTORY is not set")

    try:
        run_migration(
            Path(args.workspace_directory),
            args.source_experiment_name,
            args.destination_experiment_name,
            replace=args.replace,
            dry_run=args.dry_run,
        )
    except (FileNotFoundError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
