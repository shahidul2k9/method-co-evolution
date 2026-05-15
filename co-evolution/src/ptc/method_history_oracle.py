import argparse
import csv
import json
import os
import random
from dataclasses import dataclass
from pathlib import Path
from mhc.artifacts import is_test_case_method

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    load_dotenv = None

if load_dotenv is not None:
    load_dotenv(dotenv_path=".env", override=True)

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_DIRECTORY = os.environ.get("ME_WORKSPACE_DIRECTORY", str(REPO_ROOT / "workspace"))
ME_TEST_METHOD_ORACLE_DIRECTORY = os.environ.get("ME_TEST_METHOD_ORACLE_DIRECTORY")
DEFAULT_BLACKLIST_FILE = Path(f"{WORKSPACE_DIRECTORY}/data/oracle/blacklist-test-method-oracle.csv")
DEFAULT_REPOSITORY_FILE = Path(f"{WORKSPACE_DIRECTORY}/data/repository/repository.csv")
DEFAULT_METHOD_DIRECTORY = Path(f"{WORKSPACE_DIRECTORY}/data/method")
TARGET_REFS = {"grund", "islam"}
BLACKLIST_FIELDNAMES = [
    "file",
    "method_type",
    "method_name",
    "start_line",
    "end_line",
    "hash",
    "url",
    "parser",
]


@dataclass(frozen=True)
class Repository:
    project: str
    repository_url: str


@dataclass(frozen=True)
class MethodCandidate:
    project: str
    repository_url: str
    file: str
    method_name: str
    start_line: int
    end_line: int
    commit_hash: str
    method_type: str
    parser: str
    method_url: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Pick and validate test method oracle JSON files."
    )
    parser.add_argument(
        "--oracle-dir",
        type=Path,
        default=Path(ME_TEST_METHOD_ORACLE_DIRECTORY) if ME_TEST_METHOD_ORACLE_DIRECTORY else None,
        help="Directory containing test method oracle JSON files. Defaults to ME_TEST_METHOD_ORACLE_DIRECTORY.",
    )
    parser.add_argument(
        "--blacklist-file",
        type=Path,
        default=DEFAULT_BLACKLIST_FILE,
        help="CSV file used to store blacklisted test methods.",
    )
    subparsers = parser.add_subparsers(dest="command", required=False)

    pick_parser = subparsers.add_parser("pick", help="Pick missing oracle methods and create JSON files.")
    pick_parser.add_argument(
        "--required-per-project",
        type=int,
        default=3,
        help="Required number of oracle methods per project.",
    )
    pick_parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Random seed for reproducible method selection.",
    )
    pick_parser.add_argument(
        "--repository-file",
        type=Path,
        default=DEFAULT_REPOSITORY_FILE,
        help="Repository metadata CSV.",
    )
    pick_parser.add_argument(
        "--method-dir",
        type=Path,
        default=DEFAULT_METHOD_DIRECTORY,
        help="Directory containing per-project method CSV files.",
    )

    validate_parser = subparsers.add_parser("validate", help="Remove oracle files with too few history entries.")
    validate_parser.add_argument(
        "--min-history",
        type=int,
        default=3,
        help="Minimum number of history items required to keep an oracle file.",
    )

    return parser.parse_args()


def normalize_repo_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url


def ensure_git_url(url: str) -> str:
    normalized = (url or "").strip().rstrip("/")
    if normalized.endswith(".git"):
        return normalized
    return f"{normalized}.git"


def oracle_directory(path: Path) -> Path:
    if path is None:
        raise ValueError("Oracle directory is required. Set ME_TEST_METHOD_ORACLE_DIRECTORY or pass --oracle-dir.")
    resolved = path.expanduser().resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    return resolved


def parse_ref_tokens(ref_value: str) -> set[str]:
    return {token.strip().lower() for token in (ref_value or "").split("#") if token.strip()}


def load_target_repositories(repository_file: Path) -> list[Repository]:
    repositories: list[Repository] = []
    with repository_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not (parse_ref_tokens(row.get("ref", "")) & TARGET_REFS):
                continue
            repositories.append(
                Repository(
                    project=(row.get("project") or "").strip(),
                    repository_url=(row.get("url") or "").strip(),
                )
            )
    return repositories


def load_blacklist_rows(blacklist_file: Path) -> list[dict[str, str]]:
    if not blacklist_file.exists():
        return []
    with blacklist_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return [dict(row) for row in reader]


def load_blacklist_urls(blacklist_file: Path) -> set[str]:
    return {row.get("url", "").strip() for row in load_blacklist_rows(blacklist_file) if row.get("url")}


def save_blacklist_rows(blacklist_file: Path, rows: list[dict[str, str]]) -> None:
    deduped: dict[str, dict[str, str]] = {}
    for row in rows:
        url = (row.get("url") or "").strip()
        if not url:
            continue
        deduped[url] = {field: row.get(field, "") for field in BLACKLIST_FIELDNAMES}

    blacklist_file.parent.mkdir(parents=True, exist_ok=True)
    with blacklist_file.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=BLACKLIST_FIELDNAMES)
        writer.writeheader()
        writer.writerows(deduped.values())


def iter_oracle_files(oracle_dir: Path) -> list[Path]:
    return sorted(path for path in oracle_dir.rglob("*.json") if path.is_file())


def load_oracle_payloads(oracle_dir: Path) -> list[tuple[Path, dict]]:
    payloads: list[tuple[Path, dict]] = []
    for path in iter_oracle_files(oracle_dir):
        with path.open(encoding="utf-8") as handle:
            payloads.append((path, json.load(handle)))
    return payloads


def file_number(path: Path) -> int | None:
    prefix = path.stem.split("-", 1)[0]
    return int(prefix) if prefix.isdigit() else None


def existing_urls_and_counts(
        payloads: list[tuple[Path, dict]],
) -> tuple[set[str], dict[str, int], dict[str, int]]:
    existing_urls: set[str] = set()
    counts_by_name: dict[str, int] = {}
    counts_by_repo_url: dict[str, int] = {}

    for _, payload in payloads:
        url = (payload.get("url") or "").strip()
        if url:
            existing_urls.add(url)

        project = (payload.get("repositoryName") or "").strip()
        if project:
            counts_by_name[project] = counts_by_name.get(project, 0) + 1

        repository_url = normalize_repo_url(payload.get("repositoryUrl", ""))
        if repository_url:
            counts_by_repo_url[repository_url] = counts_by_repo_url.get(repository_url, 0) + 1

    return existing_urls, counts_by_name, counts_by_repo_url


def project_existing_numbers(payloads: list[tuple[Path, dict]]) -> dict[str, list[int]]:
    numbers: dict[str, list[int]] = {}
    for path, payload in payloads:
        project = (payload.get("repositoryName") or "").strip()
        number = file_number(path)
        if not project or number is None:
            continue
        numbers.setdefault(project, []).append(number)

    for project in numbers:
        numbers[project].sort()
    return numbers


def repository_existing_count(
        repository: Repository,
        counts_by_name: dict[str, int],
        counts_by_repo_url: dict[str, int],
) -> int:
    return max(
        counts_by_name.get(repository.project, 0),
        counts_by_repo_url.get(normalize_repo_url(repository.repository_url), 0),
    )


def parse_int(value: str) -> int:
    return int(float(value))


def load_test_method_candidates(repository: Repository, method_dir: Path) -> list[MethodCandidate]:
    method_file = method_dir / f"{repository.project}.csv"
    if not method_file.exists():
        print(f"Missing method file for {repository.project}: {method_file}")
        return []

    candidates: list[MethodCandidate] = []
    with method_file.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if not is_test_case_method(row.get("artifact") or ""):
                continue

            candidates.append(
                MethodCandidate(
                    project=repository.project,
                    repository_url=repository.repository_url,
                    file=(row.get("file") or "").strip(),
                    method_name=(row.get("name") or "").strip(),
                    start_line=parse_int(row.get("start_line") or "0"),
                    end_line=parse_int(row.get("end_line") or "0"),
                    commit_hash=(row.get("hash") or "").strip(),
                    method_type=(row.get("expression") or "").strip(),
                    parser=(row.get("parser") or "").strip(),
                    method_url=(row.get("url") or "").strip(),
                )
            )
    return candidates


def oracle_file_name(counter: int, project: str, file_path: str, method_name: str) -> str:
    java_file_name = Path(file_path).stem
    return f"{counter}-{project}-{java_file_name}-{method_name}.json"


def next_counter(occupied_numbers: set[int]) -> int:
    return max(occupied_numbers, default=1000) + 1


def choose_project_numbers(existing_numbers: list[int], required_per_project: int) -> list[int]:
    slots = set(existing_numbers)
    while len(slots) < required_per_project:
        current_min = min(slots)
        current_max = max(slots)
        internal_missing = [n for n in range(current_min, current_max + 1) if n not in slots]
        if internal_missing:
            slots.add(internal_missing[0])
            continue

        current_mean = sum(slots) / len(slots)
        candidates: list[int] = []
        if current_min > 1001:
            candidates.append(current_min - 1)
        candidates.append(current_max + 1)
        chosen = min(candidates, key=lambda value: (abs(value - current_mean), value))
        slots.add(chosen)

    return sorted(slots)


def number_slots_for_project(
    project: str,
    required_per_project: int,
    project_numbers: dict[str, list[int]],
    occupied_numbers: set[int],
) -> list[int]:
    existing_numbers = sorted(project_numbers.get(project, []))
    if existing_numbers:
        target_numbers = choose_project_numbers(existing_numbers, required_per_project)
        return [number for number in target_numbers if number not in existing_numbers]

    start = next_counter(occupied_numbers)
    return list(range(start, start + required_per_project))


def build_oracle_payload(candidate: MethodCandidate) -> dict:
    return {
        "repositoryName": candidate.project,
        "repositoryUrl": ensure_git_url(candidate.repository_url),
        "startCommitHash": candidate.commit_hash,
        "file": candidate.file,
        "url": candidate.method_url,
        "language": "Java",
        "elementType": "method",
        "element": candidate.method_name,
        "startLine": candidate.start_line,
        "endLine": candidate.end_line,
        "commits": [],
        "parser": candidate.parser,
    }


def pick_missing_methods(args: argparse.Namespace) -> None:
    oracle_dir = oracle_directory(args.oracle_dir)
    payloads = load_oracle_payloads(oracle_dir)
    existing_urls, counts_by_name, counts_by_repo_url = existing_urls_and_counts(payloads)
    project_numbers = project_existing_numbers(payloads)
    occupied_numbers = {number for numbers in project_numbers.values() for number in numbers}
    blacklist_urls = load_blacklist_urls(args.blacklist_file)
    repositories = load_target_repositories(args.repository_file)
    rng = random.Random(args.seed)

    created = 0
    for repository in repositories:
        existing_count = repository_existing_count(repository, counts_by_name, counts_by_repo_url)
        required = max(args.required_per_project - existing_count, 0)
        if required == 0:
            continue

        candidates = load_test_method_candidates(repository, args.method_dir)
        available = [
            candidate
            for candidate in candidates
            if candidate.method_url
               and candidate.method_url not in existing_urls
               and candidate.method_url not in blacklist_urls
        ]

        if not available:
            print(f"{repository.project}: no available test methods after excluding existing and blacklisted methods")
            continue

        selected = rng.sample(available, k=min(required, len(available)))
        target_numbers = number_slots_for_project(
            repository.project,
            args.required_per_project,
            project_numbers,
            occupied_numbers,
        )
        assignable_numbers = target_numbers[: len(selected)]

        for number, candidate in zip(assignable_numbers, selected):
            payload = build_oracle_payload(candidate)
            file_name = oracle_file_name(number, candidate.project, candidate.file, candidate.method_name)
            output_path = oracle_dir / file_name
            with output_path.open("w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
                handle.write("\n")
            existing_urls.add(candidate.method_url)
            counts_by_name[candidate.project] = counts_by_name.get(candidate.project, 0) + 1
            counts_by_repo_url[normalize_repo_url(candidate.repository_url)] = counts_by_repo_url.get(
                normalize_repo_url(candidate.repository_url), 0
            ) + 1
            project_numbers.setdefault(candidate.project, []).append(number)
            project_numbers[candidate.project].sort()
            occupied_numbers.add(number)
            created += 1

        print(
            f"{repository.project}: created {len(selected)} method(s), "
            f"target={args.required_per_project}, existing_after_pick={repository_existing_count(repository, counts_by_name, counts_by_repo_url)}"
        )
        if len(selected) < required:
            print(f"{repository.project}: only {len(selected)} candidate(s) available for {required} required slot(s)")

    print(f"Created {created} oracle file(s) in {oracle_dir}")


def blacklist_row_from_payload(payload: dict) -> dict[str, str]:
    return {
        "file": str(payload.get("file", "")),
        "method_type": "test",
        "method_name": str(payload.get("element", "")),
        "start_line": str(payload.get("startLine", "")),
        "end_line": str(payload.get("endLine", "")),
        "hash": str(payload.get("startCommitHash", "")),
        "url": str(payload.get("url", "")),
        "parser": str(payload.get("parser", "")),
    }


def validate_history_count(args: argparse.Namespace) -> None:
    oracle_dir = oracle_directory(args.oracle_dir)
    payloads = load_oracle_payloads(oracle_dir)
    blacklist_rows = load_blacklist_rows(args.blacklist_file)
    blacklist_urls = {row.get("url", "").strip() for row in blacklist_rows if row.get("url")}

    removed = 0
    for path, payload in payloads:
        history = payload.get("commits") or []
        if len(history) >= args.min_history:
            continue

        url = (payload.get("url") or "").strip()
        if url and url not in blacklist_urls:
            blacklist_rows.append(blacklist_row_from_payload(payload))
            blacklist_urls.add(url)

        path.unlink(missing_ok=True)
        removed += 1
        print(f"Removed {path.name}: history={len(history)}")

    save_blacklist_rows(args.blacklist_file, blacklist_rows)
    print(f"Removed {removed} oracle file(s)")
    print(f"Blacklist saved to {args.blacklist_file}")


def main() -> None:
    args = parse_args()
    command = args.command or "pick"
    # TODO: currently generate oracle ID produces conflicting number.
    if command == "pick":
        pick_missing_methods(args)
        return

    if command == "validate":
        validate_history_count(args)
        return

    raise ValueError(f"Unsupported command: {command}")

if __name__ == "__main__":
    main()
