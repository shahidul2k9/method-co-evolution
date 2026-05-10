import argparse
import re
import shlex
import sys
from dataclasses import dataclass
from pathlib import Path

import pandas as pd


_COMMAND_ALIASES = {
    "history": "method-history",
    "call-graph": "method-callgraph",
    "scan-method": "method-scan",
    "scan-class": "class-scan",
}
_SLURM_ARRAY_MAX_INDEX = 9999

_ARRAY_RE = re.compile(r"--array=(\S+)")
_JOB_INDEX_SHIFT_RE = re.compile(r"--job-index-shift(?:\s+\S+|=\S+)")
_SPACED_RE = re.compile(r"--(?P<key>shards|command|workspace-directory|tool-name|job-index-shift)\s+(\S+)")
_EQUALS_RE = re.compile(r"--(?P<key>shards|command|workspace-directory|tool-name|job-index-shift)=(\S+)")


@dataclass
class ProcessResult:
    command: str
    shards: int
    requested_index_ranges: list[tuple[int, int]]
    converted_task_groups: list[tuple[int, int]]
    repository_valid_index_ranges: list[tuple[int, int]]
    repository_excluded_index_ranges: list[tuple[int, int]]
    completed_excluded_index_ranges: list[tuple[int, int]]
    cluster_limit_excluded_index_ranges: list[tuple[int, int]]
    final_index_ranges: list[tuple[int, int]]
    final_logical_task_groups: list[tuple[int, int]]
    final_submitted_task_groups: list[tuple[int, int]]
    job_index_shift: int
    repository_truncated: bool
    task_truncated: bool


def _parse_arg(text: str, key: str) -> str | None:
    for pattern in (_SPACED_RE, _EQUALS_RE):
        for m in pattern.finditer(text):
            if m.group("key") == key:
                return m.group(2)
    return None


def _parse_index_ranges(array_str: str) -> list[tuple[int, int]]:
    """Parse a comma-separated list of project indices or index ranges.

    '0,10-15,22' -> [(0,0), (10,15), (22,22)]
    """
    result = []
    for part in array_str.split(","):
        part = part.strip()
        if "-" in part:
            start, end = part.split("-", 1)
            result.append((int(start), int(end)))
        else:
            result.append((int(part), int(part)))
    return result


def _expand_indices(index_ranges: list[tuple[int, int]]) -> list[int]:
    """Expand index ranges to a flat sorted list of individual project indices."""
    indices = []
    for start, end in index_ranges:
        indices.extend(range(start, end + 1))
    return indices


def _group_consecutive(indices: list[int]) -> list[tuple[int, int]]:
    """Re-group a sorted list of project indices into contiguous ranges."""
    if not indices:
        return []
    groups = []
    start = prev = indices[0]
    for idx in indices[1:]:
        if idx == prev + 1:
            prev = idx
        else:
            groups.append((start, prev))
            start = prev = idx
    groups.append((start, prev))
    return groups


def _indices_to_task_ranges(index_groups: list[tuple[int, int]], shards: int) -> list[str]:
    """Convert project index groups to Slurm task ID range strings.

    Each project index i covers task IDs [i*shards, (i+1)*shards - 1].
    A group (a, b) of consecutive indices covers [a*shards, (b+1)*shards - 1].
    """
    result = []
    for task_start, task_end in _indices_to_task_groups(index_groups, shards):
        result.append(f"{task_start}-{task_end}")
    return result


def _indices_to_task_groups(index_groups: list[tuple[int, int]], shards: int) -> list[tuple[int, int]]:
    """Convert project index groups to Slurm task ID range tuples."""
    result = []
    for start_idx, end_idx in index_groups:
        task_start = start_idx * shards
        task_end = (end_idx + 1) * shards - 1
        result.append((task_start, task_end))
    return result


def _format_task_ranges(task_groups: list[tuple[int, int]]) -> str:
    return ",".join(f"{start}-{end}" if start != end else str(start) for start, end in task_groups)


def _format_index_ranges(index_groups: list[tuple[int, int]]) -> str:
    if not index_groups:
        return "(none)"
    return ",".join(f"{start}-{end}" if start != end else str(start) for start, end in index_groups)


def _task_groups_to_project_indices(task_groups: list[tuple[int, int]], shards: int) -> list[int]:
    projects = set()
    for start, end in task_groups:
        projects.update(range(start // shards, end // shards + 1))
    return sorted(projects)


def _subtract_indices(requested: list[int], included: list[int]) -> list[int]:
    included_set = set(included)
    return [idx for idx in requested if idx not in included_set]


def _task_groups_to_partial_project_labels(task_groups: list[tuple[int, int]], shards: int) -> list[str]:
    shard_ranges_by_project: dict[int, list[tuple[int, int]]] = {}
    for start, end in task_groups:
        for project_index in range(start // shards, end // shards + 1):
            project_start_task = project_index * shards
            project_end_task = project_start_task + shards - 1
            shard_start = max(start, project_start_task) - project_start_task + 1
            shard_end = min(end, project_end_task) - project_start_task + 1
            shard_ranges_by_project.setdefault(project_index, []).append((shard_start, shard_end))

    labels = []
    for project_index, shard_ranges in sorted(shard_ranges_by_project.items()):
        shard_indices = []
        for start, end in shard_ranges:
            shard_indices.extend(range(start, end + 1))
        shard_groups = _group_consecutive(sorted(set(shard_indices)))
        if shard_groups != [(1, shards)]:
            missing_shards = _subtract_indices(list(range(1, shards + 1)), shard_indices)
            missing_groups = _group_consecutive(missing_shards)
            labels.append(
                f"{project_index}(included shards {_format_index_ranges(shard_groups)}; "
                f"excluded shards {_format_index_ranges(missing_groups)} of {shards})"
            )
    return labels


def _shift_task_groups(task_groups: list[tuple[int, int]]) -> tuple[list[tuple[int, int]], int]:
    """Shift task IDs down when needed to satisfy Nibi's 0-9999 array index limit."""
    max_task_id = max(end for _, end in task_groups)
    if max_task_id <= _SLURM_ARRAY_MAX_INDEX:
        return task_groups, 0

    shift = min(start for start, _ in task_groups)
    shifted_groups = [(start - shift, end - shift) for start, end in task_groups]
    shifted_max = max(end for _, end in shifted_groups)
    if shifted_max > _SLURM_ARRAY_MAX_INDEX:
        raise ValueError(
            "Expanded array task IDs exceed the 0-9999 limit even after shifting; "
            "submit a narrower project index range."
        )
    return shifted_groups, shift


def _truncate_task_groups_to_limit(
    task_groups: list[tuple[int, int]],
) -> tuple[list[tuple[int, int]], bool]:
    """Clip logical task groups to the largest submitted array span Nibi accepts."""
    shift = min(start for start, _ in task_groups)
    max_logical_task_id = shift + _SLURM_ARRAY_MAX_INDEX
    truncated_groups = []
    truncated = False
    for start, end in task_groups:
        if start > max_logical_task_id:
            truncated = True
            continue
        clipped_end = min(end, max_logical_task_id)
        truncated_groups.append((start, clipped_end))
        if clipped_end < end:
            truncated = True
    return truncated_groups, truncated


def _truncate_indices_to_repository(
    indices: list[int],
    repo_df: pd.DataFrame | None,
) -> tuple[list[int], bool]:
    if repo_df is None:
        return indices, False
    repo_count = len(repo_df)
    truncated_indices = [idx for idx in indices if 0 <= idx < repo_count]
    return truncated_indices, len(truncated_indices) != len(indices)


def _set_job_index_shift(text: str, shift: int) -> str:
    if shift <= 0:
        return _JOB_INDEX_SHIFT_RE.sub("", text, count=1)
    replacement = f"--job-index-shift {shift}"
    if _JOB_INDEX_SHIFT_RE.search(text):
        return _JOB_INDEX_SHIFT_RE.sub(replacement, text, count=1)
    return f"{text} {replacement}"


def _format_shell_command(text: str) -> str:
    parts = shlex.split(text)
    if not parts:
        return ""
    quoted_parts = [shlex.quote(part) for part in parts]
    if len(quoted_parts) == 1:
        return quoted_parts[0]
    return f" \\\n  ".join(quoted_parts)


def _load_repository(workspace_dir: str | Path) -> pd.DataFrame:
    path = Path(workspace_dir) / "data" / "repository" / "repository.csv"
    return pd.read_csv(path)


def _output_exists(command: str, workspace: str | Path, project: str, tool_name: str) -> bool:
    canonical = _COMMAND_ALIASES.get(command, command)
    base = Path(workspace)
    if canonical == "method-scan":
        return (base / "data" / "method" / f"{project}.csv").exists()
    if canonical == "method-callgraph":
        return (base / "data" / "callgraph" / f"{project}.csv").exists()
    if canonical == "method-history":
        return (base / "history" / tool_name / project).is_dir()
    if canonical == "method-code":
        return (base / "data" / "method-code" / f"{project}.csv").exists()
    return False


def process(
    text: str,
    repo_df: pd.DataFrame | None,
    replace: bool = False,
    workspace_override: str | None = None,
) -> str:
    return process_with_details(text, repo_df, replace=replace, workspace_override=workspace_override).command


def process_with_details(
    text: str,
    repo_df: pd.DataFrame | None,
    replace: bool = False,
    workspace_override: str | None = None,
) -> ProcessResult:
    array_match = _ARRAY_RE.search(text)
    if not array_match:
        raise ValueError("No --array= found in input")

    raw_shards = _parse_arg(text, "shards")
    if raw_shards is None:
        raise ValueError("No --shards found in input")
    shards = int(raw_shards)

    command = _parse_arg(text, "command")
    if command is None:
        raise ValueError("No --command found in input")

    workspace = workspace_override or _parse_arg(text, "workspace-directory")
    tool_name = _parse_arg(text, "tool-name") or ""

    index_ranges = _parse_index_ranges(array_match.group(1))
    requested_indices = _expand_indices(index_ranges)
    converted_task_groups = _indices_to_task_groups(_group_consecutive(requested_indices), shards)
    repository_indices, repository_truncated = _truncate_indices_to_repository(requested_indices, repo_df)
    repository_excluded_indices = _subtract_indices(requested_indices, repository_indices)

    if not replace and workspace is not None and repo_df is not None:
        indices = [
            idx for idx in repository_indices
            if not _output_exists(command, workspace, str(repo_df.iloc[idx]["project"]), tool_name)
        ]
        completed_excluded_indices = _subtract_indices(repository_indices, indices)
    else:
        indices = repository_indices
        completed_excluded_indices = []

    if not indices:
        raise ValueError("No indices remaining after filtering existing outputs")

    pre_limit_groups = _group_consecutive(indices)
    pre_limit_task_groups = _indices_to_task_groups(pre_limit_groups, shards)
    final_task_groups, task_truncated = _truncate_task_groups_to_limit(pre_limit_task_groups)
    if not final_task_groups:
        raise ValueError("No task IDs remaining after truncating to the 0-9999 Slurm array limit")
    included_indices = _task_groups_to_project_indices(final_task_groups, shards)
    cluster_limit_excluded_indices = _subtract_indices(indices, included_indices)
    shifted_groups, job_index_shift = _shift_task_groups(final_task_groups)
    new_array = _format_task_ranges(shifted_groups)
    updated_text = text[: array_match.start()] + f"--array={new_array}" + text[array_match.end():]
    command = _set_job_index_shift(updated_text, job_index_shift)
    return ProcessResult(
        command=command,
        shards=shards,
        requested_index_ranges=index_ranges,
        converted_task_groups=converted_task_groups,
        repository_valid_index_ranges=_group_consecutive(repository_indices),
        repository_excluded_index_ranges=_group_consecutive(repository_excluded_indices),
        completed_excluded_index_ranges=_group_consecutive(completed_excluded_indices),
        cluster_limit_excluded_index_ranges=_group_consecutive(cluster_limit_excluded_indices),
        final_index_ranges=_group_consecutive(included_indices),
        final_logical_task_groups=final_task_groups,
        final_submitted_task_groups=shifted_groups,
        job_index_shift=job_index_shift,
        repository_truncated=repository_truncated,
        task_truncated=task_truncated,
    )


def _print_summary(result: ProcessResult) -> None:
    included_indices = _task_groups_to_project_indices(result.final_logical_task_groups, result.shards)
    partial_project_labels = _task_groups_to_partial_project_labels(
        result.final_logical_task_groups,
        result.shards,
    )

    print(f"Actual project index ranges: {_format_index_ranges(result.requested_index_ranges)}", file=sys.stderr)
    print(
        "Included project index ranges in final command: "
        f"{_format_index_ranges(_group_consecutive(included_indices))}",
        file=sys.stderr,
    )
    print(
        "Excluded because output already exists: "
        f"{_format_index_ranges(result.completed_excluded_index_ranges)}",
        file=sys.stderr,
    )
    print(
        "Excluded because of cluster task-index limit: "
        f"{_format_index_ranges(result.cluster_limit_excluded_index_ranges)}",
        file=sys.stderr,
    )
    print(
        "Excluded because project index is outside repository.csv: "
        f"{_format_index_ranges(result.repository_excluded_index_ranges)}",
        file=sys.stderr,
    )
    if partial_project_labels:
        print(
            "Partially included because of cluster task-index limit: "
            f"{', '.join(partial_project_labels)}",
            file=sys.stderr,
        )
    print(f"Converted task index ranges: {_format_task_ranges(result.converted_task_groups)}", file=sys.stderr)
    if result.repository_truncated:
        print(
            "Repository-valid project index ranges: "
            f"{_format_index_ranges(result.repository_valid_index_ranges)}",
            file=sys.stderr,
        )
    else:
        print("Repository-valid project index ranges: (unchanged)", file=sys.stderr)
    if result.task_truncated:
        print(
            "Limit-truncated logical task index ranges: "
            f"{_format_task_ranges(result.final_logical_task_groups)}",
            file=sys.stderr,
        )
    else:
        print("Limit-truncated logical task index ranges: (unchanged)", file=sys.stderr)
    print(
        "Submitted task index ranges: "
        f"{_format_task_ranges(result.final_submitted_task_groups)}",
        file=sys.stderr,
    )
    if result.job_index_shift > 0:
        print(f"Job index shift: {result.job_index_shift}", file=sys.stderr)
    print("Sbatch command with truncated task indexes:\n", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Expand project indices in --array to Slurm task ID ranges."
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="Path to file containing the sbatch command (default: stdin)",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Include all indices even if output files already exist",
    )
    parser.add_argument(
        "--workspace-directory",
        dest="workspace_directory",
        default=None,
        help="Override workspace directory for repository.csv lookup and output existence checks",
    )
    args, extra = parser.parse_known_args()

    if extra or (args.input is not None and not Path(args.input).exists()):
        # Inline command passed directly: e.g. ptc-sbatch sbatch --array=22,29 --shards 200
        parts = ([args.input] if args.input is not None else []) + extra
        # --workspace-directory was consumed by our parser; restore it so the output is valid.
        if args.workspace_directory is not None and "--workspace-directory" not in parts:
            parts += ["--workspace-directory", args.workspace_directory]
        text = shlex.join(parts)
    elif args.input is not None:
        text = Path(args.input).read_text()
    else:
        text = sys.stdin.read()

    workspace = args.workspace_directory or _parse_arg(text, "workspace-directory")
    repo_df = _load_repository(workspace) if workspace is not None else None
    result = process_with_details(text, repo_df, replace=args.replace, workspace_override=args.workspace_directory)
    _print_summary(result)
    print(_format_shell_command(result.command), end="\n")


if __name__ == "__main__":
    main()
