"""Create a sanitized Zenodo replication package.

The package preserves ``workspace/...`` paths so the archive can be copied into
the project root by a reproducer.
"""

from __future__ import annotations

import argparse
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ZENODO_PLACEHOLDER_URL = "https://zenodo.org/records/0000000"
EVALUATION_EXPERIMENTS = ("tctracer-2020", "tctracer-2022", "testlinker", "t2plinker")

MAIN_EXPERIMENT_PATHS = (
    "callgraph",
    "class",
    "method",
    "method-code",
    "method-history",
    "project.csv",
    "t2p-link/nc",
    "t2p-link/omc",
    "t2p-link/omc--nc",
    "test-smell/jnose/omc--nc",
)

T2PLINKER_PATHS = (
    "t2p-link/combined",
    "t2p-link/lc",
    "t2p-link/lcba",
    "t2p-link/lcs-b",
    "t2p-link/lcs-u",
    "t2p-link/leven",
    "t2p-link/nc",
    "t2p-link/ncc",
    "t2p-link/omc",
    "t2p-link/omc--nc",
    "t2p-link/testlinkerv2",
    "t2p-link/tfidf",
    "t2p-link/tarantula",
    "t2p-tech",
    "testlinker/output/codet5/testlinkerv2",
)

EVALUATION_EXPERIMENT_PATHS = (
    "callgraph",
    "class",
    "method",
    "method-code",
    "project.csv",
    "t2p-link/combined",
    "t2p-link/lc",
    "t2p-link/lcba",
    "t2p-link/lcs-b",
    "t2p-link/lcs-u",
    "t2p-link/leven",
    "t2p-link/nc",
    "t2p-link/ncc",
    "t2p-link/omc",
    "t2p-link/omc--nc",
    "t2p-link/tarantula",
    "t2p-link/testlinkerv2",
    "t2p-link/tfidf",
    "t2p-tech",
    "testlinker/output/codet5/testlinkerv2",
)

EXCLUDED_NAMES = {
    ".DS_Store",
    ".pytest_cache",
    "__pycache__",
}


@dataclass(frozen=True)
class CopyResult:
    source: Path
    destination: Path
    status: str


def sanitized_env_content() -> str:
    return """PROJECT_DIRECTORY=/path/to/method-co-evolution
ME_PROJECT_DIRECTORY=${PROJECT_DIRECTORY}
ME_WORKSPACE_DIRECTORY=${PROJECT_DIRECTORY}/workspace

ME_EXPERIMENT_NAME=main
ME_REPLACE=false
ME_TOOLS=historyFinder
ME_SMELL_DETECTOR=jnose
ME_STRATEGIES=omc--nc
ME_ARTIFACTS=main-code,test-code,test-case-method
ME_REVISION_TYPES=ch_diff
ME_PROJECT_INDEX=:
ME_PROJECTS=:
ME_MIN_T2P_LINKS=30
ME_EXPERIMENT_FILTERS_ENABLED=false
ME_EVALUATION_EXPERIMENTS_NAMES=tctracer-2020,tctracer-2022,testlinker,t2plinker

GITHUB_API_KEY=
HF_TOKEN=
OPENAI_API_KEY=
"""


def iter_package_paths() -> Iterable[Path]:
    for relative_path in MAIN_EXPERIMENT_PATHS:
        yield Path("workspace") / "experiment" / "main" / relative_path
    for relative_path in T2PLINKER_PATHS:
        yield Path("workspace") / "experiment" / "t2plinker" / relative_path
    for experiment in EVALUATION_EXPERIMENTS:
        for relative_path in EVALUATION_EXPERIMENT_PATHS:
            yield Path("workspace") / "experiment" / experiment / relative_path


def should_ignore(path: Path) -> bool:
    return path.name in EXCLUDED_NAMES or path.name.endswith((".pyc", ".pyo"))


def copy_file(source: Path, destination: Path, *, replace: bool, dry_run: bool) -> CopyResult:
    if not source.exists():
        return CopyResult(source, destination, "missing")
    if dry_run:
        return CopyResult(source, destination, "planned")
    if destination.exists() and not replace:
        return CopyResult(source, destination, "skipped")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return CopyResult(source, destination, "copied")


def copy_tree(source: Path, destination: Path, *, replace: bool, dry_run: bool) -> CopyResult:
    if not source.exists():
        return CopyResult(source, destination, "missing")
    if dry_run:
        return CopyResult(source, destination, "planned")
    if destination.exists() and not replace:
        return CopyResult(source, destination, "skipped")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination, ignore=ignore_names)
    return CopyResult(source, destination, "copied")


def ignore_names(directory: str, names: list[str]) -> set[str]:
    del directory
    return {name for name in names if should_ignore(Path(name))}


def write_text_file(path: Path, content: str, *, replace: bool, dry_run: bool) -> CopyResult:
    source = Path("<generated>")
    if dry_run:
        return CopyResult(source, path, "planned")
    if path.exists() and not replace:
        return CopyResult(source, path, "skipped")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return CopyResult(source, path, "written")


def create_package(
    project_directory: Path,
    output_directory: Path,
    github_url: str,
    *,
    replace: bool = False,
    dry_run: bool = False,
) -> list[CopyResult]:
    del github_url
    project_root = project_directory.expanduser().resolve()
    output_root = output_directory.expanduser().resolve()
    if output_root == project_root:
        raise ValueError(
            "output directory resolves to the project root. "
            "Use a package subdirectory such as PROJECT_DIRECTORY/workspace/replication-package."
        )
    if output_root == project_root / "workspace":
        raise ValueError(
            "output directory resolves to the workspace root. "
            "Use a package subdirectory such as PROJECT_DIRECTORY/workspace/replication-package."
        )

    if output_root.exists() and replace and not dry_run:
        shutil.rmtree(output_root)

    results: list[CopyResult] = []
    results.append(write_text_file(output_root / ".env", sanitized_env_content(), replace=replace, dry_run=dry_run))

    readme_source = project_root / "replication-package.md"
    results.append(
        copy_file(
            readme_source,
            output_root / "replication-package.md",
            replace=replace,
            dry_run=dry_run,
        )
    )

    for relative_path in sorted(set(iter_package_paths())):
        source = project_root / relative_path
        destination = output_root / relative_path
        if source.is_dir():
            result = copy_tree(source, destination, replace=replace, dry_run=dry_run)
        else:
            result = copy_file(source, destination, replace=replace, dry_run=dry_run)
        results.append(result)
        print(f"{result.status}: {result.source} -> {result.destination}")

    print_summary(results)
    return results


def print_summary(results: Iterable[CopyResult]) -> None:
    result_list = list(results)
    statuses = ("copied", "written", "planned", "skipped", "missing")
    counts = {status: sum(result.status == status for result in result_list) for status in statuses}
    print()
    print(
        "Total: "
        + ", ".join(f"{status}={count}" for status, count in counts.items() if count)
    )
    missing = [result for result in result_list if result.status == "missing"]
    if missing:
        print()
        print("Missing inputs:")
        for result in missing:
            print(f"  {result.source}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create the Zenodo replication package directory.")
    parser.add_argument(
        "github_url",
        help="Public or anonymous GitHub repository URL. The script records this URL but does not clone it.",
    )
    parser.add_argument(
        "--output-directory",
        default=None,
        help="Package output directory. Defaults to workspace/replication-package.",
    )
    parser.add_argument("--replace", action="store_true", help="Overwrite an existing package output directory.")
    parser.add_argument("--dry-run", action="store_true", help="Report planned package contents without copying.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_directory = Path.cwd()
    output_directory = (
        Path(args.output_directory)
        if args.output_directory
        else Path("workspace") / "replication-package"
    )

    print(f"Project directory: {project_directory.expanduser().resolve()}")
    print(f"Output directory: {output_directory.expanduser().resolve()}")
    if args.dry_run:
        print("Dry-run: no files will be copied")
    print()

    try:
        create_package(
            project_directory,
            output_directory,
            args.github_url,
            replace=args.replace,
            dry_run=args.dry_run,
        )
    except ValueError as exc:
        parser.error(str(exc))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
