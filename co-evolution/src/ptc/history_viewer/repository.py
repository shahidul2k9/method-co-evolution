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

from mhc.config import EXPERIMENT_DIRECTORY


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


@dataclass
class GroundTruthProjectSummary:
    csv_path: Path
    project: str
    total_rows: int
    test_method_count: int
    completed_test_method_count: int

    @property
    def completion_percent(self) -> float:
        if self.test_method_count == 0:
            return 0.0
        return self.completed_test_method_count / self.test_method_count * 100.0


@dataclass
class GroundTruthTestMethodSummary:
    from_name: str
    from_url: str
    candidate_count: int
    labelled_count: int
    truth_count: int = 0
    tags: str = ""
    notes: str = ""

    @property
    def is_complete(self) -> bool:
        return self.candidate_count > 0 and self.candidate_count == self.labelled_count


@dataclass
class GroundTruthCandidateRow:
    csv_path: Path
    row_index: int
    values: dict[str, str]

    @property
    def is_labelled(self) -> bool:
        return self.values.get("label", "").strip() != ""

    @property
    def notes(self) -> str:
        return self.values.get("notes", self.values.get("note", ""))


@dataclass
class GroundTruthMethodOption:
    row_index: int
    values: dict[str, str]


def repository_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_workspace_directory() -> Path:
    return Path(EXPERIMENT_DIRECTORY)


def default_data_directory() -> Path:
    return Path(EXPERIMENT_DIRECTORY)


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


def normalize_ground_truth_fieldnames(fieldnames: list[str]) -> list[str]:
    normalized: list[str] = []
    for fieldname in fieldnames:
        name = "notes" if fieldname == "note" else fieldname
        if name and name not in normalized:
            normalized.append(name)
    return normalized


def normalize_ground_truth_row(row: dict[str, str | None]) -> dict[str, str]:
    normalized = {("notes" if key == "note" else key): value or "" for key, value in row.items() if key is not None}
    if "notes" not in normalized:
        normalized["notes"] = row.get("note") or ""
    if "tags" not in normalized:
        normalized["tags"] = ""
    return normalized


def parse_ground_truth_tags(value: str) -> list[str]:
    tags: list[str] = []
    for token in re.split(r"[\s,]+", value.strip()):
        if not token:
            continue
        tag = token if token.startswith("#") else f"#{token}"
        if tag not in tags:
            tags.append(tag)
    return tags


def normalize_ground_truth_tags(value: str) -> str:
    return " ".join(parse_ground_truth_tags(value))


def normalize_single_tag(value: str) -> str:
    tags = parse_ground_truth_tags(value)
    if len(tags) != 1:
        raise ValueError("Tag must be a single non-empty token")
    return tags[0]


def ensure_ground_truth_fieldnames(fieldnames: list[str]) -> list[str]:
    normalized = normalize_ground_truth_fieldnames(fieldnames)
    for fieldname in (
        "project",
        "from_name",
        "to_name",
        "from_url",
        "to_url",
        "from_fqs",
        "from_tctracer_fqs",
        "from_testlinker_fqs",
        "to_fqs",
        "to_tctracer_fqs",
        "to_testlinker_fqs",
        "from_artifact",
        "to_artifact",
        "to_call_depth",
        "label",
        "tags",
        "notes",
    ):
        if fieldname not in normalized:
            normalized.append(fieldname)
    return normalized


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
    def __init__(self, workspace_directory: Path | None = None, data_directory: Path | None = None):
        self.workspace_directory = Path(workspace_directory or default_workspace_directory())
        self.data_directory = Path(data_directory or default_data_directory())

    @property
    def history_directory(self) -> Path:
        return self.workspace_directory / "method-history-gz"

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

    def list_ground_truth_csv_files(self, directory_path: str | Path) -> list[Path]:
        return self.list_sample_csv_files(directory_path)

    def summarize_ground_truth_projects(self, directory_path: str | Path) -> list[GroundTruthProjectSummary]:
        summaries: list[GroundTruthProjectSummary] = []
        for csv_file in self.list_ground_truth_csv_files(directory_path):
            rows = self.read_sample_rows(csv_file)
            method_summaries = self.summarize_ground_truth_test_methods(csv_file, rows=rows)
            project = csv_file.stem
            for row in rows:
                if row.values.get("project", "").strip():
                    project = row.values["project"].strip()
                    break
            summaries.append(
                GroundTruthProjectSummary(
                    csv_path=csv_file,
                    project=project,
                    total_rows=len(rows),
                    test_method_count=len(method_summaries),
                    completed_test_method_count=sum(1 for method in method_summaries if method.is_complete),
                )
            )
        return summaries

    def summarize_ground_truth_test_methods(
        self,
        csv_path: str | Path,
        *,
        rows: list[SampleRow] | None = None,
    ) -> list[GroundTruthTestMethodSummary]:
        source_rows = rows if rows is not None else self.read_sample_rows(csv_path)
        grouped: dict[str, dict[str, Any]] = {}
        for row in source_rows:
            from_url = row.values.get("from_url", "")
            if not from_url:
                continue
            group = grouped.setdefault(
                from_url,
                {
                    "from_name": row.values.get("from_name", "") or row.values.get("from_fqs", "") or from_url,
                    "candidate_count": 0,
                    "labelled_count": 0,
                    "truth_count": 0,
                    "tags": set(),
                    "notes": [],
                },
            )
            group["candidate_count"] += 1
            label_value = row.values.get("label", "").strip()
            if label_value != "":
                group["labelled_count"] += 1
            if label_value == "1":
                group["truth_count"] += 1
            for tag in parse_ground_truth_tags(row.values.get("tags", "")):
                group["tags"].add(tag)
            notes_value = row.values.get("notes", row.values.get("note", "")).strip()
            if notes_value and notes_value not in group["notes"]:
                group["notes"].append(notes_value)

        summaries = [
            GroundTruthTestMethodSummary(
                from_name=str(values["from_name"]),
                from_url=from_url,
                candidate_count=int(values["candidate_count"]),
                labelled_count=int(values["labelled_count"]),
                truth_count=int(values["truth_count"]),
                tags=" ".join(sorted(values["tags"], key=str.lower)),
                notes=" | ".join(values["notes"]),
            )
            for from_url, values in grouped.items()
        ]
        return sorted(summaries, key=lambda item: (item.is_complete, item.from_name.lower(), item.from_url.lower()))

    def read_ground_truth_candidates(self, csv_path: str | Path, *, from_url: str) -> list[GroundTruthCandidateRow]:
        path = Path(csv_path).expanduser()
        candidates: list[GroundTruthCandidateRow] = []
        for row in self.read_sample_rows(path):
            if row.values.get("from_url", "") != from_url:
                continue
            candidates.append(GroundTruthCandidateRow(csv_path=path, row_index=row.row_index, values=row.values))
        return candidates

    def collect_ground_truth_tags(self, csv_path: str | Path) -> list[str]:
        path = Path(csv_path).expanduser()
        tags: set[str] = set()
        for candidate_path in sorted(path.parent.glob("*.csv")):
            for row in self.read_sample_rows(candidate_path):
                for tag in parse_ground_truth_tags(row.values.get("tags", "")):
                    tags.add(tag)
        return sorted(tags, key=str.lower)

    def collect_sample_tags(self, csv_path: str | Path) -> list[str]:
        return self.collect_ground_truth_tags(csv_path)

    def update_ground_truth_label(
        self,
        csv_path: str | Path,
        *,
        row_index: int,
        from_url: str,
        to_url: str,
        label: str,
        notes: str = "",
        tags: str = "",
        note: str | None = None,
    ) -> GroundTruthCandidateRow:
        normalized_label = label.strip()
        if normalized_label not in {"", "0", "1"}:
            raise ValueError("Ground-truth label must be 1, 0, or blank")

        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = normalize_ground_truth_fieldnames(reader.fieldnames or [])
            if "label" not in fieldnames:
                fieldnames.append("label")
            if "notes" not in fieldnames:
                fieldnames.append("notes")
            if "tags" not in fieldnames:
                fieldnames.append("tags")
            rows = [normalize_ground_truth_row(row) for row in reader]

        if row_index < 0 or row_index >= len(rows):
            raise ValueError("Ground-truth row index is out of range")

        row = rows[row_index]
        if row.get("from_url", "") != from_url or row.get("to_url", "") != to_url:
            raise ValueError("Ground-truth row identity did not match the CSV row")

        row["label"] = normalized_label
        row["notes"] = notes if note is None else note
        row["tags"] = normalize_ground_truth_tags(tags)

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return GroundTruthCandidateRow(csv_path=path, row_index=row_index, values=row)

    def update_ground_truth_labels(
        self,
        csv_path: str | Path,
        *,
        updates: list[dict[str, str | int]],
    ) -> list[GroundTruthCandidateRow]:
        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = normalize_ground_truth_fieldnames(reader.fieldnames or [])
            if "label" not in fieldnames:
                fieldnames.append("label")
            if "notes" not in fieldnames:
                fieldnames.append("notes")
            if "tags" not in fieldnames:
                fieldnames.append("tags")
            rows = [normalize_ground_truth_row(row) for row in reader]

        updated_rows: list[GroundTruthCandidateRow] = []
        for update in updates:
            row_index = int(update["row_index"])
            normalized_label = str(update.get("label", "")).strip()
            if normalized_label not in {"", "0", "1"}:
                raise ValueError("Ground-truth label must be 1, 0, or blank")
            if row_index < 0 or row_index >= len(rows):
                raise ValueError("Ground-truth row index is out of range")

            row = rows[row_index]
            if row.get("from_url", "") != update.get("from_url", "") or row.get("to_url", "") != update.get("to_url", ""):
                raise ValueError("Ground-truth row identity did not match the CSV row")

            row["label"] = normalized_label
            row["notes"] = str(update.get("notes", update.get("note", "")))
            row["tags"] = normalize_ground_truth_tags(str(update.get("tags", "")))
            updated_rows.append(GroundTruthCandidateRow(csv_path=path, row_index=row_index, values=row))

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return updated_rows

    def delete_ground_truth_test_method(self, csv_path: str | Path, *, from_url: str) -> int:
        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = normalize_ground_truth_fieldnames(reader.fieldnames or [])
            rows = [normalize_ground_truth_row(row) for row in reader]

        remaining_rows = [row for row in rows if row.get("from_url", "") != from_url]
        deleted_count = len(rows) - len(remaining_rows)
        if deleted_count == 0:
            raise ValueError("No ground-truth rows matched that test method")

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(remaining_rows)
        return deleted_count

    def delete_ground_truth_candidate(self, csv_path: str | Path, *, from_url: str, to_url: str) -> int:
        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = normalize_ground_truth_fieldnames(reader.fieldnames or [])
            rows = [normalize_ground_truth_row(row) for row in reader]

        remaining_rows = [
            row for row in rows if not (row.get("from_url", "") == from_url and row.get("to_url", "") == to_url)
        ]
        deleted_count = len(rows) - len(remaining_rows)
        if deleted_count == 0:
            raise ValueError("No ground-truth row matched that candidate")

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(remaining_rows)
        return deleted_count

    def ground_truth_project_name(self, csv_path: str | Path) -> str:
        path = Path(csv_path).expanduser()
        for row in self.read_sample_rows(path):
            project = row.values.get("project", "").strip()
            if project:
                return project
        return path.stem

    def ground_truth_method_csv_path(self, csv_path: str | Path) -> Path:
        project = self.ground_truth_project_name(csv_path)
        return self.data_directory / "method" / f"{project}.csv"

    def search_ground_truth_method_options(
        self,
        csv_path: str | Path,
        *,
        query: str,
        mode: str = "name",
        limit: int = 25,
    ) -> list[GroundTruthMethodOption]:
        method_path = self.ground_truth_method_csv_path(csv_path)
        if not method_path.is_file():
            raise ValueError(f"Method CSV does not exist: {method_path}")
        normalized_query = query.strip().lower()
        if not normalized_query:
            return []
        search_mode = mode if mode in {"url", "file"} else "name"
        options: list[GroundTruthMethodOption] = []
        with method_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            for row_index, row in enumerate(reader):
                values = {key: value or "" for key, value in row.items() if key is not None}
                if search_mode == "url":
                    haystack = values.get("url", "")
                elif search_mode == "file":
                    haystack = " ".join(
                        [
                            values.get("file", ""),
                            values.get("file_path", ""),
                            values.get("path", ""),
                        ]
                    )
                else:
                    haystack = " ".join([values.get("name", ""), values.get("fqs", ""), values.get("fqn", "")])
                if normalized_query not in haystack.lower():
                    continue
                options.append(GroundTruthMethodOption(row_index=row_index, values=values))
                if len(options) >= limit:
                    break
        return options

    def append_ground_truth_candidate(
        self,
        csv_path: str | Path,
        *,
        from_url: str,
        method_row_index: int,
    ) -> GroundTruthCandidateRow:
        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = ensure_ground_truth_fieldnames(reader.fieldnames or [])
            rows = [normalize_ground_truth_row(row) for row in reader]

        matching_indexes = [index for index, row in enumerate(rows) if row.get("from_url", "") == from_url]
        if not matching_indexes:
            raise ValueError("No current test method rows matched that from_url")

        method_path = self.ground_truth_method_csv_path(path)
        if not method_path.is_file():
            raise ValueError(f"Method CSV does not exist: {method_path}")
        with method_path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            method_rows = [{key: value or "" for key, value in row.items() if key is not None} for row in reader]
        if method_row_index < 0 or method_row_index >= len(method_rows):
            raise ValueError("Method row index is out of range")

        source_row = rows[matching_indexes[0]]
        method_row = method_rows[method_row_index]
        to_url = method_row.get("url", "")
        if not to_url:
            raise ValueError("Selected method does not have a URL")
        if any(row.get("from_url", "") == from_url and row.get("to_url", "") == to_url for row in rows):
            raise ValueError("Selected method is already a candidate for this test method")

        new_row = {fieldname: "" for fieldname in fieldnames}
        for fieldname in (
            "project",
            "from_name",
            "from_url",
            "from_fqs",
            "from_tctracer_fqs",
            "from_testlinker_fqs",
            "from_artifact",
        ):
            new_row[fieldname] = source_row.get(fieldname, "")
        new_row["project"] = new_row.get("project", "") or self.ground_truth_project_name(path)
        new_row["to_name"] = method_row.get("name", "")
        new_row["to_url"] = to_url
        new_row["to_fqs"] = method_row.get("fqs", "")
        new_row["to_tctracer_fqs"] = method_row.get("tctracer_fqs", "")
        new_row["to_testlinker_fqs"] = method_row.get("testlinker_fqs", "")
        new_row["to_artifact"] = method_row.get("artifact", "")
        new_row["to_call_depth"] = "1"
        new_row["label"] = ""
        new_row["tags"] = ""
        new_row["notes"] = ""

        insert_at = matching_indexes[-1] + 1
        rows.insert(insert_at, new_row)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return GroundTruthCandidateRow(csv_path=path, row_index=insert_at, values=new_row)

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
        for preferred_option in ("t2p-link/ncc", "t2p-tech"):
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
        label: str | None = None,
    ) -> SampleRow:
        normalized_label = label.strip() if label is not None else None
        if normalized_label is not None and normalized_label not in {"0", "1"}:
            raise ValueError("Sample label must be 1 or 0")

        path = Path(csv_path).expanduser()
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = list(reader.fieldnames or [])
            if "label" not in fieldnames:
                fieldnames.append("label")
            if "notes" not in fieldnames:
                fieldnames.append("notes")
            if "tags" not in fieldnames:
                fieldnames.append("tags")
            rows = [{key: value or "" for key, value in row.items()} for row in reader]

        matched_row: SampleRow | None = None
        for index, row in enumerate(rows):
            if row.get("from_url", "") == from_url and row.get("to_url", "") == to_url:
                row["notes"] = notes
                row["tags"] = normalize_ground_truth_tags(tags)
                if normalized_label is not None:
                    row["label"] = normalized_label
                matched_row = SampleRow(csv_path=path, row_index=index, values=row)
                break

        if matched_row is None:
            raise ValueError("Could not locate the requested row in the sample CSV")

        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        return matched_row

    def rename_sample_tag_in_folder(self, csv_path: str | Path, *, old_tag: str, new_tag: str) -> dict[str, str | int]:
        path = Path(csv_path).expanduser()
        old_normalized = normalize_single_tag(old_tag)
        new_normalized = normalize_single_tag(new_tag)
        files_updated = 0
        rows_updated = 0

        for candidate_path in sorted(path.parent.glob("*.csv")):
            with candidate_path.open("r", encoding="utf-8", newline="") as handle:
                reader = csv.DictReader(handle)
                fieldnames = list(reader.fieldnames or [])
                rows = [{key: value or "" for key, value in row.items()} for row in reader]

            if "tags" not in fieldnames:
                continue

            file_changed = False
            for row in rows:
                tags = parse_ground_truth_tags(row.get("tags", ""))
                if old_normalized not in tags:
                    continue
                row["tags"] = " ".join(new_normalized if tag == old_normalized else tag for tag in tags)
                rows_updated += 1
                file_changed = True

            if not file_changed:
                continue

            with candidate_path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(rows)
            files_updated += 1

        return {
            "files_updated": files_updated,
            "rows_updated": rows_updated,
            "old_tag": old_normalized,
            "new_tag": new_normalized,
        }

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

        for root_name in ("t2p-candidate-filtered", "t2p-tech", "callgraph"):
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
                        to_name=row.get("to_name", "") or row.get("to_tctracer_fqs", "") or to_url,
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
                        from_name=row.get("from_name", "") or row.get("from_tctracer_fqs", "") or from_url,
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
            "t2p-candidate-filtered",
            "t2p-tech",
            "callgraph",
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
