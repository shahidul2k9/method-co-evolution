from __future__ import annotations

import difflib
import html
import math
import re
import traceback
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Iterable
from urllib.parse import parse_qs, quote, urlencode

from ptc.util.helper import extract_change_count

from .repository import (
    CallingMethod,
    CommitEntry,
    HistoryRepository,
    MethodHistory,
    RelatedMethod,
    SampleRow,
    build_row_token,
    dump_json_bytes,
    load_post_data,
)


STYLE = """
<style>
:root {
  --bg: #f7f4ed;
  --panel: #fffdfa;
  --line: #d8cfbd;
  --ink: #1f2933;
  --muted: #6b7280;
  --accent: #0f766e;
  --accent-soft: #d7f3ef;
  --warn: #a16207;
  --warn-soft: #fef3c7;
  --danger: #b91c1c;
  --danger-soft: #fee2e2;
  --shadow: 0 18px 42px rgba(31, 41, 51, 0.08);
  --mono: "SFMono-Regular", Consolas, "Liberation Mono", Menlo, monospace;
  --sans: "Iowan Old Style", "Palatino Linotype", "Book Antiqua", Georgia, serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background:
    radial-gradient(circle at top left, rgba(15, 118, 110, 0.10), transparent 26%),
    linear-gradient(180deg, #fbf8f2 0%, #f7f4ed 50%, #f1ece1 100%);
  color: var(--ink);
  font-family: var(--sans);
}
a { color: var(--accent); }
main { max-width: 1280px; margin: 0 auto; padding: 32px 24px 72px; }
h1, h2, h3 { margin: 0; font-weight: 700; }
p { margin: 0; line-height: 1.55; }
code, pre, .mono { font-family: var(--mono); }
.hero {
  display: grid;
  gap: 18px;
  padding: 28px;
  border: 1px solid rgba(216, 207, 189, 0.9);
  border-radius: 28px;
  background: linear-gradient(135deg, rgba(255,255,255,0.94), rgba(252,247,237,0.88));
  box-shadow: var(--shadow);
}
.hero p { color: var(--muted); max-width: 74ch; }
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 20px;
  margin-top: 24px;
}
.card, .summary-card, .panel {
  background: rgba(255, 253, 250, 0.92);
  border: 1px solid rgba(216, 207, 189, 0.95);
  border-radius: 24px;
  padding: 22px;
  box-shadow: var(--shadow);
}
.panel { padding: 18px 20px; }
.eyebrow {
  color: var(--accent);
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-size: 0.78rem;
  font-weight: 700;
}
.muted { color: var(--muted); }
form {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}
label {
  display: grid;
  gap: 6px;
  font-size: 0.95rem;
}
input, select, textarea, button {
  border-radius: 14px;
  border: 1px solid #cfc4af;
  padding: 12px 14px;
  font: inherit;
  color: var(--ink);
  background: rgba(255,255,255,0.96);
}
textarea { min-height: 110px; resize: vertical; }
button {
  background: linear-gradient(135deg, #0f766e, #155e75);
  color: white;
  border: none;
  cursor: pointer;
  font-weight: 700;
}
button.secondary {
  background: linear-gradient(135deg, #ebe2d3, #e3d6c0);
  color: var(--ink);
}
.button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.stats {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 14px;
  margin: 22px 0 28px;
}
.summary-card strong {
  display: block;
  font-size: 1.8rem;
  margin-top: 8px;
}
.chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.chip {
  display: inline-flex;
  align-items: center;
  padding: 6px 11px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: var(--accent);
  font-size: 0.86rem;
  font-weight: 700;
}
.chip.warn {
  background: var(--warn-soft);
  color: var(--warn);
}
.chip.danger {
  background: var(--danger-soft);
  color: var(--danger);
}
.chip.type-introduction {
  background: #dbeafe;
  color: #1d4ed8;
}
.chip.type-body {
  background: #dcfce7;
  color: #166534;
}
.chip.type-rename,
.chip.type-move,
.chip.type-file-move {
  background: #ede9fe;
  color: #6d28d9;
}
.chip.type-documentation,
.chip.type-format {
  background: #fce7f3;
  color: #be185d;
}
.chip.type-annotation,
.chip.type-modifier,
.chip.type-return-type,
.chip.type-exception,
.chip.type-parameter,
.chip.type-parameter-meta {
  background: #fef3c7;
  color: #a16207;
}
.chip.type-multi,
.chip.type-unknown {
  background: #fee2e2;
  color: #b91c1c;
}
.methods {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 24px;
}
.method-panel h2 {
  font-size: 1.1rem;
  margin-top: 10px;
}
.method-panel .mono {
  font-size: 0.92rem;
  line-height: 1.5;
  word-break: break-word;
}
.timeline {
  display: grid;
  gap: 16px;
}
.timeline-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 84px minmax(0, 1fr);
  gap: 16px;
  align-items: start;
}
.timeline-row > div {
  min-width: 0;
}
.timeline-center {
  position: relative;
  min-height: 0;
  align-self: stretch;
  display: grid;
  justify-items: center;
  gap: 8px;
  padding-top: 14px;
  padding-bottom: 14px;
}
.timeline-center::before {
  content: "";
  position: absolute;
  top: 0;
  bottom: 0;
  width: 4px;
  border-radius: 999px;
  background: linear-gradient(180deg, rgba(15,118,110,0.22), rgba(21,94,117,0.85));
}
.marker-stack {
  position: relative;
  z-index: 1;
  display: flex;
  gap: 8px;
  align-items: center;
}
.marker {
  width: 18px;
  height: 18px;
  border-radius: 999px;
  background: #fff;
  border: 4px solid var(--accent);
  box-shadow: 0 0 0 4px rgba(215, 243, 239, 0.95);
}
.marker.right {
  border-color: #155e75;
  box-shadow: 0 0 0 4px rgba(191, 219, 254, 0.95);
}
.gap-label {
  position: relative;
  z-index: 1;
  text-align: center;
  font-size: 0.82rem;
  font-weight: 700;
  color: var(--muted);
  background: rgba(247, 244, 237, 0.96);
  padding: 4px 8px;
  border-radius: 999px;
}
.event-card {
  border-radius: 20px;
  border: 1px solid rgba(216, 207, 189, 0.95);
  background: rgba(255,255,255,0.92);
  padding: 14px 16px;
  overflow: hidden;
}
.event-card.right {
  background: rgba(245, 250, 255, 0.94);
}
details { border-radius: 16px; }
summary {
  list-style: none;
  cursor: pointer;
}
summary::-webkit-details-marker { display: none; }
.event-header {
  display: grid;
  gap: 7px;
}
.event-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.meta-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 8px;
  border-radius: 999px;
  background: #f2ece2;
  font-size: 0.8rem;
  font-weight: 700;
}
.detail-grid {
  display: grid;
  gap: 12px;
  padding-top: 14px;
}
.diff-panel {
  border: 1px solid #d0d7de;
  border-radius: 16px;
  overflow: hidden;
  background: #ffffff;
}
.diff-panel.compact {
  overflow: hidden;
}
.diff-scroll {
  display: block;
  max-width: 100%;
  overflow-x: scroll;
  overflow-y: hidden;
  scrollbar-gutter: stable;
  -webkit-overflow-scrolling: touch;
}
.diff-panel.compact .diff-scroll .diff-table {
  width: max-content;
  min-width: 100%;
}
.diff-panel.compact .diff-line-no {
  width: 34px;
  padding: 5px 6px !important;
  font-size: 0.76rem;
}
.diff-panel.compact .diff-code {
  padding: 5px 8px !important;
  font-size: 0.76rem;
  line-height: 1.35;
  white-space: pre;
  overflow-wrap: normal;
}
.diff-panel.compact .diff-toolbar {
  padding: 8px 10px;
  justify-content: flex-start;
}
.diff-panel.compact .diff-toolbar span {
  font-size: 0.74rem;
  letter-spacing: 0.02em;
}
.diff-toolbar-group {
  display: inline-flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.diff-scroll-button {
  padding: 6px 10px;
  font-size: 0.74rem;
}
.diff-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 10px 14px;
  background: #f6f8fa;
  color: #57606a;
  font-size: 0.82rem;
  font-weight: 700;
  letter-spacing: 0.04em;
}
.diff-toolbar button {
  flex: 0 0 auto;
}
.diff-table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 0;
  font-size: 0.85rem;
  table-layout: fixed;
}
.diff-table.unified {
  table-layout: auto;
}
.diff-table td {
  padding: 0;
  border-bottom: none;
  vertical-align: top;
}
.diff-line-no {
  width: 42px;
  padding: 6px 8px !important;
  text-align: right;
  color: #57606a;
  background: transparent;
  font-family: var(--mono);
  user-select: none;
}
.diff-code {
  padding: 6px 10px !important;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-family: var(--mono);
}
.diff-cell-context.diff-line-no,
.diff-cell-context.diff-code {
  background: transparent;
}
.diff-cell-del.diff-line-no,
.diff-cell-del.diff-code {
  background: #ffebe9;
}
.diff-cell-add.diff-line-no,
.diff-cell-add.diff-code {
  background: #dafbe1;
}
.diff-cell-change.diff-line-no,
.diff-cell-change.diff-code {
  background: #fff8c5;
}
.diff-inline-del {
  background: #ffd8d3;
  color: #7f1d1d;
  border-radius: 4px;
}
.diff-inline-add {
  background: #c7f0d2;
  color: #14532d;
  border-radius: 4px;
}
.diff-code-empty {
  background: transparent;
}
.diff-hunk td {
  background: #ddf4ff;
  color: #0969da;
  font-family: var(--mono);
  padding: 6px 10px !important;
}
.diff-hunk .diff-line-no,
.diff-meta .diff-line-no {
  width: 42px;
  padding: 6px 8px !important;
  text-align: right;
  color: #57606a;
  background: transparent;
  font-family: var(--mono);
}
.diff-hunk .diff-code,
.diff-meta .diff-code {
  padding: 6px 10px !important;
  font-family: var(--mono);
}
.diff-meta td {
  background: #f6f8fa;
  color: #57606a;
  font-family: var(--mono);
  padding: 6px 10px !important;
}
.diff-modal {
  position: fixed;
  inset: 0;
  display: none;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(31, 41, 51, 0.64);
  z-index: 1000;
}
.diff-modal.open {
  display: flex;
}
.diff-modal-card {
  width: min(1480px, 96vw);
  max-height: 88vh;
  overflow: auto;
  border-radius: 16px;
  border: 1px solid #d0d7de;
  background: #ffffff;
  box-shadow: 0 24px 60px rgba(31, 41, 51, 0.22);
}
.diff-modal-header {
  position: sticky;
  top: 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 16px 18px;
  background: #f6f8fa;
  border-bottom: 1px solid #d0d7de;
  z-index: 1;
}
.diff-modal-body {
  padding: 0;
}
.diff-modal-controls {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #d0d7de;
  background: #ffffff;
}
.diff-view-toggle.active {
  background: linear-gradient(135deg, #0f766e, #155e75);
  color: white;
}
.diff-modal-view {
  display: none;
}
.diff-modal-view.open {
  display: block;
}
.diff-mark {
  display: inline-block;
  min-width: 14px;
  margin-right: 6px;
  color: #8b7d67;
}
.syntax-keyword {
  color: #cf222e;
  font-weight: 700;
}
.syntax-string {
  color: #0a3069;
}
.syntax-comment {
  color: #6e7781;
  font-style: italic;
}
.syntax-annotation {
  color: #8250df;
  font-weight: 700;
}
.syntax-number {
  color: #0550ae;
}
.diff-panel.github-split .diff-code {
  padding: 5px 10px !important;
}
.diff-panel.github-split td:nth-child(3) {
  border-left: 1px solid #d0d7de;
}
.source-versions {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
}
.source-version-panel + .source-version-panel {
  border-left: 1px solid #d0d7de;
}
.source-version-panel .diff-table {
  margin-top: 0;
}
.source-version-panel .diff-code {
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}
pre {
  white-space: pre-wrap;
  overflow-x: auto;
  padding: 14px;
  border-radius: 16px;
  background: #1f2933;
  color: #f8fafc;
  font-size: 0.86rem;
}
table {
  width: 100%;
  border-collapse: collapse;
  margin-top: 18px;
  font-size: 0.95rem;
}
th, td {
  padding: 12px 10px;
  border-bottom: 1px solid rgba(216, 207, 189, 0.75);
  text-align: left;
  vertical-align: top;
}
th {
  color: var(--muted);
  font-size: 0.82rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}
.flash {
  margin-top: 14px;
  padding: 12px 14px;
  border-radius: 16px;
  background: var(--accent-soft);
  color: var(--accent);
  font-weight: 700;
}
.trend-up {
  color: #166534;
  font-weight: 700;
}
.trend-down {
  color: #b91c1c;
  font-weight: 700;
}
.trend-flat {
  color: var(--muted);
  font-weight: 700;
}
.error {
  background: var(--danger-soft);
  color: var(--danger);
}
@media (max-width: 920px) {
  .methods, .timeline-row { grid-template-columns: 1fr; }
  .timeline-center { min-height: 72px; order: -1; }
  .timeline-center::before { left: 50%; transform: translateX(-50%); }
}
</style>
"""


@dataclass
class TimelineRow:
    left: CommitEntry | None
    right: CommitEntry | None
    sort_date: datetime | None
    sort_index: int
    gap_label: str


@dataclass
class PairSummary:
    exact_shared_commits: int
    left_only_commits: int
    right_only_commits: int
    nearest_gap_days: float | None
    pattern_label: str
    pattern_tone: str


def create_app(cache_directory: str | None = None, data_directory: str | None = None) -> "HistoryViewerApp":
    return HistoryViewerApp(HistoryRepository(cache_directory=cache_directory, data_directory=data_directory))


class HistoryViewerApp:
    def __init__(self, repository: HistoryRepository):
        self.repository = repository

    def __call__(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        try:
            method = environ.get("REQUEST_METHOD", "GET").upper()
            path = environ.get("PATH_INFO", "/")

            if method == "GET" and path == "/":
                return self._respond_html(start_response, render_page("Method Co-Evolution Viewer", self._render_home()))
            if method == "GET" and path == "/revision":
                return self._handle_revision(environ, start_response)
            if method == "GET" and path == "/sample":
                return self._handle_sample(environ, start_response)
            if method == "GET" and path == "/api/history-json":
                return self._handle_history_json(environ, start_response)
            if method == "POST" and path == "/api/notes":
                return self._handle_update_note(environ, start_response)
            if method == "POST" and path == "/api/revision-links":
                return self._handle_write_revision_links(environ, start_response)

            return self._respond_html(start_response, render_page("Not Found", self._render_error("Route not found")), status="404 Not Found")
        except Exception as exc:  # pragma: no cover - safety net for interactive app
            content = self._render_error(f"{exc}", traceback.format_exc())
            return self._respond_html(start_response, render_page("Error", content), status="500 Internal Server Error")

    def _handle_revision(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        params = _query_params(environ)
        tool = params.get("tool") or _infer_tool_from_query(params)
        if not tool:
            raise ValueError("Pass tool=historyFinder or tool=codeShovel")

        from_history = self.repository.load_history(tool=tool, url=params.get("from_url", ""), file_path=params.get("from_file", ""))
        to_history = self.repository.load_history(tool=tool, url=params.get("to_url", ""), file_path=params.get("to_file", ""))

        sample_row = None
        sample_csv = params.get("sample_csv", "")
        if sample_csv and params.get("from_url") and params.get("to_url"):
            sample_row = self.repository.read_sample_row(sample_csv, from_url=params["from_url"], to_url=params["to_url"])

        content = self._render_revision(
            from_history=from_history,
            to_history=to_history,
            sample_row=sample_row,
            sample_csv=sample_csv,
            related_source=params.get("related_source", ""),
            calling_source=params.get("calling_source", ""),
        )
        return self._respond_html(start_response, render_page("Method History Revision", content))

    def _handle_sample(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        params = _query_params(environ)
        sample_dir = params.get("sample_dir", "")
        sample_csv = params.get("sample_csv", "")
        if sample_dir:
            csv_files = self.repository.list_sample_csv_files(sample_dir)
            content = self._render_sample_directory(sample_dir=sample_dir, csv_files=csv_files)
            return self._respond_html(start_response, render_page("Sample Directory", content))
        if not sample_csv:
            raise ValueError("Pass sample_dir=<sample directory> or sample_csv=<absolute path to a sampled CSV>")
        rows = self.repository.read_sample_rows(sample_csv)
        page_size = 20
        page = max(1, int(params.get("page", "1")))
        total_rows = len(rows)
        total_pages = max(1, math.ceil(total_rows / page_size))
        page = min(page, total_pages)
        start_index = (page - 1) * page_size
        end_index = start_index + page_size
        content = self._render_sample_table(
            sample_csv=sample_csv,
            rows=rows[start_index:end_index],
            total_rows=total_rows,
            base_url=_request_base_url(environ),
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            start_index=start_index,
        )
        return self._respond_html(start_response, render_page("Sample CSV", content))

    def _handle_update_note(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        payload = _read_payload(environ)
        updated = self.repository.update_sample_note(
            payload["sample_csv"],
            from_url=payload["from_url"],
            to_url=payload["to_url"],
            notes=payload.get("notes", ""),
            tags=payload.get("tags", ""),
        )
        response = {
            "ok": True,
            "row_index": updated.row_index,
            "row_token": build_row_token(updated.csv_path, updated.values.get("from_url", ""), updated.values.get("to_url", "")),
            "notes": updated.notes,
            "tags": updated.tags,
        }
        return self._respond_json(start_response, response)

    def _handle_write_revision_links(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        payload = _read_payload(environ)
        base_url = payload.get("base_url") or _request_base_url(environ)
        row_count = self.repository.write_revision_links(payload["sample_csv"], base_url=base_url)
        return self._respond_json(start_response, {"ok": True, "rows": row_count, "base_url": base_url})

    def _handle_history_json(self, environ: dict[str, Any], start_response: Any) -> Iterable[bytes]:
        params = _query_params(environ)
        side = params.get("side", "from")
        if side not in {"from", "to"}:
            raise ValueError("side must be from or to")
        tool = params.get("tool") or _infer_tool_from_query(params)
        if not tool:
            raise ValueError("Pass tool=historyFinder or tool=codeShovel")

        history = self.repository.load_history(
            tool=tool,
            url=params.get(f"{side}_url", ""),
            file_path=params.get(f"{side}_file", ""),
        )
        body = dump_json_bytes(history.raw)
        headers = [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))]
        if params.get("download") == "1":
            headers.append(("Content-Disposition", f'attachment; filename="{safe_json_filename(history)}"'))
        start_response("200 OK", headers)
        return [body]

    def _render_home(self) -> str:
        cache_dir = html.escape(str(self.repository.cache_directory))
        sample_hint = html.escape(str(self.repository.data_directory / "aggregate"))
        return f"""
<main>
  <section class="hero">
    <div class="eyebrow">Method Evolution UI</div>
    <h1>Inspect how test and production methods move together</h1>
    <p>Use GitHub method URLs, cached history JSON files, or a sampled CSV. The viewer aligns both histories on one timeline so you can spot direct co-evolution, lagged follow-up changes, and long periods where the two sides drift apart.</p>
    <p class="muted">Default cache root: <span class="mono">{cache_dir}</span></p>
  </section>

  <section class="grid">
    <article class="card">
      <div class="eyebrow">Use Case 1</div>
      <h2>Compare by URL</h2>
      <p class="muted">Best when you already have a test method link and a production method link from GitHub.</p>
      <form method="get" action="/revision">
        <label>Tool
          <select name="tool">
            <option value="historyFinder">historyFinder</option>
            <option value="codeShovel">codeShovel</option>
          </select>
        </label>
        <label>From URL
          <input type="text" name="from_url" placeholder="https://github.com/.../blob/<commit>/...#L17" />
        </label>
        <label>To URL
          <input type="text" name="to_url" placeholder="https://github.com/.../blob/<commit>/...#L29" />
        </label>
        <button type="submit">Open comparison</button>
      </form>
    </article>

    <article class="card">
      <div class="eyebrow">Use Case 1</div>
      <h2>Compare by cached JSON</h2>
      <p class="muted">Best when you already know the exact method-history JSON files.</p>
      <form method="get" action="/revision">
        <label>Tool
          <select name="tool">
            <option value="historyFinder">historyFinder</option>
            <option value="codeShovel">codeShovel</option>
          </select>
        </label>
        <label>From file
          <input type="text" name="from_file" placeholder="/Users/.../.cache/history/...json" />
        </label>
        <label>To file
          <input type="text" name="to_file" placeholder="/Users/.../.cache/history/...json" />
        </label>
        <button type="submit">Open comparison</button>
      </form>
    </article>

    <article class="card">
      <div class="eyebrow">Use Case 2</div>
      <h2>Browse a sample directory</h2>
      <p class="muted">Open a sample directory first, choose one CSV, then inspect rows in the browser and write a <span class="mono">revision_url</span> column that DBeaver can click directly.</p>
      <form method="get" action="/sample">
        <label>Sample directory
          <input type="text" name="sample_dir" value="{sample_hint}" />
        </label>
        <button type="submit">Open directory</button>
      </form>
    </article>
  </section>
</main>
"""

    def _render_revision(
        self,
        *,
        from_history: MethodHistory,
        to_history: MethodHistory,
        sample_row: SampleRow | None,
        sample_csv: str,
        related_source: str,
        calling_source: str,
    ) -> str:
        rows = build_timeline_rows(from_history.entries, to_history.entries)
        summary = build_pair_summary(from_history.entries, to_history.entries)
        change_count_summary = build_change_count_summary(from_history.raw, to_history.raw)
        source_options = self.repository.related_source_options(
            tool=from_history.tool or to_history.tool,
            sample_csv=sample_csv,
        )
        effective_related_source = related_source or (source_options[0] if source_options else "")
        effective_calling_source = calling_source or (source_options[0] if source_options else "")
        query_params = {
            "tool": from_history.tool or to_history.tool,
            "sample_csv": sample_csv,
            "from_url": from_history.input_url,
            "to_url": to_history.input_url,
            "from_file": from_history.input_file,
            "to_file": to_history.input_file,
            "related_source": effective_related_source,
            "calling_source": effective_calling_source,
        }
        related_methods: list[RelatedMethod] = []
        related_source_label = ""
        searched_related_labels: list[str] = []
        calling_methods: list[CallingMethod] = []
        calling_source_label = ""
        searched_calling_labels: list[str] = []
        calling_source = query_params.get("calling_source", "")
        current_from_url = from_history.input_url or (sample_row.values.get("from_url", "") if sample_row is not None else "")
        current_to_url = to_history.input_url or (sample_row.values.get("to_url", "") if sample_row is not None else "")
        if current_from_url:
            related_methods, searched_related_labels = self.repository.find_related_production_methods(
                project=from_history.project or to_history.project,
                from_url=current_from_url,
                tool=from_history.tool or to_history.tool,
                sample_csv=sample_csv,
                selected_source=effective_related_source,
            )
            if related_methods:
                related_source_label = related_methods[0].source_label
        if current_to_url:
            calling_methods, searched_calling_labels = self.repository.find_calling_test_methods(
                project=from_history.project or to_history.project,
                to_url=current_to_url,
                tool=from_history.tool or to_history.tool,
                sample_csv=sample_csv,
                selected_source=effective_calling_source,
            )
            if calling_methods:
                calling_source_label = calling_methods[0].source_label
        note_panel = ""
        if sample_row is not None:
            note_panel = self._render_note_panel(sample_row, sample_csv)

        return f"""
<main>
  <section class="hero">
    <div class="eyebrow">Revision Viewer</div>
    <h1>{html.escape(summary.pattern_label)}</h1>
    <p>This view keeps both method histories on one descending timeline. Same-commit changes share a row, while unmatched changes show the nearest opposite-side gap so you can quickly see whether the test and source methods co-evolved or drifted.</p>
    <div class="chip-row">
      <span class="chip {html.escape(summary.pattern_tone)}">{html.escape(summary.pattern_label)}</span>
      <span class="chip">Tool: {html.escape(from_history.tool)}</span>
      <span class="chip">Project: {html.escape(from_history.project or to_history.project)}</span>
    </div>
    {render_tool_switch_links(query_params=query_params)}
  </section>

  <section class="stats">
    <article class="summary-card">
      <div class="eyebrow">Shared Commits</div>
      <strong>{summary.exact_shared_commits}</strong>
      <p class="muted">Changes recorded on the same commit hash.</p>
    </article>
    <article class="summary-card">
      <div class="eyebrow">Test-Only Changes</div>
      <strong>{summary.left_only_commits}</strong>
      <p class="muted">Commits seen only on the left side.</p>
    </article>
    <article class="summary-card">
      <div class="eyebrow">Production-Only Changes</div>
      <strong>{summary.right_only_commits}</strong>
      <p class="muted">Commits seen only on the right side.</p>
    </article>
    <article class="summary-card">
      <div class="eyebrow">Nearest Gap</div>
      <strong>{format_days(summary.nearest_gap_days)}</strong>
      <p class="muted">Smallest time gap between any left and right change.</p>
    </article>
  </section>

  <section class="methods">
    {self._render_method_panel("Test / From", from_history, side="from", query_params=query_params, related_methods=related_methods, related_source_label=related_source_label, searched_related_labels=searched_related_labels)}
    {self._render_method_panel("Production / To", to_history, side="to", query_params=query_params, calling_methods=calling_methods, calling_source_label=calling_source_label, searched_calling_labels=searched_calling_labels)}
  </section>

  {render_change_count_summary_table(change_count_summary)}

  <section class="panel">
    <div class="eyebrow">Timeline</div>
    <h2 style="margin-top:10px;">Change history, newest first</h2>
    <div class="timeline" style="margin-top:18px;">
      {''.join(render_timeline_row(row) for row in rows)}
    </div>
  </section>

  {note_panel}
</main>
{NOTE_SCRIPT}
"""

    def _render_method_panel(
        self,
        title: str,
        history: MethodHistory,
        *,
        side: str,
        query_params: dict[str, str],
        related_methods: list[RelatedMethod] | None = None,
        related_source_label: str = "",
        searched_related_labels: list[str] | None = None,
        calling_methods: list[CallingMethod] | None = None,
        calling_source_label: str = "",
        searched_calling_labels: list[str] | None = None,
    ) -> str:
        links = []
        if history.input_file:
            links.append(f'<span class="mono">{html.escape(history.input_file)}</span>')
        json_view_url = build_history_json_url(side=side, query_params=query_params, download=False)
        json_download_url = build_history_json_url(side=side, query_params=query_params, download=True)
        related_html = ""
        if side == "from":
            related_html = self._render_related_methods(
                related_methods=related_methods or [],
                related_source_label=related_source_label,
                searched_related_labels=searched_related_labels or [],
                query_params=query_params,
                source_options=self.repository.related_source_options(tool=history.tool, sample_csv=query_params.get("sample_csv", "")),
            )
        elif side == "to":
            related_html = self._render_calling_methods(
                calling_methods=calling_methods or [],
                calling_source_label=calling_source_label,
                searched_calling_labels=searched_calling_labels or [],
                query_params=query_params,
                source_options=self.repository.related_source_options(tool=history.tool, sample_csv=query_params.get("sample_csv", "")),
            )
        method_name = html.escape(history.function_name or history.function_id or "Unknown method")
        method_heading = method_name
        if history.input_url:
            method_heading = (
                f'<a href="{html.escape(history.input_url)}" target="_blank" rel="noreferrer">{method_name}</a>'
            )
        return f"""
<article class="panel method-panel">
  <div class="eyebrow">{html.escape(title)}</div>
  <h2>{method_heading}</h2>
  <p class="mono" style="margin-top:10px;">{html.escape(history.source_file_path)}:{history.function_start_line}</p>
  <p class="muted" style="margin-top:10px;">{len(history.entries)} change commit(s)</p>
  <div class="chip-row">
    <span class="chip">Origin: {html.escape(history.origin or history.tool)}</span>
    <span class="chip">Start line: {history.function_start_line}</span>
  </div>
  <div class="button-row" style="margin-top:14px;">
    <a href="{html.escape(json_download_url)}" class="chip" target="_blank" rel="noreferrer">Download JSON</a>
    <button type="button" class="secondary copy-json-button" data-json-url="{html.escape(json_view_url)}">Copy JSON</button>
    <span class="flash json-copy-status" style="display:none;"></span>
  </div>
  {related_html}
  <div style="margin-top:14px; display:grid; gap:8px;">{''.join(links)}</div>
</article>
"""

    def _render_related_methods(
        self,
        *,
        related_methods: list[RelatedMethod],
        related_source_label: str,
        searched_related_labels: list[str],
        query_params: dict[str, str],
        source_options: list[str],
    ) -> str:
        selected_source = query_params.get("related_source", "") or (source_options[0] if source_options else "")
        option_html = "".join(
            f'<option value="{html.escape(option)}"{" selected" if option == selected_source else ""}>{html.escape(option)}</option>'
            for option in source_options
        )
        if related_methods:
            items = []
            for method in related_methods:
                revision_url = build_related_revision_url(query_params=query_params, to_url=method.to_url)
                items.append(
                    f'<li><a href="{html.escape(revision_url)}">{html.escape(method.to_name)}</a></li>'
                )
            return f"""
<div style="margin-top:16px;">
  <div class="eyebrow">Tested Production Methods</div>
  {render_related_source_form(query_params=query_params, option_html=option_html, field_name="related_source")}
  <p class="muted" style="margin-top:8px;">Loaded from <span class="mono">{html.escape(related_source_label)}</span></p>
  <div style="margin-top:10px;">
    <ul style="margin:0; padding-left:20px; display:grid; gap:8px;">
      {''.join(items)}
    </ul>
  </div>
</div>
"""

        searched = ", ".join(searched_related_labels) if searched_related_labels else "t2p-link, t2p-candidate, m2m-tech, fan-out"
        return f"""
<div style="margin-top:16px;">
  <div class="eyebrow">Tested Production Methods</div>
  {render_related_source_form(query_params=query_params, option_html=option_html, field_name="related_source")}
  <p class="muted" style="margin-top:8px;">No matching production methods found. Searched in <span class="mono">{html.escape(searched)}</span></p>
</div>
"""

    def _render_calling_methods(
        self,
        *,
        calling_methods: list[CallingMethod],
        calling_source_label: str,
        searched_calling_labels: list[str],
        query_params: dict[str, str],
        source_options: list[str],
    ) -> str:
        selected_source = query_params.get("calling_source", "") or (source_options[0] if source_options else "")
        option_html = "".join(
            f'<option value="{html.escape(option)}"{" selected" if option == selected_source else ""}>{html.escape(option)}</option>'
            for option in source_options
        )
        if calling_methods:
            items = []
            for method in calling_methods:
                revision_url = build_related_revision_url(query_params=query_params, from_url=method.from_url)
                items.append(
                    f'<li><a href="{html.escape(revision_url)}">{html.escape(method.from_name)}</a></li>'
                )
            return f"""
<div style="margin-top:16px;">
  <div class="eyebrow">Calling Test Methods</div>
  {render_related_source_form(query_params=query_params, option_html=option_html, field_name="calling_source")}
  <p class="muted" style="margin-top:8px;">Loaded from <span class="mono">{html.escape(calling_source_label)}</span></p>
  <div style="margin-top:10px;">
    <ul style="margin:0; padding-left:20px; display:grid; gap:8px;">
      {''.join(items)}
    </ul>
  </div>
</div>
"""

        searched = ", ".join(searched_calling_labels) if searched_calling_labels else "t2p-link, t2p-candidate, m2m-tech, fan-out"
        return f"""
<div style="margin-top:16px;">
  <div class="eyebrow">Calling Test Methods</div>
  {render_related_source_form(query_params=query_params, option_html=option_html, field_name="calling_source")}
  <p class="muted" style="margin-top:8px;">No matching test methods found. Searched in <span class="mono">{html.escape(searched)}</span></p>
</div>
"""

    def _render_note_panel(self, sample_row: SampleRow, sample_csv: str) -> str:
        token = build_row_token(sample_row.csv_path, sample_row.values.get("from_url", ""), sample_row.values.get("to_url", ""))
        return f"""
<section class="panel">
  <div class="eyebrow">Research Notes</div>
  <h2 style="margin-top:10px;">Save manual review notes and tags back to the sampled CSV</h2>
  <p class="muted" style="margin-top:8px;">This updates the <span class="mono">notes</span> and <span class="mono">tags</span> columns in place for the current row.</p>
  <form id="note-form" data-row-token="{html.escape(token)}">
    <input type="hidden" name="sample_csv" value="{html.escape(sample_csv)}" />
    <input type="hidden" name="from_url" value="{html.escape(sample_row.values.get('from_url', ''))}" />
    <input type="hidden" name="to_url" value="{html.escape(sample_row.values.get('to_url', ''))}" />
    <label>Tags
      <input type="text" name="tags" value="{html.escape(sample_row.tags)}" placeholder="coupled, flaky, review-later" />
    </label>
    <label>Notes
      <textarea name="notes">{html.escape(sample_row.notes)}</textarea>
    </label>
    <div class="button-row">
      <button type="submit">Save notes and tags</button>
      <span id="note-status" class="flash" style="display:none;"></span>
    </div>
  </form>
</section>
"""

    def _render_sample_table(
        self,
        *,
        sample_csv: str,
        rows: list[SampleRow],
        total_rows: int,
        base_url: str,
        page: int,
        page_size: int,
        total_pages: int,
        start_index: int,
    ) -> str:
        table_rows = []
        for row in rows:
            values = row.values
            from_name = values.get("from_name", "")
            to_name = values.get("to_name", "")
            revision_url = values.get("revision_url") or self.repository.build_revision_url(
                base_url=base_url,
                csv_path=sample_csv,
                from_url=values.get("from_url", ""),
                to_url=values.get("to_url", ""),
                tool=values.get("tool", ""),
                project=values.get("project", ""),
            )
            table_rows.append(
                f"""
<tr>
  <td>{html.escape(values.get('project', ''))}</td>
  <td><strong title="{html.escape(from_name)}">{html.escape(truncate_display_text(from_name))}</strong></td>
  <td><strong title="{html.escape(to_name)}">{html.escape(truncate_display_text(to_name))}</strong></td>
  <td>{html.escape(values.get('tool', ''))}</td>
  <td><a href="{html.escape(revision_url)}" target="_blank" rel="noreferrer">Open revision</a></td>
  <td>{html.escape(values.get('tags', '')) or '<span class="muted">No tags</span>'}</td>
  <td>{html.escape(values.get('notes', '')) or '<span class="muted">No notes</span>'}</td>
</tr>
"""
            )

        end_index = start_index + len(rows)
        previous_link = ""
        next_link = ""
        if page > 1:
            previous_link = (
                f'<a class="secondary" href="/sample?sample_csv={quote(sample_csv, safe="")}&page={page - 1}">'
                "Previous"
                "</a>"
            )
        if page < total_pages:
            next_link = (
                f'<a class="secondary" href="/sample?sample_csv={quote(sample_csv, safe="")}&page={page + 1}">'
                "Next"
                "</a>"
            )

        return f"""
<main>
  <section class="hero">
    <div class="eyebrow">Sample Browser</div>
    <h1>{html.escape(sample_csv)}</h1>
    <p>Showing rows {start_index + 1}-{end_index} of {total_rows}. Open a row directly from here, or persist a <span class="mono">revision_url</span> column for DBeaver.</p>
    <div class="button-row" style="margin-top:12px;">
      <button class="secondary" id="revision-link-button" data-sample-csv="{html.escape(sample_csv)}" data-base-url="{html.escape(base_url)}">Write revision_url column</button>
      <span id="revision-link-status" class="flash" style="display:none;"></span>
    </div>
    <div class="button-row" style="margin-top:12px;">
      {previous_link}
      <span class="muted">Page {page} of {total_pages} · 20 methods per page</span>
      {next_link}
    </div>
  </section>

  <section class="panel" style="margin-top:24px;">
    <div class="eyebrow">Rows</div>
    <table>
      <thead>
        <tr>
          <th>Project</th>
          <th>From</th>
          <th>To</th>
          <th>Tool</th>
          <th>Revision</th>
          <th>Tags</th>
          <th>Notes</th>
        </tr>
      </thead>
      <tbody>
        {''.join(table_rows)}
      </tbody>
    </table>
  </section>
</main>
{REVISION_LINK_SCRIPT}
"""

    def _render_sample_directory(self, *, sample_dir: str, csv_files: list[Any]) -> str:
        file_links = []
        for csv_file in csv_files:
            file_links.append(
                f"""
<tr>
  <td><a href="/sample?sample_csv={quote(str(csv_file), safe='')}">{html.escape(csv_file.name)}</a></td>
  <td><span class="mono">{html.escape(str(csv_file))}</span></td>
</tr>
"""
            )

        if not file_links:
            file_links.append(
                """
<tr>
  <td colspan="2"><span class="muted">No CSV files found in this directory.</span></td>
</tr>
"""
            )

        return f"""
<main>
  <section class="hero">
    <div class="eyebrow">Sample Directory</div>
    <h1>{html.escape(sample_dir)}</h1>
    <p>Select a CSV file to see the sampled method pairs.</p>
  </section>

  <section class="panel" style="margin-top:24px;">
    <div class="eyebrow">CSV Files</div>
    <table>
      <thead>
        <tr>
          <th>File</th>
          <th>Path</th>
        </tr>
      </thead>
      <tbody>
        {''.join(file_links)}
      </tbody>
    </table>
  </section>
</main>
"""

    def _render_error(self, message: str, detail: str = "") -> str:
        detail_html = f"<pre>{html.escape(detail)}</pre>" if detail else ""
        return f"""
<main>
  <section class="hero">
    <div class="eyebrow">Viewer Error</div>
    <h1>Something blocked the viewer</h1>
    <div class="flash error">{html.escape(message)}</div>
    {detail_html}
  </section>
</main>
"""

    def _respond_html(self, start_response: Any, content: str, status: str = "200 OK") -> Iterable[bytes]:
        body = content.encode("utf-8")
        start_response(status, [("Content-Type", "text/html; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]

    def _respond_json(self, start_response: Any, payload: dict[str, Any], status: str = "200 OK") -> Iterable[bytes]:
        body = dump_json_bytes(payload)
        start_response(status, [("Content-Type", "application/json; charset=utf-8"), ("Content-Length", str(len(body)))])
        return [body]


def render_page(title: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{html.escape(title)}</title>
  {STYLE}
</head>
<body>{content}</body>
</html>"""


def build_timeline_rows(left_entries: list[CommitEntry], right_entries: list[CommitEntry]) -> list[TimelineRow]:
    right_by_hash = {entry.commit_hash: entry for entry in right_entries}
    used_right_hashes: set[str] = set()
    rows: list[TimelineRow] = []

    for index, left_entry in enumerate(left_entries):
        paired_right = right_by_hash.get(left_entry.commit_hash)
        if paired_right is not None:
            used_right_hashes.add(paired_right.commit_hash)
        rows.append(
            TimelineRow(
                left=left_entry,
                right=paired_right,
                sort_date=max_datetime(left_entry.commit_date, paired_right.commit_date if paired_right else None),
                sort_index=index,
                gap_label=row_gap_label(left_entry, paired_right, right_entries),
            )
        )

    for index, right_entry in enumerate(right_entries, start=len(rows)):
        if right_entry.commit_hash in used_right_hashes:
            continue
        rows.append(
            TimelineRow(
                left=None,
                right=right_entry,
                sort_date=right_entry.commit_date,
                sort_index=index,
                gap_label=row_gap_label(None, right_entry, left_entries),
            )
        )

    rows.sort(key=lambda row: (row.sort_date or datetime.min, -row.sort_index), reverse=True)
    return rows


def build_pair_summary(left_entries: list[CommitEntry], right_entries: list[CommitEntry]) -> PairSummary:
    left_hashes = {entry.commit_hash for entry in left_entries}
    right_hashes = {entry.commit_hash for entry in right_entries}
    shared = len(left_hashes & right_hashes)
    left_only = len(left_hashes - right_hashes)
    right_only = len(right_hashes - left_hashes)

    nearest_gap: float | None = None
    right_dates = [entry.commit_date for entry in right_entries if entry.commit_date is not None]
    for left_entry in left_entries:
        if left_entry.commit_date is None:
            continue
        for right_date in right_dates:
            gap = abs((left_entry.commit_date - right_date).total_seconds()) / 86400.0
            nearest_gap = gap if nearest_gap is None else min(nearest_gap, gap)

    if shared > 0:
        label, tone = "Direct co-evolution", ""
    elif nearest_gap is not None and nearest_gap <= 7:
        label, tone = "Lagged co-evolution", "warn"
    else:
        label, tone = "Mostly separate evolution", "danger"

    return PairSummary(
        exact_shared_commits=shared,
        left_only_commits=left_only,
        right_only_commits=right_only,
        nearest_gap_days=nearest_gap,
        pattern_label=label,
        pattern_tone=tone,
    )


def render_timeline_row(row: TimelineRow) -> str:
    left_html = render_event_card(row.left, side="left")
    right_html = render_event_card(row.right, side="right")
    marker_html = []
    if row.left is not None:
        marker_html.append('<span class="marker"></span>')
    if row.right is not None:
        marker_html.append('<span class="marker right"></span>')

    return f"""
<article class="timeline-row">
  <div>{left_html}</div>
  <div class="timeline-center">
    <div class="marker-stack">{''.join(marker_html)}</div>
    <div class="gap-label">{html.escape(row.gap_label)}</div>
  </div>
  <div>{right_html}</div>
</article>
"""


def render_event_card(entry: CommitEntry | None, *, side: str) -> str:
    if entry is None:
        return "<div></div>"

    css_class = "event-card right" if side == "right" else "event-card"
    date_value = format_commit_datetime(entry.commit_date, entry.commit_date_raw)
    change_labels = entry.display_change_tags or entry.change_types
    change_chip_html = "".join(render_change_chip(change_label) for change_label in change_labels)
    change_types = ", ".join(entry.change_types)
    link_lines = []
    if entry.commit_url:
        link_lines.append(f'<a href="{html.escape(entry.commit_url)}" target="_blank" rel="noreferrer">Commit</a>')
    if entry.new_file_url:
        link_lines.append(f'<a href="{html.escape(entry.new_file_url)}" target="_blank" rel="noreferrer">Method URL</a>')
    if entry.old_file_url:
        link_lines.append(f'<a href="{html.escape(entry.old_file_url)}" target="_blank" rel="noreferrer">Previous Method URL</a>')
    if entry.diff_url:
        link_lines.append(f'<a href="{html.escape(entry.diff_url)}" target="_blank" rel="noreferrer">Diff URL</a>')

    return f"""
<details class="{css_class}">
  <summary>
    <div class="event-header">
      <div class="event-meta">
        <span class="meta-pill">{html.escape(entry.short_hash)}</span>
        <span class="meta-pill">{html.escape(date_value)}</span>
        <span class="meta-pill">{format_days(entry.days_between_commits)}</span>
      </div>
      <div class="chip-row">{change_chip_html}</div>
      <strong>{html.escape(entry.commit_message or "No commit message")}</strong>
      <span class="muted">{html.escape(entry.commit_author or "Unknown author")} · {html.escape(entry.path)}</span>
    </div>
  </summary>
  <div class="detail-grid">
    <div class="chip-row">
      <span class="chip">Types: {html.escape(change_types)}</span>
    </div>
    <div>{' · '.join(link_lines)}</div>
    <div>
      <div class="eyebrow">Diff</div>
      {render_diff_html(entry.diff, modal_id=f"diff-modal-{side}-{entry.short_hash}", title=entry.path)}
    </div>
  </div>
</details>
"""


def max_datetime(first: datetime | None, second: datetime | None) -> datetime | None:
    if first is None:
        return second
    if second is None:
        return first
    return max(first, second)


def nearest_gap_days(target: CommitEntry, others: list[CommitEntry]) -> float | None:
    if target.commit_date is None:
        return None
    gaps = [
        abs((target.commit_date - other.commit_date).total_seconds()) / 86400.0
        for other in others
        if other.commit_date is not None
    ]
    return min(gaps) if gaps else None


def row_gap_label(left: CommitEntry | None, right: CommitEntry | None, others: list[CommitEntry]) -> str:
    if left is not None and right is not None:
        return "same commit"
    target = left or right
    gap = nearest_gap_days(target, others) if target is not None else None
    if gap is None:
        return "no time gap"
    return f"nearest {format_days(gap)}"


def format_days(value: float | None) -> str:
    if value is None:
        return "n/a"
    if value == 0:
        return "0.0 d"
    if value < 1:
        return f"{value * 24:.1f} h"
    return f"{value:.1f} d"


def format_commit_datetime(value: datetime | None, fallback: str) -> str:
    if value is None:
        return fallback or "Unknown date"
    return f"{value.year} {value.strftime('%B')} {value.day}, {value.strftime('%H:%M')}"


def truncate_display_text(value: str, max_chars: int = 36) -> str:
    text = value.strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 3:
        return "." * max_chars
    return f"{text[:max_chars - 3]}..."


def build_change_count_summary(from_raw: dict[str, Any], to_raw: dict[str, Any]) -> list[tuple[str, int, int]]:
    from_counts = extract_change_count(from_raw)
    to_counts = extract_change_count(to_raw)
    ordered_keys = [
        "ch_all",
        "ch_diff",
        "ch_introduction",
        "ch_body",
        "ch_rename",
        "ch_move",
        "ch_file_move",
        "ch_documentation",
        "ch_modifier",
        "ch_return_type",
        "ch_exception",
        "ch_parameter",
        "ch_parameter_meta",
        "ch_annotation",
        "ch_format",
        "ch_multi",
    ]
    summary_rows: list[tuple[str, int, int]] = []
    for key in ordered_keys:
        from_value = int(from_counts.get(key, 0))
        to_value = int(to_counts.get(key, 0))
        if key not in {"ch_all", "ch_diff"} and from_value == 0 and to_value == 0:
            continue
        summary_rows.append((change_count_label(key), from_value, to_value))
    return summary_rows


def change_count_label(key: str) -> str:
    labels = {
        "ch_all": "All commits",
        "ch_diff": "Commits with diff",
        "ch_introduction": "Introduction",
        "ch_body": "Body",
        "ch_rename": "Rename",
        "ch_move": "Move",
        "ch_file_move": "File move",
        "ch_documentation": "Documentation",
        "ch_modifier": "Modifier",
        "ch_return_type": "Return type",
        "ch_exception": "Exception",
        "ch_parameter": "Parameter",
        "ch_parameter_meta": "Parameter meta",
        "ch_annotation": "Annotation",
        "ch_format": "Format",
        "ch_multi": "Multi",
    }
    return labels.get(key, key.removeprefix("ch_").replace("_", " ").title())


def render_change_count_summary_table(summary_rows: list[tuple[str, int, int]]) -> str:
    table_rows = "".join(
        f"""
<tr>
  <td>{html.escape(label)}</td>
  <td>{from_count}</td>
  <td>{to_count}</td>
  <td>{render_change_count_trend(from_count, to_count)}</td>
</tr>
"""
        for label, from_count, to_count in summary_rows
    )
    return f"""
<section class="panel" style="margin-top:24px;">
  <div class="eyebrow">Change Summary</div>
  <h2 style="margin-top:10px;">Change count summary</h2>
  <p class="muted" style="margin-top:8px;">Counts are extracted from each method history JSON using the shared change-count helper.</p>
  <table>
    <thead>
      <tr>
        <th>Change Type</th>
        <th>Test</th>
        <th>Production</th>
        <th>Trend</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</section>
"""


def render_change_count_trend(from_count: int, to_count: int) -> str:
    if from_count > to_count:
        return f'<span class="trend-up">&uarr; {from_count - to_count}</span>'
    if from_count < to_count:
        return f'<span class="trend-down">&darr; {to_count - from_count}</span>'
    return '<span class="trend-flat">-</span>'


def render_change_chip(label: str) -> str:
    chip_class = f"chip {change_type_chip_class(label)}"
    return f'<span class="{html.escape(chip_class)}">{html.escape(label)}</span>'


def change_type_chip_class(label: str) -> str:
    normalized = (
        label.strip().lower()
        .replace(" ", "-")
        .replace("_", "-")
    )
    aliases = {
        "introduction": "type-introduction",
        "yintroduced": "type-introduction",
        "body": "type-body",
        "ybodychange": "type-body",
        "rename": "type-rename",
        "yrename": "type-rename",
        "move": "type-move",
        "ymovefromfile": "type-move",
        "file-move": "type-file-move",
        "file-move/rename": "type-file-move",
        "yfilerename": "type-file-move",
        "documentation": "type-documentation",
        "ydocumentationchange": "type-documentation",
        "format": "type-format",
        "yformatchange": "type-format",
        "annotation": "type-annotation",
        "yannotationchnage": "type-annotation",
        "modifier": "type-modifier",
        "ymodifierchange": "type-modifier",
        "return-type": "type-return-type",
        "yreturntypechange": "type-return-type",
        "exception": "type-exception",
        "exceptions": "type-exception",
        "yexceptionschange": "type-exception",
        "parameter": "type-parameter",
        "yparameterchange": "type-parameter",
        "parameter-meta": "type-parameter-meta",
        "yparametermetachange": "type-parameter-meta",
        "multi": "type-multi",
        "ymultichange": "type-multi",
        "unknown": "type-unknown",
    }
    return aliases.get(normalized, "type-unknown")


JAVA_KEYWORDS = (
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char", "class",
    "const", "continue", "default", "do", "double", "else", "enum", "extends", "final",
    "finally", "float", "for", "if", "goto", "implements", "import", "instanceof", "int",
    "interface", "long", "native", "new", "package", "private", "protected", "public",
    "record", "return", "sealed", "short", "static", "strictfp", "super", "switch",
    "synchronized", "this", "throw", "throws", "transient", "try", "var", "void",
    "volatile", "while", "yield", "true", "false", "null",
)


def highlight_java_code(text: str) -> str:
    escaped = html.escape(text)
    placeholders: dict[str, str] = {}

    def stash(pattern: str, css_class: str, source: str) -> str:
        def replace(match: re.Match[str]) -> str:
            token = f"__TOK{len(placeholders)}__"
            placeholders[token] = f'<span class="{css_class}">{match.group(0)}</span>'
            return token
        return re.sub(pattern, replace, source)

    escaped = stash(r"//.*$", "syntax-comment", escaped)
    escaped = stash(r'"(?:\\.|[^"])*"', "syntax-string", escaped)
    escaped = stash(r"'(?:\\.|[^'])*'", "syntax-string", escaped)
    escaped = stash(r"@\w+", "syntax-annotation", escaped)

    keyword_pattern = r"\b(" + "|".join(re.escape(keyword) for keyword in JAVA_KEYWORDS) + r")\b"
    escaped = re.sub(keyword_pattern, r'<span class="syntax-keyword">\1</span>', escaped)
    escaped = re.sub(r"\b(\d+(?:\.\d+)?)\b", r'<span class="syntax-number">\1</span>', escaped)

    for token, replacement in placeholders.items():
        escaped = escaped.replace(token, replacement)
    return escaped


def render_diff_html(diff_text: str, *, modal_id: str, title: str = "") -> str:
    if not diff_text.strip():
        return "<pre>No diff captured</pre>"

    rows = parse_unified_diff(diff_text)
    compact_rows = []
    table_rows = []
    word_rows = []
    inline_scroll_id = f"{modal_id}-inline-scroll"
    source_versions_html = render_source_versions_html(rows)
    for row in rows:
        if row["kind"] == "hunk":
            hunk_row = f'<tr class="diff-hunk"><td class="diff-line-no"></td><td class="diff-code" colspan="2">{html.escape(row["text"])}</td></tr>'
            compact_rows.append(hunk_row)
            table_rows.append(hunk_row)
            word_rows.append(hunk_row)
            continue
        if row["kind"] == "meta":
            meta_row = f'<tr class="diff-meta"><td class="diff-line-no"></td><td class="diff-code" colspan="2">{html.escape(row["text"])}</td></tr>'
            compact_rows.append(meta_row)
            table_rows.append(meta_row)
            word_rows.append(meta_row)
            continue

        compact_prefix = " "
        compact_kind = "context"
        compact_line_no = row.get("right_no") or row.get("left_no", "")
        compact_text = row.get("right_text") or row.get("left_text", "")
        if row.get("left_kind") == "del" and row.get("right_kind") == "add":
            compact_rows.append(
                f"""
<tr class="diff-del">
  <td class="diff-line-no diff-cell-del">{html.escape(row.get("left_no", ""))}</td>
  <td class="diff-code diff-cell-del"><span class="diff-mark">-</span>{highlight_java_code(row.get("left_text", ""))}</td>
</tr>
<tr class="diff-add">
  <td class="diff-line-no diff-cell-add">{html.escape(row.get("right_no", ""))}</td>
  <td class="diff-code diff-cell-add"><span class="diff-mark">+</span>{highlight_java_code(row.get("right_text", ""))}</td>
</tr>
"""
            )
            table_rows.append(
                f"""
<tr class="diff-{html.escape(row['kind'])}">
  <td class="diff-line-no diff-cell-{html.escape(row.get('left_kind', 'context'))}">{html.escape(row.get('left_no') or row.get('right_no', ''))}</td>
  <td class="diff-code diff-cell-{html.escape(row.get('left_kind', 'context'))} {'diff-code-empty' if not row.get('left_text') else ''}">{highlight_java_code(row.get('left_text', ''))}</td>
  <td class="diff-code diff-cell-{html.escape(row.get('right_kind', 'context'))} {'diff-code-empty' if not row.get('right_text') else ''}">{highlight_java_code(row.get('right_text', ''))}</td>
</tr>
"""
            )
            left_word_html, right_word_html = render_word_diff_cells(row.get("left_text", ""), row.get("right_text", ""))
            word_rows.append(
                f"""
<tr class="diff-{html.escape(row['kind'])}">
  <td class="diff-line-no diff-cell-{html.escape(row.get('left_kind', 'context'))}">{html.escape(row.get('left_no') or row.get('right_no', ''))}</td>
  <td class="diff-code diff-cell-{html.escape(row.get('left_kind', 'context'))} {'diff-code-empty' if not row.get('left_text') else ''}">{left_word_html}</td>
  <td class="diff-code diff-cell-{html.escape(row.get('right_kind', 'context'))} {'diff-code-empty' if not row.get('right_text') else ''}">{right_word_html}</td>
</tr>
"""
            )
            continue
        elif row.get("left_kind") == "del":
            compact_prefix = "-"
            compact_kind = "del"
            compact_line_no = row.get("left_no", "")
            compact_text = row.get("left_text", "")
        elif row.get("right_kind") == "add":
            compact_prefix = "+"
            compact_kind = "add"
            compact_line_no = row.get("right_no", "")
            compact_text = row.get("right_text", "")
        compact_rows.append(
            f"""
<tr class="diff-{html.escape(compact_kind)}">
  <td class="diff-line-no diff-cell-{html.escape(compact_kind)}">{html.escape(compact_line_no)}</td>
  <td class="diff-code diff-cell-{html.escape(compact_kind)}"><span class="diff-mark">{html.escape(compact_prefix)}</span>{highlight_java_code(compact_text)}</td>
</tr>
"""
        )
        table_rows.append(
            f"""
<tr class="diff-{html.escape(row['kind'])}">
  <td class="diff-line-no diff-cell-{html.escape(row.get('left_kind', 'context'))}">{html.escape(row.get('left_no') or row.get('right_no', ''))}</td>
  <td class="diff-code diff-cell-{html.escape(row.get('left_kind', 'context'))} {'diff-code-empty' if not row.get('left_text') else ''}">{highlight_java_code(row.get('left_text', ''))}</td>
  <td class="diff-code diff-cell-{html.escape(row.get('right_kind', 'context'))} {'diff-code-empty' if not row.get('right_text') else ''}">{highlight_java_code(row.get('right_text', ''))}</td>
</tr>
"""
        )
        word_rows.append(
            f"""
<tr class="diff-{html.escape(row['kind'])}">
  <td class="diff-line-no diff-cell-{html.escape(row.get('left_kind', 'context'))}">{html.escape(row.get('left_no') or row.get('right_no', ''))}</td>
  <td class="diff-code diff-cell-{html.escape(row.get('left_kind', 'context'))} {'diff-code-empty' if not row.get('left_text') else ''}">{highlight_java_code(row.get('left_text', ''))}</td>
  <td class="diff-code diff-cell-{html.escape(row.get('right_kind', 'context'))} {'diff-code-empty' if not row.get('right_text') else ''}">{highlight_java_code(row.get('right_text', ''))}</td>
</tr>
"""
        )

    return f"""
<div class="diff-panel compact">
  <div class="diff-toolbar">
    <div class="diff-toolbar-group">
      <button type="button" class="secondary diff-modal-open" data-modal-id="{html.escape(modal_id)}">Open split view</button>
      <button type="button" class="secondary diff-scroll-button" data-scroll-target="{html.escape(inline_scroll_id)}" data-scroll-direction="left">Scroll left</button>
      <button type="button" class="secondary diff-scroll-button" data-scroll-target="{html.escape(inline_scroll_id)}" data-scroll-direction="right">Scroll right</button>
    </div>
    <span>Scroll sideways for long lines</span>
  </div>
  <div class="diff-scroll" id="{html.escape(inline_scroll_id)}">
    <table class="diff-table unified">
      <tbody>
        {''.join(compact_rows)}
      </tbody>
    </table>
  </div>
</div>
<div class="diff-modal" id="{html.escape(modal_id)}" aria-hidden="true">
  <div class="diff-modal-card">
    <div class="diff-modal-header">
      <div style="display:grid; gap:4px;">
        <strong>Split Diff View</strong>
        <span class="mono muted">{html.escape(title)}</span>
      </div>
      <button type="button" class="secondary diff-modal-close" data-modal-id="{html.escape(modal_id)}">Close</button>
    </div>
    <div class="diff-modal-body">
      <div class="diff-modal-controls">
        <button type="button" class="secondary diff-view-toggle active" data-modal-id="{html.escape(modal_id)}" data-view="diff">Split diff</button>
        <button type="button" class="secondary diff-view-toggle" data-modal-id="{html.escape(modal_id)}" data-view="word">Word diff</button>
        <button type="button" class="secondary diff-view-toggle" data-modal-id="{html.escape(modal_id)}" data-view="source">Source versions</button>
      </div>
      <div class="diff-modal-view open" data-modal-id="{html.escape(modal_id)}" data-view="diff">
        <div class="diff-panel github-split">
          <div class="diff-toolbar">
            <span>{html.escape(title or "Diff")}</span>
            <span>Split View</span>
          </div>
          <table class="diff-table">
            <tbody>
              {''.join(table_rows)}
            </tbody>
          </table>
        </div>
      </div>
      <div class="diff-modal-view" data-modal-id="{html.escape(modal_id)}" data-view="word">
        <div class="diff-panel github-split">
          <div class="diff-toolbar">
            <span>{html.escape(title or "Diff")}</span>
            <span>Word View</span>
          </div>
          <table class="diff-table">
            <tbody>
              {''.join(word_rows)}
            </tbody>
          </table>
        </div>
      </div>
      <div class="diff-modal-view" data-modal-id="{html.escape(modal_id)}" data-view="source">
        {source_versions_html}
      </div>
    </div>
  </div>
</div>
"""


def render_source_versions_html(rows: list[dict[str, str]]) -> str:
    previous_rows: list[str] = []
    new_rows: list[str] = []
    previous_gap_pending = False
    new_gap_pending = False

    def append_gap(target_rows: list[str]) -> None:
        target_rows.append(
            '<tr><td class="diff-line-no"></td><td class="diff-code diff-code-empty">&nbsp;</td></tr>'
        )

    for row in rows:
        kind = row.get("kind", "")
        if kind in {"hunk", "meta"}:
            if previous_rows:
                previous_gap_pending = True
            if new_rows:
                new_gap_pending = True
            continue

        left_text = row.get("left_text", "")
        left_no = row.get("left_no", "")
        right_text = row.get("right_text", "")
        right_no = row.get("right_no", "")

        if left_text:
            if previous_gap_pending:
                append_gap(previous_rows)
                previous_gap_pending = False
            previous_rows.append(
                f'<tr><td class="diff-line-no">{html.escape(left_no)}</td><td class="diff-code">{highlight_java_code(left_text)}</td></tr>'
            )
        if right_text:
            if new_gap_pending:
                append_gap(new_rows)
                new_gap_pending = False
            new_rows.append(
                f'<tr><td class="diff-line-no">{html.escape(right_no)}</td><td class="diff-code">{highlight_java_code(right_text)}</td></tr>'
            )

    if not previous_rows:
        previous_rows.append('<tr><td class="diff-line-no"></td><td class="diff-code diff-code-empty">No previous source captured</td></tr>')
    if not new_rows:
        new_rows.append('<tr><td class="diff-line-no"></td><td class="diff-code diff-code-empty">No new source captured</td></tr>')

    return f"""
<div class="source-versions">
  <div class="source-version-panel">
    <table class="diff-table unified">
      <tbody>
        {''.join(previous_rows)}
      </tbody>
    </table>
  </div>
  <div class="source-version-panel">
    <table class="diff-table unified">
      <tbody>
        {''.join(new_rows)}
      </tbody>
    </table>
  </div>
</div>
"""


def render_word_diff_cells(left_text: str, right_text: str) -> tuple[str, str]:
    left_tokens = tokenize_diff_text(left_text)
    right_tokens = tokenize_diff_text(right_text)
    matcher = difflib.SequenceMatcher(a=left_tokens, b=right_tokens)
    left_parts: list[str] = []
    right_parts: list[str] = []

    for tag, left_start, left_end, right_start, right_end in matcher.get_opcodes():
        left_chunk = "".join(left_tokens[left_start:left_end])
        right_chunk = "".join(right_tokens[right_start:right_end])
        if tag == "equal":
            rendered = highlight_java_code(left_chunk)
            left_parts.append(rendered)
            right_parts.append(rendered)
            continue
        if tag in {"replace", "delete"} and left_chunk:
            left_parts.append(f'<span class="diff-inline-del">{highlight_java_code(left_chunk)}</span>')
        if tag in {"replace", "insert"} and right_chunk:
            right_parts.append(f'<span class="diff-inline-add">{highlight_java_code(right_chunk)}</span>')

    return "".join(left_parts) or "&nbsp;", "".join(right_parts) or "&nbsp;"


def tokenize_diff_text(text: str) -> list[str]:
    if not text:
        return []
    return re.findall(r"\s+|\w+|[^\w\s]", text)


def parse_unified_diff(diff_text: str) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    left_line_no: int | None = None
    right_line_no: int | None = None
    pending_deletions: list[tuple[str, int]] = []
    pending_additions: list[tuple[str, int]] = []

    def flush_pending() -> None:
        nonlocal pending_deletions, pending_additions
        while pending_deletions or pending_additions:
            left_text, left_no = pending_deletions.pop(0) if pending_deletions else ("", "")
            right_text, right_no = pending_additions.pop(0) if pending_additions else ("", "")
            kind = "context"
            if left_text and right_text:
                kind = "context"
            elif left_text:
                kind = "del"
            elif right_text:
                kind = "add"
            rows.append(
                {
                    "kind": "change" if left_text and right_text else kind,
                    "left_no": str(left_no) if left_no != "" else "",
                    "left_text": left_text,
                    "left_kind": "del" if left_text else "context",
                    "right_no": str(right_no) if right_no != "" else "",
                    "right_text": right_text,
                    "right_kind": "add" if right_text else "context",
                }
            )

    for raw_line in diff_text.splitlines():
        if raw_line.startswith("@@"):
            flush_pending()
            left_line_no, right_line_no = parse_hunk_header(raw_line)
            rows.append({"kind": "hunk", "text": raw_line})
            continue
        if raw_line.startswith("---") or raw_line.startswith("+++"):
            flush_pending()
            rows.append({"kind": "meta", "text": raw_line})
            continue
        if raw_line.startswith("\\"):
            flush_pending()
            rows.append({"kind": "meta", "text": raw_line})
            continue
        if raw_line.startswith("-"):
            pending_deletions.append((raw_line[1:], left_line_no or 0))
            if left_line_no is not None:
                left_line_no += 1
            continue
        if raw_line.startswith("+"):
            pending_additions.append((raw_line[1:], right_line_no or 0))
            if right_line_no is not None:
                right_line_no += 1
            continue

        flush_pending()
        text = raw_line[1:] if raw_line.startswith(" ") else raw_line
        rows.append(
            {
                "kind": "context",
                "left_no": str(left_line_no) if left_line_no is not None else "",
                "left_text": text,
                "left_kind": "context",
                "right_no": str(right_line_no) if right_line_no is not None else "",
                "right_text": text,
                "right_kind": "context",
            }
        )
        if left_line_no is not None:
            left_line_no += 1
        if right_line_no is not None:
            right_line_no += 1

    flush_pending()
    return rows


def parse_hunk_header(header: str) -> tuple[int | None, int | None]:
    match = re.match(r"^@@ -(?P<left>\d+)(?:,\d+)? \+(?P<right>\d+)(?:,\d+)? @@", header)
    if not match:
        return None, None
    return int(match.group("left")), int(match.group("right"))


def _query_params(environ: dict[str, Any]) -> dict[str, str]:
    parsed = parse_qs(environ.get("QUERY_STRING", ""), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


def _request_base_url(environ: dict[str, Any]) -> str:
    scheme = environ.get("wsgi.url_scheme", "http")
    host = environ.get("HTTP_HOST") or f"{environ.get('SERVER_NAME', '127.0.0.1')}:{environ.get('SERVER_PORT', '8765')}"
    return f"{scheme}://{host}"


def _read_payload(environ: dict[str, Any]) -> dict[str, str]:
    content_length = int(environ.get("CONTENT_LENGTH", "0") or "0")
    body = environ["wsgi.input"].read(content_length)
    return load_post_data(body, environ.get("CONTENT_TYPE", "application/x-www-form-urlencoded"))


def _infer_tool_from_query(params: dict[str, str]) -> str:
    for key in ("from_file", "to_file"):
        value = params.get(key, "")
        if "/historyFinder/" in value:
            return "historyFinder"
        if "/codeShovel/" in value:
            return "codeShovel"
    return ""


def build_history_json_url(*, side: str, query_params: dict[str, str], download: bool) -> str:
    params = {"side": side}
    for key in ("tool", "sample_csv", "from_url", "to_url", "from_file", "to_file"):
        value = query_params.get(key, "")
        if value:
            params[key] = value
    if download:
        params["download"] = "1"
    return f"/api/history-json?{urlencode(params)}"


def build_related_revision_url(*, query_params: dict[str, str], from_url: str = "", to_url: str = "") -> str:
    params: dict[str, str] = {}
    for key in ("tool", "sample_csv", "from_url", "to_url", "from_file", "to_file", "related_source", "calling_source"):
        value = query_params.get(key, "")
        if value:
            params[key] = value
    if from_url:
        params["from_url"] = from_url
        params.pop("from_file", None)
    if to_url:
        params["to_url"] = to_url
        params.pop("to_file", None)
    return f"/revision?{urlencode(params)}"


def build_tool_switch_url(*, query_params: dict[str, str], tool: str) -> str:
    params: dict[str, str] = {"tool": tool}
    for key in ("sample_csv", "from_url", "to_url", "from_file", "to_file", "related_source", "calling_source"):
        value = query_params.get(key, "")
        if value:
            params[key] = value
    return f"/revision?{urlencode(params)}"


def render_related_source_form(*, query_params: dict[str, str], option_html: str, field_name: str) -> str:
    hidden_inputs = []
    for key in ("tool", "sample_csv", "from_url", "to_url", "from_file", "to_file", "related_source", "calling_source"):
        if key == field_name:
            continue
        value = query_params.get(key, "")
        if value:
            hidden_inputs.append(
                f'<input type="hidden" name="{html.escape(key)}" value="{html.escape(value)}" />'
            )
    return f"""
<form method="get" action="/revision" style="margin-top:10px;">
  {''.join(hidden_inputs)}
  <label>Source
    <select name="{html.escape(field_name)}" onchange="this.form.submit()">
      {option_html}
    </select>
  </label>
</form>
"""


def render_tool_switch_links(*, query_params: dict[str, str]) -> str:
    current_tool = query_params.get("tool", "")
    links = []
    for tool_name in ("historyFinder", "codeShovel"):
        url = build_tool_switch_url(query_params=query_params, tool=tool_name)
        label = tool_name if tool_name != current_tool else f"{tool_name} (current)"
        links.append(
            f'<a href="{html.escape(url)}" target="_blank" rel="noreferrer" class="chip">{html.escape(label)}</a>'
        )
    return f"""
<div style="margin-top:14px;">
  <div class="eyebrow">Open This Revision With Tool</div>
  <div class="chip-row" style="margin-top:8px;">
    {''.join(links)}
  </div>
</div>
"""


def safe_json_filename(history: MethodHistory) -> str:
    function_name = history.function_name or history.function_id or "method-history"
    normalized = "".join(character if character.isalnum() or character in {"-", "_"} else "-" for character in function_name)
    normalized = normalized.strip("-") or "method-history"
    project = history.project or "project"
    return f"{project}-{normalized}-{history.function_start_line}.json"


NOTE_SCRIPT = """
<script>
for (const button of document.querySelectorAll(".diff-modal-open")) {
  button.addEventListener("click", () => {
    const modal = document.getElementById(button.dataset.modalId);
    if (!modal) return;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
  });
}
for (const button of document.querySelectorAll(".diff-modal-close")) {
  button.addEventListener("click", () => {
    const modal = document.getElementById(button.dataset.modalId);
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  });
}
for (const modal of document.querySelectorAll(".diff-modal")) {
  modal.addEventListener("click", (event) => {
    if (event.target !== modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  });
}
for (const button of document.querySelectorAll(".diff-view-toggle")) {
  button.addEventListener("click", () => {
    const modalId = button.dataset.modalId;
    const view = button.dataset.view;
    for (const toggle of document.querySelectorAll(`.diff-view-toggle[data-modal-id="${modalId}"]`)) {
      toggle.classList.toggle("active", toggle === button);
    }
    for (const panel of document.querySelectorAll(`.diff-modal-view[data-modal-id="${modalId}"]`)) {
      panel.classList.toggle("open", panel.dataset.view === view);
    }
  });
}
for (const button of document.querySelectorAll(".copy-json-button")) {
  button.addEventListener("click", async () => {
    const status = button.parentElement.querySelector(".json-copy-status");
    try {
      const response = await fetch(button.dataset.jsonUrl);
      const text = await response.text();
      await navigator.clipboard.writeText(text);
      status.style.display = "inline-flex";
      status.textContent = "JSON copied";
      status.classList.remove("error");
    } catch (error) {
      status.style.display = "inline-flex";
      status.textContent = "Copy failed";
      status.classList.add("error");
    }
  });
}
for (const button of document.querySelectorAll(".diff-scroll-button")) {
  button.addEventListener("click", () => {
    const target = document.getElementById(button.dataset.scrollTarget);
    if (!target) return;
    const direction = button.dataset.scrollDirection === "left" ? -1 : 1;
    target.scrollBy({ left: direction * Math.max(180, Math.floor(target.clientWidth * 0.75)), behavior: "smooth" });
  });
}
const noteForm = document.getElementById("note-form");
if (noteForm) {
  noteForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = document.getElementById("note-status");
    const formData = new FormData(noteForm);
    const response = await fetch("/api/notes", { method: "POST", body: new URLSearchParams(formData) });
    const payload = await response.json();
    status.style.display = "inline-flex";
    status.textContent = payload.ok ? "Notes and tags saved to CSV" : "Save failed";
    status.classList.toggle("error", !payload.ok);
  });
}
</script>
"""


REVISION_LINK_SCRIPT = """
<script>
const revisionButton = document.getElementById("revision-link-button");
if (revisionButton) {
  revisionButton.addEventListener("click", async () => {
    const status = document.getElementById("revision-link-status");
    const payload = new URLSearchParams({
      sample_csv: revisionButton.dataset.sampleCsv,
      base_url: revisionButton.dataset.baseUrl,
    });
    const response = await fetch("/api/revision-links", { method: "POST", body: payload });
    const data = await response.json();
    status.style.display = "inline-flex";
    status.textContent = data.ok ? `revision_url written for ${data.rows} row(s)` : "Write failed";
    status.classList.toggle("error", !data.ok);
  });
}
</script>
"""
