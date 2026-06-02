import argparse
import os
import sys
from pathlib import Path
from mhc import config
from mhc.method_history_collector import *
from mhc.method_history_jar_runner import DEFAULT_MERGE_THRESHOLD
from mhc.util import parse_project_index

_DASH_VALUE_OPTIONS = {"--java-options", "--command-options"}
_KNOWN_OPTION_FLAGS = {
    "--workspace-directory",
    "--history-directory",
    "--repository-directory",
    "--jar-directory",
    "--experiment-name",
    "--tool-name",
    "--command-options",
    "--java-options",
    "--timeout-seconds",
    "--merge-threshold",
    "--merge-interval-seconds",
    "--max-cache-size",
    "--merge-only",
    "--project",
    "--projects",
    "--project-index",
    "--shards",
    "--shard",
    "--replace",
    "--retry-errors",
    "--artifact-config-path",
    "--target",
    "--dry-run",
    "--backup",
    "--stage",
    "--callgraph-dir",
    "--max-workers",
    "--init-reset-interval-files",
}


def _parse_bool(value: str | bool) -> bool:
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected a boolean value: true or false")


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
    workspace_directory: str,
    experiment_directory: str,
    repository_directory: str,
    jar_directory: str,
    history_directory: str | None = None,
) -> MethodHistoryCollector:
    return MethodHistoryCollector(
        workspace_directory,
        experiment_directory,
        repository_directory,
        jar_directory,
        history_directory,
    )


def _parse_projects_csv(projects: str | None) -> list[str]:
    if not projects:
        return []
    return [project.strip() for project in projects.split(",") if project.strip()]


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
        return parse_project_index(project_index, candidate_projects)
    if project is not None or projects is not None:
        return candidate_projects
    raise ValueError("exactly one of --project, --projects, or --project-index is required")


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description="Method History Collector (MHC)")

    parser.add_argument(
        "command", type=str, help="Command to execute (e.g., method-history, method-callgraph)"
    )
    parser.add_argument(
        "--workspace-directory",
        type=str,
        required=True,
        help="Shared workspace root. Experiment outputs default to <workspace-directory>/experiment/<experiment>.",
    )
    parser.add_argument(
        "--experiment-name",
        type=str,
        default=None,
        help="Experiment name. Defaults to ME_EXPERIMENT_NAME.",
    )
    parser.add_argument(
        "--repository-directory",
        type=str,
        default=None,
        help="Repository directory path. Defaults to <workspace-directory>/experiment/<experiment>/repository.",
    )
    parser.add_argument(
        "--history-directory",
        type=str,
        help="Method history JSON/archive directory path. Defaults to <workspace-directory>/experiment/<experiment>/history.",
    )
    parser.add_argument(
        "--jar-directory",
        type=str,
        default=None,
        help="Jar directory path. Defaults to <workspace-directory>/jar.",
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
            "History: number of unarchived JSON files before merging into tar.gz. "
            "For history, 0 disables intermediate merging and negative values disable final merging too. "
            "Scan/code commands: pending cache rows before flushing. "
            "Default: 10000. For scan/code commands, 0 or negative disables threshold-triggered intermediate flushes."
        ),
    )
    parser.add_argument(
        "--merge-interval-seconds",
        dest="merge_interval_seconds",
        type=int,
        default=15 * 60,
        help=(
            "For method-scan, class-scan, method-code, and method-callgraph, flush pending cache rows after this many seconds "
            "(default: 900; 0 or negative disables time-triggered intermediate flushes)."
        ),
    )
    parser.add_argument(
        "--max-cache-size",
        dest="max_cache_size",
        type=int,
        default=256,
        help="Generic in-memory cache budget in MB for supported long-running commands (default: 256; 0 disables optional caches).",
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
        help="Python-style project index or slice from project.csv, for example '10', '-1', '10:20', ':10', '10:', or ':'.",
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
    parser.add_argument(
        "--retry-errors",
        dest="retry_errors",
        nargs="?",
        const=True,
        default=True,
        type=_parse_bool,
        help="Retry rows/files previously marked with __error_marker__ (default: true). Use '--retry-errors false' to skip them.",
    )
    parser.add_argument(
        "--enable-symbol-solver",
        dest="enable_symbol_solver",
        nargs="?",
        const=True,
        default=True,
        type=_parse_bool,
        help=(
            "Whether supported commands use JavaParser symbol resolution for FQN/FQS "
            "(default: true). For method-scan, use '--enable-symbol-solver false' for faster heuristic signatures."
        ),
    )
    parser.add_argument(
        "--cache-evict-interval-seconds",
        dest="cache_evict_interval_seconds",
        type=int,
        default=0,
        help="For method-scan, evict JavaParser caches after this many seconds (default: 0 disables time-based eviction).",
    )
    parser.add_argument(
        "--cache-evict-interval-files",
        dest="cache_evict_interval_files",
        type=int,
        default=0,
        help="For method-scan, evict JavaParser caches after this many completed files (default: 0 disables file-count eviction).",
    )
    parser.add_argument(
        "--init-reset-interval-files",
        dest="init_reset_interval_files",
        type=int,
        default=2000,
        help=(
            "For method-scan and method-callgraph, recreate each thread's Java scanner instance after this "
            "many files to reset JavaParser/type-solver state. 0 disables init resets. Default: 2000."
        ),
    )
    parser.add_argument(
        "--artifact-config-path",
        dest="artifact_config_path",
        type=str,
        help="Artifact detection YAML file or directory.",
    )
    parser.add_argument(
        "--target",
        dest="target",
        type=str,
        default="method,class",
        help="Comma-separated artifact-update targets. Supported: method,class.",
    )
    parser.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_true",
        help="Preview artifact-update changes without writing CSV files.",
    )
    parser.add_argument(
        "--backup",
        dest="backup",
        action="store_true",
        help="Create bk_<project>.csv files before artifact-update writes outputs.",
    )
    parser.add_argument(
        "--stage",
        dest="stage",
        choices=("preprocess", "execute", "postprocess", "all"),
        default="all",
        help="Pipeline stage for staged commands such as test-smell.",
    )
    parser.add_argument(
        "--callgraph-dir",
        dest="callgraph_dir",
        type=str,
        default="callgraph",
        help="Callgraph-like directory under the experiment directory used by test-smell preprocessing.",
    )
    parser.add_argument(
        "--max-workers",
        dest="max_workers",
        type=int,
        default=1,
        help="Maximum number of parallel worker threads for supported commands (default: 1).",
    )
    normalized_argv = _normalize_dash_prefixed_option_values(
        list(sys.argv[1:] if argv is None else argv)
    )
    args = parser.parse_args(normalized_argv)
    try:
        experiment_name = config.resolve_experiment_name(args.experiment_name)
    except ValueError as exc:
        parser.error(str(exc))
    workspace_directory = str(Path(args.workspace_directory))
    experiment_directory = str(config.resolve_experiment_directory(workspace_directory, experiment_name))
    repository_directory = str(
        config.resolve_repository_directory(workspace_directory, experiment_name, args.repository_directory)
    )
    history_directory = str(
        config.resolve_history_directory(workspace_directory, experiment_name, args.history_directory)
    )
    jar_directory = str(config.resolve_jar_directory(workspace_directory, args.jar_directory))

    mhc = _build_method_history_collector(
        workspace_directory,
        experiment_directory,
        repository_directory,
        jar_directory,
        history_directory,
    )
    if args.shards <= 0:
        print("Error: --shards must be positive.")
        sys.exit(1)
    if args.shard <= 0 or args.shard > args.shards:
        print("Error: --shard must be between 1 and --shards.")
        sys.exit(1)
    if args.max_workers <= 0:
        print("Error: --max-workers must be positive.")
        sys.exit(1)
    if args.cache_evict_interval_seconds < 0:
        print("Error: --cache-evict-interval-seconds must be non-negative.")
        sys.exit(1)
    if args.cache_evict_interval_files < 0:
        print("Error: --cache-evict-interval-files must be non-negative.")
        sys.exit(1)
    if args.init_reset_interval_files < 0:
        print("Error: --init-reset-interval-files must be non-negative.")
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
            args.max_workers,
        )
    elif command in ("method-callgraph", "call-graph"):
        if not args.tool_name:
            print(
                "Error: tool_name is required for call graph command."
            )
            sys.exit(1)
        call_args = [
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
            args.retry_errors,
            args.merge_threshold,
            args.merge_interval_seconds,
            args.max_cache_size,
            args.max_workers,
        ]
        if args.artifact_config_path:
            call_args.append(args.artifact_config_path)
        else:
            call_args.append(None)
        call_args.append(args.init_reset_interval_files)
        mhc.generate_callgraph(*call_args)
    elif command in ("class-scan", "scan-class"):
        call_args = [
            resolve_selected_projects(),
            args.java_options,
            args.replace,
            args.shards,
            args.shard,
            args.merge_only is not None,
            "delete-empty" in (args.merge_only or []),
            "delete-tmp" in (args.merge_only or []),
            "delete-lock" in (args.merge_only or []),
            args.retry_errors,
            args.merge_threshold,
            args.merge_interval_seconds,
            args.max_workers,
        ]
        if args.artifact_config_path:
            call_args.append(args.artifact_config_path)
        mhc.scan_class(*call_args)
    elif command in ("method-scan", "scan-method"):
        call_args = [
            resolve_selected_projects(),
            args.java_options,
            args.replace,
            args.shards,
            args.shard,
            args.merge_only is not None,
            "delete-empty" in (args.merge_only or []),
            "delete-tmp" in (args.merge_only or []),
            "delete-lock" in (args.merge_only or []),
            args.retry_errors,
            args.merge_threshold,
            args.merge_interval_seconds,
            args.max_workers,
        ]
        if args.artifact_config_path:
            call_args.append(args.artifact_config_path)
        else:
            call_args.append(None)
        call_args.append(args.enable_symbol_solver)
        call_args.append(args.cache_evict_interval_seconds)
        call_args.append(args.cache_evict_interval_files)
        call_args.append(args.init_reset_interval_files)
        mhc.scan_method(*call_args)
    elif command in ("artifact-update", "update-artifacts"):
        mhc.update_artifacts(
            resolve_selected_projects(),
            args.java_options,
            args.artifact_config_path,
            [target.strip() for target in args.target.split(",") if target.strip()],
            args.dry_run,
            args.backup,
            args.replace,
            args.max_workers,
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
            args.retry_errors,
            args.merge_threshold,
            args.merge_interval_seconds,
            args.max_workers,
        )
    elif command == "index":
        mhc.update_repository_index()
    elif command == "method-complexity":
        if not args.tool_name:
            print(
                "Error: tool_name is required for method-complexity command."
            )
            sys.exit(1)
        mhc.run_complexity_analyzer(resolve_selected_projects(), args.tool_name)
    elif command == "test-smell":
        if not args.tool_name:
            print("Error: tool_name is required for test-smell command.")
            sys.exit(1)
        mhc.run_test_smell(
            resolve_selected_projects(),
            args.tool_name,
            args.stage,
            args.callgraph_dir,
            args.max_workers,
        )
    else:
        print(f"Unknown command: {args.command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
