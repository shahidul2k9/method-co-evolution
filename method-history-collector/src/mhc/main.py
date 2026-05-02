import argparse
import sys
from mhc.method_history_collector import *
from mhc.method_history_jar_runner import DEFAULT_MERGE_THRESHOLD

_DASH_VALUE_OPTIONS = {"--java-options", "--command-options"}
_KNOWN_OPTION_FLAGS = {
    "--cache-directory",
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
    "--project-range",
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
) -> MethodHistoryCollector:
    return MethodHistoryCollector(
        cache_directory,
        repository_directory,
        data_directory,
        jar_directory,
    )


def _parse_projects_csv(projects: str | None) -> list[str]:
    if not projects:
        return []
    return [project.strip() for project in projects.split(",") if project.strip()]


def _parse_project_range(project_range: str | None, known_projects: list[str]) -> list[str]:
    if not project_range:
        return []
    if ":" not in project_range:
        raise ValueError("project-range must use 1-based inclusive indexes like 10:20, :20, 10:, or :")

    start_text, end_text = project_range.split(":", maxsplit=1)
    start_index = int(start_text) if start_text else 1
    end_index = int(end_text) if end_text else len(known_projects)

    if start_index <= 0 or end_index <= 0 or start_index > end_index:
        raise ValueError("project-range must use 1-based inclusive indexes like 10:20, :20, 10:, or :")
    if end_index > len(known_projects):
        raise ValueError(
            f"project-range end {end_index} exceeds repository count {len(known_projects)}"
        )
    return known_projects[start_index - 1:end_index]


def _resolve_projects(
    project: str | None,
    projects: str | None,
    project_range: str | None,
    known_projects: list[str],
) -> list[str]:
    provided_selection_count = sum(
        value is not None for value in (project, projects, project_range)
    )
    if provided_selection_count != 1:
        raise ValueError("exactly one of --project, --projects, or --project-range is required")

    if project is not None:
        return [project]
    if projects is not None:
        return _parse_projects_csv(projects)
    return _parse_project_range(project_range, known_projects)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Method History Collector (MHC)")

    parser.add_argument(
        "command", type=str, help="Command to execute (e.g., history, call-graph)"
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

    # Conditional args for history command
    parser.add_argument(
        "--tool-name", dest="tool_name", type=str, help="Tool name (required for history command)"
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
            "For history command, merge existing loose history JSON files without generating new history. "
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
        "--project-range",
        dest="project_range",
        type=str,
        help="1-based inclusive project index range from repository.csv, for example '10:20'.",
    )
    parser.add_argument(
        "--shards",
        dest="shards",
        type=int,
        default=1,
        help="Total number of method-history shards to split work into (default: 1).",
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
        help="Regenerate outputs even when existing output/cache files are present. Supported by scan-method and call-graph.",
    )

    normalized_argv = _normalize_dash_prefixed_option_values(
        list(sys.argv[1:] if argv is None else argv)
    )
    args = parser.parse_args(normalized_argv)

    mhc = _build_method_history_collector(
        args.cache_directory,
        args.repository_directory,
        args.data_directory,
        args.jar_directory,
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
                args.project_range,
                repository_projects,
            )
        except ValueError as exc:
            print(f"Error: {exc}")
            sys.exit(1)

    if args.command.lower() == "history":
        if not args.tool_name:
            print(
                "Error: tool_name is required for history command."
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
    elif args.command.lower() == "call-graph":
        if not args.tool_name:
            print(
                "Error: tool_name is required for call graph command."
            )
            sys.exit(1)
        mhc.generate_call_graph(resolve_selected_projects(), [args.tool_name], args.replace, args.java_options)
    elif args.command.lower() == "scan-method":
        mhc.scan_method(resolve_selected_projects(), args.java_options, args.replace)
    elif args.command.lower() == "method-code":
        mhc.generate_method_code(resolve_selected_projects())
    elif args.command.lower() == "index":
        mhc.update_repository_index()
    elif args.command.lower() == "complexity-analyzer":
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
