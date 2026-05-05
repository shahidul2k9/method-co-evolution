import argparse
import os
import sys
from mhc.method_history_collector import *
from mhc.method_history_jar_runner import DEFAULT_MERGE_THRESHOLD

_DASH_VALUE_OPTIONS = {"--java-options", "--command-options"}
_KNOWN_OPTION_FLAGS = {
    "--cache-directory",
    "--history-directory",
    "--repository-directory",
    "--data-directory",
    "--jar-directory",
    "--tool-name",
    "--command-options",
    "--java-options",
    "--timeout-seconds",
    "--merge-threshold",
    "--merge-only",
    "--project",
    "--projects",
    "--project-index",
    "--shards",
    "--shard",
}


def _normalize_dash_prefixed_option_values(argv: list[str]) -> list[str]:
    normalized_argv = []
    index = 0

    while index < len(argv):
        token = argv[index]
        if (
            token in _DASH_VALUE_OPTIONS
            and index + 1 < len(argv)
            and argv[index + 1].startswith("-")
            and argv[index + 1] != "--"
            and argv[index + 1] not in _KNOWN_OPTION_FLAGS
        ):
            normalized_argv.append(f"{token}={argv[index + 1]}")
            index += 2
            continue

        normalized_argv.append(token)
        index += 1

    return normalized_argv


def _build_method_history_collector(
    cache_directory: str,
    repository_directory: str,
    data_directory: str,
    jar_directory: str,
    history_directory: str | None = None,
) -> MethodHistoryCollector:
    return MethodHistoryCollector(
        cache_directory,
        repository_directory,
        data_directory,
        jar_directory,
        history_directory,
    )


def _parse_projects_csv(projects: str | None) -> list[str]:
    if not projects:
        return []
    return [project.strip() for project in projects.split(",") if project.strip()]


def _parse_project_index(project_index: str | None, known_projects: list[str]) -> list[str]:
    if not project_index:
        return []

    if ":" not in project_index:
        try:
            return [known_projects[int(project_index)]]
        except (ValueError, IndexError):
            raise ValueError(
                "project-index must use Python-style indexes or slices like 10, -1, 10:20, :10, 10:, or :"
            )

    if project_index.count(":") != 1:
        raise ValueError(
            "project-index must use Python-style indexes or slices like 10, -1, 10:20, :10, 10:, or :"
        )

    start_text, end_text = project_index.split(":", maxsplit=1)
    try:
        start_index = int(start_text) if start_text else None
        end_index = int(end_text) if end_text else None
    except ValueError:
        raise ValueError(
            "project-index must use Python-style indexes or slices like 10, -1, 10:20, :10, 10:, or :"
        )
    return known_projects[start_index:end_index]


def _resolve_projects(
    project: str | None,
    projects: str | None,
    project_index: str | None,
    known_projects: list[str],
) -> list[str]:
    if project is not None and projects is not None:
        raise ValueError("use either --project or --projects, not both")

    if project is not None:
        candidate_projects = [project]
    elif projects is not None:
        candidate_projects = _parse_projects_csv(projects)
    else:
        candidate_projects = known_projects

    if project_index is not None:
        return _parse_project_index(project_index, candidate_projects)
    if project is not None or projects is not None:
        return candidate_projects
    raise ValueError("exactly one of --project, --projects, or --project-index is required")


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Method History Collector (MHC)")

    parser.add_argument(
        "command", type=str, help="Command to execute (e.g., method-history, method-callgraph)"
    )
    parser.add_argument(
        "--cache-directory",
        type=str,
        required=True,
        help="Cache directory path"
    )
    parser.add_argument(
        "--repository-directory",
        type=str,
        required=True,
        help="Repository directory path",
    )
    parser.add_argument(
        "--history-directory",
        type=str,
        help="Method history JSON/archive directory path. Defaults to ME_HISTORY_DIRECTORY or <cache-directory>/history.",
    )
    parser.add_argument(
        "--data-directory",
        type=str,
        required=True,
        help="Data directory path"
    )
    parser.add_argument(
        "--jar-directory",
        type=str,
        required=True,
        help="Jar directory path"
    )

    # Conditional args for long-running project commands
    parser.add_argument(
        "--tool-name", dest="tool_name", type=str, help="Tool name (required for tool-backed commands)"
    )
    parser.add_argument(
        "--command-options",
        dest="command_options",
        type=str,
        help="Optional extra arguments forwarded to the underlying command or jar.",
    )
    parser.add_argument(
        "--java-options",
        dest="java_options",
        type=str,
        help="Optional JVM arguments passed before -jar, for example '-Xmx4g'.",
    )
    parser.add_argument(
        "--timeout-seconds",
        dest="timeout_seconds",
        type=int,
        default=30 * 60,
        help="Subprocess timeout in seconds for history jar execution (default: 1800).",
    )
    parser.add_argument(
        "--merge-threshold",
        dest="merge_threshold",
        type=int,
        default=DEFAULT_MERGE_THRESHOLD,
        help=(
            "Number of unarchived history JSON files to accumulate before merging into tar.gz "
            "(default: 10000; 0 disables intermediate merging; negative values disable final merging too)."
        ),
    )
    parser.add_argument(
        "--merge-only",
        dest="merge_only",
        nargs="*",
        choices=("delete-empty", "delete-tmp", "delete-lock"),
        help=(
            "For method-history, merge existing loose history JSON files without generating new history. "
            "For method-callgraph, finalize shared callgraph cache into callgraph/fanin CSVs. "
            "Optional cleanup modes: delete-empty, delete-tmp, delete-lock."
        ),
    )
    parser.add_argument(
        "--project",
        dest="project",
        type=str,
        help="Project name (required for project-scoped commands)",
    )
    parser.add_argument(
        "--projects",
        dest="projects",
        type=str,
        help="Comma-separated project names.",
    )
    parser.add_argument(
        "--project-index",
        dest="project_index",
        type=str,
        help="Python-style project index or slice from repository.csv, for example '10', '-1', '10:20', ':10', '10:', or ':'.",
    )
    parser.add_argument(
        "--shards",
        dest="shards",
        type=int,
        default=1,
        help="Total number of method-history, method-scan, class-scan, method-code, or method-callgraph shards to split work into (default: 1).",
    )
    parser.add_argument(
        "--shard",
        dest="shard",
        type=int,
        default=1,
        help="1-based shard number to run for history collection (default: 1).",
    )
    parser.add_argument(
        "--replace",
        dest="replace",
        action="store_true",
        help="Regenerate outputs even when existing output/cache files are present. Supported by method-scan and method-callgraph.",
    )

    normalized_argv = _normalize_dash_prefixed_option_values(
        list(sys.argv[1:] if argv is None else argv)
    )
    args = parser.parse_args(normalized_argv)
    history_directory = args.history_directory or os.environ.get(
        "ME_HISTORY_DIRECTORY",
        os.path.join(args.cache_directory, "history"),
    )

    mhc = _build_method_history_collector(
        args.cache_directory,
        args.repository_directory,
        args.data_directory,
        args.jar_directory,
        history_directory,
    )
    if args.shards <= 0:
        print("Error: --shards must be positive.")
        sys.exit(1)
    if args.shard <= 0 or args.shard > args.shards:
        print("Error: --shard must be between 1 and --shards.")
        sys.exit(1)
    repository_projects = mhc.repository_df["project"].tolist()

    def resolve_selected_projects() -> list[str]:
        try:
            return _resolve_projects(
                args.project,
                args.projects,
                args.project_index,
                repository_projects,
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)

    command = args.command.lower()
    if command == "history":
        command = "method-history"

    if command == "method-history":
        if not args.tool_name:
            print(
                "Error: tool_name is required for method-history command."
            )
            sys.exit(1)
        mhc.collect_method_history(
            resolve_selected_projects(),
            [args.tool_name],
            args.command_options,
            args.java_options,
            args.timeout_seconds,
            args.shards,
            args.shard,
            args.merge_threshold,
            args.merge_only is not None,
            "delete-empty" in (args.merge_only or []),
            "delete-tmp" in (args.merge_only or []),
            "delete-lock" in (args.merge_only or []),
        )
    elif command in ("method-callgraph", "call-graph"):
        if not args.tool_name:
            print(
                "Error: tool_name is required for call graph command."
            )
            sys.exit(1)
        mhc.generate_callgraph(
            resolve_selected_projects(),
            [args.tool_name],
            args.replace,
            args.java_options,
            args.shards,
            args.shard,
            args.merge_only is not None,
            "delete-empty" in (args.merge_only or []),
            "delete-tmp" in (args.merge_only or []),
            "delete-lock" in (args.merge_only or []),
        )
    elif command in ("class-scan", "scan-class"):
        mhc.scan_class(
            resolve_selected_projects(),
            args.java_options,
            args.replace,
            args.shards,
            args.shard,
            args.merge_only is not None,
            "delete-empty" in (args.merge_only or []),
            "delete-tmp" in (args.merge_only or []),
            "delete-lock" in (args.merge_only or []),
        )
    elif command in ("method-scan", "scan-method"):
        mhc.scan_method(
            resolve_selected_projects(),
            args.java_options,
            args.replace,
            args.shards,
            args.shard,
            args.merge_only is not None,
            "delete-empty" in (args.merge_only or []),
            "delete-tmp" in (args.merge_only or []),
            "delete-lock" in (args.merge_only or []),
        )
    elif command == "method-code":
        mhc.generate_method_code(
            resolve_selected_projects(),
            args.shards,
            args.shard,
            args.replace,
            args.merge_only is not None,
            "delete-empty" in (args.merge_only or []),
            "delete-tmp" in (args.merge_only or []),
            "delete-lock" in (args.merge_only or []),
        )
    elif command == "index":
        mhc.update_repository_index()
    elif command == "complexity-analyzer":
        if not args.tool_name:
            print(
                "Error: tool_name is required for complexity analyzer command."
            )
            sys.exit(1)
        mhc.run_complexity_analyzer(resolve_selected_projects(), args.tool_name)
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
