#!/usr/bin/env python3
"""Update oracle JSON metadata from method CSV files.

Matches each JSON file by:
1. repository/project
2. file path
3. element name

If no exact `(file, element)` match is found, the script falls back to searching
by method name only. Any ambiguous match is left unchanged and written to the
log.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Tuple


@dataclass(frozen=True)
class MethodRow:
    project: str
    name: str
    file: str
    url: str
    start_line: int
    end_line: int
    commit_hash: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Update oracle JSON startCommitHash, url, startLine, and endLine."
    )
    parser.add_argument(
        "--oracle-dir",
        type=Path,
        required=True,
        help="Directory containing oracle JSON files.",
    )
    parser.add_argument(
        "--method-dir",
        type=Path,
        required=True,
        help="Directory containing method CSV files.",
    )
    parser.add_argument(
        "--log-file",
        type=Path,
        default=Path("update_oracle_method_metadata.log"),
        help="Path to the log file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report what would change without writing JSON files.",
    )
    return parser.parse_args()


def parse_line_number(raw_value: str) -> int:
    return int(float(raw_value))


def load_method_index(
    csv_path: Path,
) -> Tuple[Dict[Tuple[str, str], List[MethodRow]], Dict[str, List[MethodRow]]]:
    file_and_name_index: Dict[Tuple[str, str], List[MethodRow]] = defaultdict(list)
    name_only_index: Dict[str, List[MethodRow]] = defaultdict(list)

    with csv_path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("expression") != "method":
                continue

            file_path = (row.get("file") or "").strip()
            method_name = (row.get("name") or "").strip()
            if not file_path or not method_name:
                continue

            method_row = MethodRow(
                project=(row.get("project") or "").strip(),
                name=method_name,
                file=file_path,
                url=(row.get("url") or "").strip(),
                start_line=parse_line_number(row["start_line"]),
                end_line=parse_line_number(row["end_line"]),
                commit_hash=(row.get("hash") or "").strip(),
            )
            file_and_name_index[(file_path, method_name)].append(method_row)
            name_only_index[method_name].append(method_row)

    return file_and_name_index, name_only_index


def resolve_csv_path(method_dir: Path, repository_name: str, file_path: str) -> Path | None:
    direct_path = method_dir / f"{repository_name}.csv"
    if direct_path.exists():
        return direct_path

    # `lucene-solr` is split into separate CSV files in the dataset.
    if repository_name == "lucene-solr":
        if file_path.startswith("lucene/"):
            candidate = method_dir / "lucene.csv"
            return candidate if candidate.exists() else None
        if file_path.startswith("solr/"):
            candidate = method_dir / "solr.csv"
            return candidate if candidate.exists() else None

    return None


def iter_oracle_files(oracle_dir: Path) -> Iterable[Path]:
    return sorted(oracle_dir.glob("*.json"))


def log_message(lines: List[str], json_path: Path, message: str) -> None:
    lines.append(f"{json_path.name}: {message}")


def build_target_filename(json_path: Path, repository_name: str, file_path: str, element_name: str) -> str:
    number = json_path.stem.split("-", 1)[0]
    java_file_name = Path(file_path).stem
    return f"{number}-{repository_name}-{java_file_name}-{element_name}.json"


def repository_url_from_blob_url(url: str) -> str:
    marker = "/blob/"
    if marker not in url:
        return url
    prefix = url.split(marker, 1)[0]
    return f"{prefix}.git"


def main() -> int:
    args = parse_args()

    oracle_dir = args.oracle_dir.expanduser().resolve()
    method_dir = args.method_dir.expanduser().resolve()
    log_file = args.log_file.expanduser().resolve()

    if not oracle_dir.is_dir():
        raise SystemExit(f"Oracle directory not found: {oracle_dir}")
    if not method_dir.is_dir():
        raise SystemExit(f"Method directory not found: {method_dir}")

    csv_cache: Dict[
        Path,
        Tuple[Dict[Tuple[str, str], List[MethodRow]], Dict[str, List[MethodRow]]],
    ] = {}
    log_lines: List[str] = []
    updated = 0
    unchanged = 0
    skipped = 0
    renamed = 0

    for json_path in iter_oracle_files(oracle_dir):
        with json_path.open(encoding="utf-8") as handle:
            payload = json.load(handle)

        repository_name = payload.get("repositoryName", "").strip()
        file_path = payload.get("file", "").strip()
        element_name = payload.get("element", "").strip()

        csv_path = resolve_csv_path(method_dir, repository_name, file_path)
        if csv_path is None:
            skipped += 1
            log_message(
                log_lines,
                json_path,
                f"no CSV file found for repository '{repository_name}' and file '{file_path}'",
            )
            continue

        if csv_path not in csv_cache:
            csv_cache[csv_path] = load_method_index(csv_path)

        exact_index, name_only_index = csv_cache[csv_path]

        matches = exact_index.get((file_path, element_name), [])
        used_fallback = False

        if len(matches) > 1:
            skipped += 1
            log_message(
                log_lines,
                json_path,
                f"multiple matches ({len(matches)}) for file='{file_path}', element='{element_name}' in {csv_path.name}",
            )
            continue

        if not matches:
            matches = name_only_index.get(element_name, [])
            used_fallback = True

        if not matches:
            skipped += 1
            log_message(
                log_lines,
                json_path,
                f"no method match for file='{file_path}', element='{element_name}' in {csv_path.name}",
            )
            continue

        if len(matches) > 1:
            skipped += 1
            log_message(
                log_lines,
                json_path,
                f"multiple fallback matches ({len(matches)}) for element='{element_name}' in {csv_path.name}",
            )
            continue

        match = matches[0]
        changed = False

        for key, value in (
            ("repositoryName", match.project or repository_name),
            ("repositoryUrl", repository_url_from_blob_url(match.url)),
            ("startCommitHash", match.commit_hash),
            ("url", match.url),
            ("startLine", match.start_line),
            ("endLine", match.end_line),
            ("file", match.file),
        ):
            if payload.get(key) != value:
                payload[key] = value
                changed = True

        if used_fallback:
            log_message(
                log_lines,
                json_path,
                "updated using fallback match by method name only "
                f"(element='{element_name}', matched_file='{match.file}')",
            )

        target_name = build_target_filename(
            json_path=json_path,
            repository_name=payload.get("repositoryName", repository_name),
            file_path=payload.get("file", file_path),
            element_name=payload.get("element", element_name),
        )
        target_path = json_path.with_name(target_name)
        rename_needed = target_path != json_path
        if rename_needed:
            changed = True

        if changed:
            updated += 1
            if not args.dry_run:
                write_path = target_path if rename_needed else json_path
                with write_path.open("w", encoding="utf-8") as handle:
                    json.dump(payload, handle, indent=2)
                    handle.write("\n")
                if rename_needed and json_path.exists():
                    json_path.unlink()
                    renamed += 1
        else:
            unchanged += 1

    log_file.parent.mkdir(parents=True, exist_ok=True)
    summary = [
        f"oracle_dir={oracle_dir}",
        f"method_dir={method_dir}",
        f"dry_run={args.dry_run}",
        f"updated={updated}",
        f"unchanged={unchanged}",
        f"skipped={skipped}",
        f"renamed={renamed}",
        "",
    ]
    log_file.write_text("\n".join(summary + log_lines) + "\n", encoding="utf-8")

    print(f"Updated: {updated}")
    print(f"Unchanged: {unchanged}")
    print(f"Skipped: {skipped}")
    print(f"Renamed: {renamed}")
    print(f"Log: {log_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
