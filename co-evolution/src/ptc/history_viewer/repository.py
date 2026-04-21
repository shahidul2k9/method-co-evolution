from __future__ import annotations

import csv
import hashlib
import json
import re
import tarfile
from dataclasses import dataclass, field
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlencode, urlparse


DATE_PATTERNS = (
    "%d/%m/%y %H:%M",
    "%d/%m/%y, %H:%M",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y, %H:%M",
    "%d/%m/%y %I:%M %p",
    "%d/%m/%y, %I:%M %p",
    "%d/%m/%Y %I:%M %p",
    "%d/%m/%Y, %I:%M %p",
    "%m/%d/%y %I:%M %p",
    "%m/%d/%y, %I:%M %p",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%Y, %I:%M %p",
    "%y/%m/%d %H:%M",
    "%y/%m/%d, %H:%M",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d, %H:%M",
)


@dataclass(frozen=True)
class MethodUrlRef:
    project: str
    commit: str
    file_path: str
    line: int
    url: str


@dataclass
class CommitEntry:
    commit_hash: str
    short_hash: str
    change_types: list[str]
    display_change_tags: list[str]
    commit_date_raw: str
    commit_date: datetime | None
    commit_message: str
    commit_author: str
    diff: str
    diff_url: str
    commit_url: str
    old_file_url: str
    new_file_url: str
    actual_source: str
    path: str
    days_between_commits: float | None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass
class MethodHistory:
    tool: str
    project: str
    source_file_path: str
    source_file_name: str
    function_name: str
    function_id: str
    function_start_line: int
    function_end_line: int | None
    origin: str
    input_url: str
    input_file: str
    entries: list[CommitEntry]
    raw: dict[str, Any]


@dataclass
class SampleRow:
    csv_path: Path
    row_index: int
    values: dict[str, str]

    @property
    def notes(self) -> str:
        return self.values.get("notes", "")

    @property
    def tags(self) -> str:
        return self.values.get("tags", "")


@dataclass
class RelatedMethod:
    to_name: str
    to_url: str
    to_file: str
    source_label: str
    source_csv: Path


@dataclass
class CallingMethod:
    from_name: str
    from_url: str
    from_file: str
    source_label: str
    source_csv: Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_cache_directory() -> Path:
    cwd_cache = Path.cwd() / ".cache"
    return cwd_cache if cwd_cache.exists() else repository_root() / ".cache"


def default_data_directory() -> Path:
    cache_directory = default_cache_directory()
    return cache_directory / "data"


def normalize_date_text(value: str) -> str:
    normalized = (
        value.replace("\u202f", " ")
        .replace("\xa0", " ")
        .replace(" ,", ",")
        .strip()
    )
    normalized = re.sub(r"\b00:(\d{2})\s*AM\b", r"12:\1 AM", normalized, flags=re.IGNORECASE)
    match = re.search(r"(\d{1,2}):(\d{2})\s*([AP]M)$", normalized, flags=re.IGNORECASE)
    if match:
        hour = int(match.group(1))
        if hour > 12:
            normalized = re.sub(r"\s*([AP]M)$", "", normalized, flags=re.IGNORECASE)
    return normalized


def parse_commit_datetime(value: str) -> datetime | None:
    if not value:
        return None
    normalized = normalize_date_text(value)
    heuristic_patterns = infer_date_patterns(normalized)
    for pattern in heuristic_patterns:
        try:
            return datetime.strptime(normalized, pattern)
        except ValueError:
            continue
    for pattern in DATE_PATTERNS:
        try:
            return datetime.strptime(normalized, pattern)
        except ValueError:
            continue
    return None


def infer_date_patterns(value: str) -> tuple[str, ...]:
    match = re.match(
        r"^(?P<a>\d{1,4})/(?P<b>\d{1,2})/(?P<c>\d{1,4})(?P<rest>(?:,)?\s+\d{1,2}:\d{2}(?:\s*[AP]M)?)$",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return ()

    a = int(match.group("a"))
    b = int(match.group("b"))
    c = int(match.group("c"))
    a_len = len(match.group("a"))
    c_len = len(match.group("c"))
    rest = match.group("rest")
    has_am_pm = "AM" in rest.upper() or "PM" in rest.upper()
    time_patterns = ["%I:%M %p"] if has_am_pm else ["%H:%M"]
    if rest.lstrip().startswith(","):
        time_patterns = [pattern.replace(" ", ", ", 1) for pattern in time_patterns]

    date_patterns: list[str] = []
    if a_len == 4 or a > 31:
        date_patterns.extend(["%Y/%m/%d", "%y/%m/%d"])
    elif c_len == 4:
        if a > 12 and b <= 12:
            date_patterns.extend(["%d/%m/%Y", "%m/%d/%Y"])
        elif b > 12 and a <= 12:
            date_patterns.extend(["%m/%d/%Y", "%d/%m/%Y"])
        else:
            date_patterns.extend(["%d/%m/%Y", "%m/%d/%Y"])
    elif a > 12 and b <= 12:
        date_patterns.extend(["%d/%m/%y", "%y/%m/%d"])
    elif b > 12 and a <= 12:
        date_patterns.extend(["%m/%d/%y", "%d/%m/%y"])
    else:
        date_patterns.extend(["%d/%m/%y", "%m/%d/%y", "%y/%m/%d"])

    ordered_patterns: list[str] = []
    for date_pattern in date_patterns:
        for time_pattern in time_patterns:
            combined = f"{date_pattern} {time_pattern}"
            if combined not in ordered_patterns:
                ordered_patterns.append(combined)
    return tuple(ordered_patterns)


def parse_method_url(url: str) -> MethodUrlRef:
    parsed = urlparse(url)
    if parsed.netloc not in {"github.com", "www.github.com"}:
        raise ValueError("Only GitHub blob URLs are supported")

    path_parts = [part for part in unquote(parsed.path).split("/") if part]
    if len(path_parts) < 5 or path_parts[2] != "blob":
        raise ValueError("URL must look like https://github.com/<owner>/<repo>/blob/<commit>/<path>#L<line>")

    fragment = parsed.fragment or ""
    if not fragment.startswith("L"):
        raise ValueError("URL fragment must include a start line like #L17")

    return MethodUrlRef(
        project=path_parts[1],
        commit=path_parts[3],
        file_path="/".join(path_parts[4:]),
        line=int(fragment[1:].split("-")[0]),
        url=url,
    )


def infer_tool_from_history_file(path: Path) -> str:
    parts = path.resolve().parts
    for index, part in enumerate(parts):
        if part == "history" and index + 1 < len(parts):
            return parts[index + 1]
    return ""


def infer_project_from_history_file(path: Path) -> str:
    parts = path.resolve().parts
    for index, part in enumerate(parts):
        if part == "history" and index + 2 < len(parts):
            return parts[index + 2]
    return path.parent.name


def _method_member_matches(member_name: str, project: str, file_path: str, line: int) -> bool:
    candidate = Path(member_name)
    expected_parent = Path(project) / Path(file_path).parent
    if candidate.parent != expected_parent:
        return False
    return candidate.name.startswith(f"{Path(file_path).stem}--") and candidate.name.endswith(f"--{line}.json")


def _coerce_change_types(detail: dict[str, Any], short_type: str) -> list[str]:
    change_types: list[str] = []
    detail_type = detail.get("type")
    if isinstance(detail_type, str) and detail_type.strip():
        change_types.append(detail_type.strip())
    for raw_value in detail.get("changeTags", []):
        if isinstance(raw_value, str) and raw_value.strip():
            change_types.append(raw_value.strip())
    if short_type and short_type not in change_types:
        change_types.append(short_type)
    if not change_types:
        change_types.append("UNKNOWN")
    return list(dict.fromkeys(change_types))


def _coerce_display_tags(detail: dict[str, Any], change_types: list[str]) -> list[str]:
    display_tags = [str(tag).strip() for tag in detail.get("displayChangeTags", []) if str(tag).strip()]
    if display_tags:
        return display_tags
    return change_types


def _ordered_commit_hashes(raw: dict[str, Any]) -> list[str]:
    change_history = raw.get("changeHistory")
    if isinstance(change_history, list) and change_history:
        return [str(value) for value in change_history]

    commit_details = raw.get("commitDetails")
    if isinstance(commit_details, list) and commit_details:
        return [
            str(detail.get("commitName", "")).strip()
            for detail in commit_details
            if str(detail.get("commitName", "")).strip()
        ]

    commit_map = raw.get("changeHistoryDetails")
    if isinstance(commit_map, dict) and commit_map:
        return list(commit_map.keys())

    commits = raw.get("commits")
    if isinstance(commits, list) and commits:
        return [
            str(commit.get("commitHash", "")).strip()
            for commit in commits
            if str(commit.get("commitHash", "")).strip()
        ]

    return []


def normalize_history(raw: dict[str, Any], *, tool: str, input_url: str = "", input_file: str = "") -> MethodHistory:
    details_by_hash: dict[str, dict[str, Any]] = {}
    for commit_hash, detail in raw.get("changeHistoryDetails", {}).items():
        if isinstance(detail, dict):
            details_by_hash[str(commit_hash)] = dict(detail)

    for detail in raw.get("commitDetails", []):
        if isinstance(detail, dict):
            commit_hash = str(detail.get("commitName", "")).strip()
            if commit_hash and commit_hash not in details_by_hash:
                details_by_hash[commit_hash] = dict(detail)

    short_types = {
        str(commit_hash): str(change_type)
        for commit_hash, change_type in raw.get("changeHistoryShort", {}).items()
    }

    entries: list[CommitEntry] = []
    for commit_hash in _ordered_commit_hashes(raw):
        detail = dict(details_by_hash.get(commit_hash, {}))
        change_types = _coerce_change_types(detail, short_types.get(commit_hash, ""))
        entries.append(
            CommitEntry(
                commit_hash=commit_hash,
                short_hash=commit_hash[:6],
                change_types=change_types,
                display_change_tags=_coerce_display_tags(detail, change_types),
                commit_date_raw=str(detail.get("commitDate", "")),
                commit_date=parse_commit_datetime(str(detail.get("commitDate", ""))),
                commit_message=str(detail.get("commitMessage", "")),
                commit_author=str(detail.get("commitAuthor", "")),
                diff=str(detail.get("diff", "")),
                diff_url=str(detail.get("diffUrl", "")),
                commit_url=str(detail.get("commitUrl", "")),
                old_file_url=str(detail.get("oldFileUrl", "")),
                new_file_url=str(detail.get("newFileUrl", "")),
                actual_source=str(detail.get("actualSource", "")),
                path=str(detail.get("path", raw.get("sourceFilePath", ""))),
                days_between_commits=_parse_optional_float(detail.get("daysBetweenCommits")),
                details=detail,
            )
        )

    return MethodHistory(
        tool=tool,
        project=str(raw.get("repositoryName", "")),
        source_file_path=str(raw.get("sourceFilePath", "")),
        source_file_name=str(raw.get("sourceFileName", "")),
        function_name=str(raw.get("functionName", "")),
        function_id=str(raw.get("functionId", "")),
        function_start_line=_parse_optional_int(raw.get("functionStartLine")) or 0,
        function_end_line=_parse_optional_int(raw.get("functionEndLine")),
        origin=str(raw.get("origin", tool)),
        input_url=input_url,
        input_file=input_file,
        entries=entries,
        raw=raw,
    )


def _parse_optional_int(value: Any) -> int | None:
    try:
        if value in ("", None):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_optional_float(value: Any) -> float | None:
    try:
        if value in ("", None):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


class HistoryRepository:
    def __init__(self, cache_directory: Path | None = None, data_directory: Path | None = None):
        self.cache_directory = Path(cache_directory or default_cache_directory())
        self.data_directory = Path(data_directory or default_data_directory())

    @property
    def history_directory(self) -> Path:
        return self.cache_directory / "history"

    def load_history_from_file(self, file_path: str | Path, tool: str | None = None) -> MethodHistory:
        path = Path(file_path).expanduser()
        raw = json.loads(path.read_text(encoding="utf-8"))
        resolved_tool = tool or infer_tool_from_history_file(path) or str(raw.get("origin", ""))
        return normalize_history(raw, tool=resolved_tool, input_file=str(path))

    def load_history_from_url(self, url: str, tool: str) -> MethodHistory:
        ref = parse_method_url(url)
        member_name = self._resolve_member_name(tool=tool, project=ref.project, file_path=ref.file_path, line=ref.line)
        raw = self._read_history_json(tool=tool, project=ref.project, member_name=member_name)
        history = normalize_history(raw, tool=tool, input_url=url)
        if not history.project:
            history.project = ref.project
        return history

    def load_history(self, *, tool: str, url: str = "", file_path: str = "") -> MethodHistory:
        if file_path:
            return self.load_history_from_file(file_path, tool=tool)
        if url:
            return self.load_history_from_url(url, tool=tool)
        raise ValueError("Either file_path or url must be provided")

    def read_sample_rows(self, csv_path: str | Path) -> list[SampleRow]:
        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            return [
                SampleRow(csv_path=path, row_index=index, values={key: value or "" for key, value in row.items()})
                for index, row in enumerate(reader)
            ]

    def list_sample_csv_files(self, directory_path: str | Path) -> list[Path]:
        directory = Path(directory_path).expanduser()
        if not directory.is_dir():
            raise ValueError(f"Sample directory does not exist: {directory}")
        return sorted(path for path in directory.glob("*.csv") if path.is_file())

    def find_related_production_methods(
        self,
        *,
        project: str,
        from_url: str,
        tool: str = "",
        sample_csv: str = "",
        selected_source: str = "",
    ) -> tuple[list[RelatedMethod], list[str]]:
        searched_labels: list[str] = []
        for csv_file, source_label in self._iter_related_csv_candidates(
            project=project,
            tool=tool,
            sample_csv=sample_csv,
            selected_source=selected_source,
        ):
            searched_labels.append(source_label)
            if not csv_file.exists():
                continue
            matches = self._read_related_rows(csv_file=csv_file, source_label=source_label, from_url=from_url)
            if matches:
                return matches, searched_labels
        return [], searched_labels

    def find_calling_test_methods(
        self,
        *,
        project: str,
        to_url: str,
        tool: str = "",
        sample_csv: str = "",
        selected_source: str = "",
    ) -> tuple[list[CallingMethod], list[str]]:
        searched_labels: list[str] = []
        for csv_file, source_label in self._iter_related_csv_candidates(
            project=project,
            tool=tool,
            sample_csv=sample_csv,
            selected_source=selected_source,
        ):
            searched_labels.append(source_label)
            if not csv_file.exists():
                continue
            matches = self._read_calling_rows(csv_file=csv_file, source_label=source_label, to_url=to_url)
            if matches:
                return matches, searched_labels
        return [], searched_labels

    def related_source_options(self, *, tool: str, sample_csv: str) -> list[str]:
        options: list[str] = []
        for preferred_option in ("t2p-link/ncc", "m2m-tech"):
            if preferred_option in self._available_source_options():
                options.append(preferred_option)
        options.extend(
            option
            for option in self._available_source_options()
            if option not in options
        )
        return options

    def read_sample_row(self, csv_path: str | Path, *, from_url: str, to_url: str) -> SampleRow:
        for row in self.read_sample_rows(csv_path):
            if row.values.get("from_url", "") == from_url and row.values.get("to_url", "") == to_url:
                return row
        raise ValueError("Could not locate the requested row in the sample CSV")

    def write_revision_links(self, csv_path: str | Path, *, base_url: str) -> int:
        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            if "revision_url" not in fieldnames:
                fieldnames.append("revision_url")
            rows = [{key: value or "" for key, value in row.items()} for row in reader]

        for row in rows:
            row["revision_url"] = self.build_revision_url(
                base_url=base_url,
                csv_path=path,
                from_url=row.get("from_url", ""),
                to_url=row.get("to_url", ""),
                tool=row.get("tool", ""),
                project=row.get("project", ""),
            )

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def update_sample_note(
        self,
        csv_path: str | Path,
        *,
        from_url: str,
        to_url: str,
        notes: str,
        tags: str = "",
    ) -> SampleRow:
        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            if "notes" not in fieldnames:
                fieldnames.append("notes")
            if "tags" not in fieldnames:
                fieldnames.append("tags")
            rows = [{key: value or "" for key, value in row.items()} for row in reader]

        matched_row: SampleRow | None = None
        for index, row in enumerate(rows):
            if row.get("from_url", "") == from_url and row.get("to_url", "") == to_url:
                row["notes"] = notes
                row["tags"] = tags
                matched_row = SampleRow(csv_path=path, row_index=index, values=row)
                break

        if matched_row is None:
            raise ValueError("Could not locate the requested row in the sample CSV")

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return matched_row

    def build_revision_url(
        self,
        *,
        base_url: str,
        csv_path: str | Path,
        from_url: str,
        to_url: str,
        tool: str = "",
        project: str = "",
    ) -> str:
        params = {
            "sample_csv": str(Path(csv_path).expanduser()),
            "from_url": from_url,
            "to_url": to_url,
        }
        if tool:
            params["tool"] = tool
        if project:
            params["project"] = project
        encoded = urlencode({key: value for key, value in params.items() if value})
        return f"{base_url.rstrip('/')}/revision?{encoded}"

    def _iter_related_csv_candidates(
        self,
        *,
        project: str,
        tool: str,
        sample_csv: str,
        selected_source: str = "",
    ) -> list[tuple[Path, str]]:
        candidates: list[tuple[Path, str]] = []
        sample_context = self._sample_context(sample_csv)
        data_directory = self.data_directory

        if selected_source:
            return self._candidate_paths_for_source(
                project=project,
                tool=tool,
                sample_context=sample_context,
                selected_source=selected_source,
            )

        exact_t2p_change = None
        if sample_context and sample_context["kind"] == "t2p-change-sample":
            exact_t2p_change = data_directory / "t2p-link" / sample_context["strategy"] / f"{project}.csv"
            candidates.append((exact_t2p_change, self._source_label(exact_t2p_change)))

        for csv_file in self._iter_t2p_link_csv_files(project):
            if exact_t2p_change is not None and csv_file == exact_t2p_change:
                continue
            candidates.append((csv_file, self._source_label(csv_file)))

        for root_name in ("t2p-candidate", "m2m-tech", "fan-out"):
            csv_file = data_directory / root_name / f"{project}.csv"
            candidates.append((csv_file, self._source_label(csv_file)))

        deduped: list[tuple[Path, str]] = []
        seen_paths: set[Path] = set()
        for csv_file, label in candidates:
            if csv_file in seen_paths:
                continue
            seen_paths.add(csv_file)
            deduped.append((csv_file, label))
        return deduped

    def _candidate_paths_for_source(
        self,
        *,
        project: str,
        tool: str,
        sample_context: dict[str, str] | None,
        selected_source: str,
    ) -> list[tuple[Path, str]]:
        data_directory = self.data_directory
        if selected_source.startswith("t2p-link/"):
            parts = selected_source.split("/")
            if len(parts) >= 2:
                csv_file = data_directory / parts[0] / parts[1] / f"{project}.csv"
                return [(csv_file, selected_source)]
            if sample_context and sample_context["kind"] == "t2p-change-sample":
                csv_file = data_directory / "t2p-link" / sample_context["strategy"] / f"{project}.csv"
                return [(csv_file, self._source_label(csv_file))]
            return [
                (csv_file, self._source_label(csv_file))
                for csv_file in self._iter_t2p_link_csv_files(project)
            ]

        csv_file = data_directory / selected_source / f"{project}.csv"
        return [(csv_file, selected_source)]

    def _sample_context(self, sample_csv: str) -> dict[str, str] | None:
        if not sample_csv:
            return None
        path = Path(sample_csv).expanduser()
        parts = path.parts
        for index, part in enumerate(parts):
            if part == "t2p-change-sample" and index + 3 < len(parts):
                return {
                    "kind": part,
                    "tool": parts[index + 1],
                    "strategy": parts[index + 2],
                }
        return None

    def _read_related_rows(self, *, csv_file: Path, source_label: str, from_url: str) -> list[RelatedMethod]:
        with csv_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            methods_by_url: dict[str, RelatedMethod] = {}
            for row in reader:
                if (row.get("from_url") or "") != from_url:
                    continue
                to_url = row.get("to_url", "") or ""
                if not to_url:
                    continue
                if to_url not in methods_by_url:
                    methods_by_url[to_url] = RelatedMethod(
                        to_name=row.get("to_name", "") or row.get("to_fqs_alt", "") or to_url,
                        to_url=to_url,
                        to_file=row.get("to_file", "") or "",
                        source_label=source_label,
                        source_csv=csv_file,
                    )
            return sorted(methods_by_url.values(), key=lambda item: (item.to_name.lower(), item.to_url.lower()))

    def _read_calling_rows(self, *, csv_file: Path, source_label: str, to_url: str) -> list[CallingMethod]:
        with csv_file.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            methods_by_url: dict[str, CallingMethod] = {}
            for row in reader:
                if (row.get("to_url") or "") != to_url:
                    continue
                from_url = row.get("from_url", "") or ""
                if not from_url:
                    continue
                if from_url not in methods_by_url:
                    methods_by_url[from_url] = CallingMethod(
                        from_name=row.get("from_name", "") or row.get("from_fqs_alt", "") or from_url,
                        from_url=from_url,
                        from_file=row.get("from_file", "") or "",
                        source_label=source_label,
                        source_csv=csv_file,
                    )
            return sorted(methods_by_url.values(), key=lambda item: (item.from_name.lower(), item.from_url.lower()))

    def _source_label(self, csv_file: Path) -> str:
        try:
            relative_parent = csv_file.parent.relative_to(self.data_directory)
            return str(relative_parent).replace("\\", "/")
        except ValueError:
            return str(csv_file.parent)

    def _iter_t2p_link_csv_files(self, project: str) -> list[Path]:
        t2p_link_root = self.data_directory / "t2p-link"
        if not t2p_link_root.exists():
            return []
        return sorted(t2p_link_root.glob(f"*/{project}.csv"))

    def _t2p_link_options(self) -> list[str]:
        t2p_link_root = self.data_directory / "t2p-link"
        if not t2p_link_root.exists():
            return []
        return [
            f"t2p-link/{directory.name}"
            for directory in sorted(path for path in t2p_link_root.iterdir() if path.is_dir())
        ]

    def _available_source_options(self) -> list[str]:
        return [
            *self._t2p_link_options(),
            "t2p-candidate",
            "m2m-tech",
            "fan-out",
        ]

    def _resolve_member_name(self, *, tool: str, project: str, file_path: str, line: int) -> str:
        extracted_root = self.history_directory / tool / project / Path(file_path).parent
        if extracted_root.exists():
            matches = sorted(extracted_root.glob(f"{Path(file_path).stem}--*--{line}.json"))
            if matches:
                project_root = self.history_directory / tool
                return str(matches[0].relative_to(project_root)).replace("\\", "/")

        tar_path = self.history_directory / tool / f"{project}.tar.gz"
        if not tar_path.exists():
            raise FileNotFoundError(
                f"No history file found for project={project!r}, tool={tool!r}. "
                f"Expected either {extracted_root} or {tar_path}."
            )

        matches = [
            member_name
            for member_name in self._load_tar_index(str(tar_path))
            if _method_member_matches(member_name, project=project, file_path=file_path, line=line)
        ]
        if not matches:
            raise FileNotFoundError(
                f"Could not resolve history JSON for {file_path}#L{line} in {tar_path}."
            )
        return sorted(matches)[0]

    def _read_history_json(self, *, tool: str, project: str, member_name: str) -> dict[str, Any]:
        extracted_path = self.history_directory / tool / member_name
        if extracted_path.exists():
            return json.loads(extracted_path.read_text(encoding="utf-8"))

        tar_path = self.history_directory / tool / f"{project}.tar.gz"
        with tarfile.open(tar_path, "r:gz") as archive:
            extracted = archive.extractfile(member_name)
            if extracted is None:
                raise FileNotFoundError(f"Could not open {member_name} from {tar_path}")
            return json.loads(extracted.read().decode("utf-8"))

    @staticmethod
    @lru_cache(maxsize=128)
    def _load_tar_index(tar_path: str) -> tuple[str, ...]:
        with tarfile.open(tar_path, "r:gz") as archive:
            return tuple(archive.getnames())


def build_row_token(csv_path: str | Path, from_url: str, to_url: str) -> str:
    payload = f"{Path(csv_path).resolve()}|{from_url}|{to_url}".encode("utf-8")
    return hashlib.sha1(payload).hexdigest()[:12]


def load_post_data(body: bytes, content_type: str) -> dict[str, str]:
    if content_type.startswith("application/json"):
        payload = json.loads(body.decode("utf-8") or "{}")
        return {str(key): "" if value is None else str(value) for key, value in payload.items()}

    parsed = parse_qs(body.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def dump_json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, indent=2, sort_keys=True).encode("utf-8")
