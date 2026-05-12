from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


TARGET_INTEGER_COLUMNS: dict[str, list[str]] = {
    "method": ["start_line", "end_line", "abstract"],
    "method-code": ["start_line", "end_line"],
    "class": ["start_line", "end_line", "abstract"],
    "callgraph": [
        "from_start",
        "from_end",
        "to_start",
        "to_end",
        "from_invocation",
        "to_invocation",
        "from_lcba",
        "to_lcba",
        "from_call_depth",
        "to_call_depth",
    ],
    "fanin": [
        "from_start",
        "from_end",
        "to_start",
        "to_end",
        "from_invocation",
        "to_invocation",
        "from_lcba",
        "to_lcba",
        "from_call_depth",
        "to_call_depth",
    ],
}


@dataclass(frozen=True)
class MigrationResult:
    file: Path
    target: str
    rows: int
    changed_rows: int
    changed_cells: int
    written: bool


def normalize_integer_columns(df: pd.DataFrame, columns: Iterable[str]) -> pd.DataFrame:
    out = df.copy()
    for column in columns:
        if column in out.columns:
            out[column] = out[column].map(_normalize_integer_cell)
    return out


def migrate_file(
    csv_file: Path,
    target: str,
    *,
    dry_run: bool = False,
    backup: bool = False,
) -> MigrationResult:
    columns = TARGET_INTEGER_COLUMNS[target]
    df = pd.read_csv(csv_file, dtype=str, keep_default_na=False, na_filter=False)
    normalized = normalize_integer_columns(df, columns)
    present_columns = [column for column in columns if column in df.columns]
    if present_columns:
        changed_mask = df[present_columns] != normalized[present_columns]
        changed_rows = int(changed_mask.any(axis=1).sum())
        changed_cells = int(changed_mask.sum().sum())
    else:
        changed_rows = 0
        changed_cells = 0

    should_write = changed_cells > 0 and not dry_run
    if should_write:
        if backup:
            backup_file = csv_file.with_name(f"bk_{csv_file.name}")
            backup_file.write_bytes(csv_file.read_bytes())
        tmp_file = csv_file.with_suffix(f"{csv_file.suffix}.tmp")
        normalized.to_csv(tmp_file, index=False)
        os.replace(tmp_file, csv_file)

    return MigrationResult(
        file=csv_file,
        target=target,
        rows=len(df),
        changed_rows=changed_rows,
        changed_cells=changed_cells,
        written=should_write,
    )


def collect_csv_files(data_directory: Path, targets: Iterable[str], projects: set[str] | None) -> list[tuple[str, Path]]:
    files: list[tuple[str, Path]] = []
    for target in targets:
        target_dir = data_directory / target
        if projects:
            files.extend((target, target_dir / f"{project}.csv") for project in sorted(projects))
        elif target_dir.exists():
            files.extend((target, path) for path in sorted(target_dir.glob("*.csv")))
    return files


def parse_projects(values: list[str] | None) -> set[str] | None:
    if not values:
        return None
    projects: set[str] = set()
    for value in values:
        projects.update(part.strip() for part in value.split(",") if part.strip())
    return projects or None


def parse_targets(value: str) -> list[str]:
    targets = [part.strip() for part in value.split(",") if part.strip()]
    unknown = sorted(set(targets) - set(TARGET_INTEGER_COLUMNS))
    if unknown:
        raise argparse.ArgumentTypeError(f"unknown target(s): {', '.join(unknown)}")
    return targets


def run_migration(
    data_directory: Path,
    targets: list[str],
    *,
    projects: set[str] | None = None,
    dry_run: bool = False,
    backup: bool = False,
) -> list[MigrationResult]:
    results: list[MigrationResult] = []
    for target, csv_file in collect_csv_files(data_directory, targets, projects):
        if not csv_file.exists():
            print(f"{csv_file}: skipped, file does not exist")
            continue
        result = migrate_file(csv_file, target, dry_run=dry_run, backup=backup)
        results.append(result)
        action = "dry run" if dry_run else "written" if result.written else "already clean"
        print(
            f"{csv_file}: {result.rows} row(s), "
            f"{result.changed_rows} row(s) changed, {result.changed_cells} cell(s) changed; "
            f"{action}"
        )
    return results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="One-time migration for CSV integer columns serialized as values such as 72.0.",
    )
    parser.add_argument(
        "--data-directory",
        required=True,
        help="Data directory containing method, class, method-code, callgraph, and fanin subdirectories.",
    )
    parser.add_argument(
        "--target",
        default="method,class,method-code,callgraph,fanin",
        type=parse_targets,
        help="Comma-separated targets to migrate. Supported: method,class,method-code,callgraph,fanin.",
    )
    parser.add_argument(
        "--project",
        action="append",
        help="Project name to migrate. May be repeated or comma-separated. Defaults to all CSVs for selected targets.",
    )
    parser.add_argument("--dry-run", action="store_true", help="Report changes without writing CSVs.")
    parser.add_argument("--backup", action="store_true", help="Create bk_<project>.csv before rewriting a CSV.")
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    run_migration(
        Path(args.data_directory),
        args.target,
        projects=parse_projects(args.project),
        dry_run=args.dry_run,
        backup=args.backup,
    )


def _normalize_integer_cell(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    if not text:
        return ""
    try:
        numeric = float(text)
    except ValueError:
        return text
    if not np.isfinite(numeric) or not np.isclose(numeric, round(numeric)):
        return text
    return str(int(round(numeric)))


if __name__ == "__main__":
    main()
