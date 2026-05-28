from __future__ import annotations

import csv
from io import BytesIO
import json
from pathlib import Path
import shutil
import sys
import unittest
from urllib.parse import quote, urlencode

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PTC_SRC_DIRECTORY = REPOSITORY_ROOT / "co-evolution" / "src"
if str(PTC_SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(PTC_SRC_DIRECTORY))

from ptc.history_viewer.app import (
    build_change_count_summary,
    change_count_label,
    change_type_chip_class,
    create_app,
    format_commit_datetime,
    parse_unified_diff,
    render_change_count_summary_table,
    render_change_count_trend,
    render_change_chip,
    render_diff_html,
    truncate_display_text,
)
from ptc.history_viewer.repository import HistoryRepository, parse_commit_datetime, parse_method_url


WORKSPACE_DIRECTORY = REPOSITORY_ROOT / "workspace" / "experiment" / "main"
EXPERIMENT_DIRECTORY = WORKSPACE_DIRECTORY
SAMPLE_CSV = EXPERIMENT_DIRECTORY / "t2p-change-sample" / "historyFinder" / "omc--nc--ncc" / "cucumber-jvm.csv"
SAMPLE_DIR = EXPERIMENT_DIRECTORY / "t2p-change-sample" / "historyFinder" / "omc--nc--ncc"
HF_SAMPLE_URL = (
    "https://github.com/cucumber/cucumber-jvm/blob/4d9dd9304fe05e15c445c6f3b4d0e364d7c70223/"
    "cucumber-core/src/test/java/io/cucumber/core/plugin/UTF8PrintWriterTest.java#L17"
)


class TestHistoryViewer(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = HistoryRepository(workspace_directory=WORKSPACE_DIRECTORY, data_directory=EXPERIMENT_DIRECTORY)

    def write_ground_truth_fixture(self, directory_name: str = "ground-truth") -> Path:
        temp_dir = REPOSITORY_ROOT / "workspace" / "test" / "history-viewer" / directory_name
        temp_dir.mkdir(parents=True, exist_ok=True)
        csv_path = temp_dir / "sample-project.csv"
        fieldnames = [
            "project",
            "from_name",
            "to_name",
            "from_url",
            "to_url",
            "to_fqs",
            "from_artifact",
            "to_artifact",
            "to_call_depth",
            "label",
            "tags",
        ]
        rows = [
            {
                "project": "sample-project",
                "from_name": "testAlpha",
                "to_name": "makeAlpha",
                "from_url": "https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
                "to_url": "https://github.com/acme/sample/blob/abc/src/main/Alpha.java#L20",
                "to_fqs": "acme.Alpha.makeAlpha()",
                "from_artifact": "#test-code #test-case-method",
                "to_artifact": "#main-code",
                "to_call_depth": "",
                "label": "1",
                "tags": "#existing",
            },
            {
                "project": "sample-project",
                "from_name": "testAlpha",
                "to_name": "helperAlpha",
                "from_url": "https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
                "to_url": "https://github.com/acme/sample/blob/abc/src/main/Alpha.java#L30",
                "to_fqs": "acme.Alpha.helperAlpha(java.lang.String)",
                "from_artifact": "#test-code #test-case-method",
                "to_artifact": "#main-code",
                "to_call_depth": "2",
                "label": "",
                "tags": "",
            },
            {
                "project": "sample-project",
                "from_name": "testBeta",
                "to_name": "makeBeta",
                "from_url": "https://github.com/acme/sample/blob/abc/src/test/BetaTest.java#L11",
                "to_url": "https://github.com/acme/sample/blob/abc/src/main/Beta.java#L22",
                "to_fqs": "acme.Beta.makeBeta()",
                "from_artifact": "#test-code #test-case-method",
                "to_artifact": "#main-code",
                "to_call_depth": "1",
                "label": "0",
                "tags": "#beta",
            },
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def write_method_fixture(self, data_directory: Path, project: str = "sample-project") -> Path:
        method_dir = data_directory / "method"
        method_dir.mkdir(parents=True, exist_ok=True)
        csv_path = method_dir / f"{project}.csv"
        fieldnames = [
            "project",
            "name",
            "url",
            "file",
            "artifact",
            "fqs",
            "tctracer_fqs",
            "testlinker_fqs",
        ]
        rows = [
            {
                "project": project,
                "name": "newUtility",
                "url": "https://github.com/acme/sample/blob/abc/src/main/NewUtility.java#L40",
                "file": "src/main/NewUtility.java",
                "artifact": "#main-code",
                "fqs": "acme.NewUtility.newUtility()",
                "tctracer_fqs": "acme.NewUtility.newUtility()",
                "testlinker_fqs": "acme.NewUtility.newUtility()",
            },
            {
                "project": project,
                "name": "testFixtureHelper",
                "url": "https://github.com/acme/sample/blob/abc/src/test/TestFixture.java#L8",
                "file": "src/test/TestFixture.java",
                "artifact": "#test-code",
                "fqs": "acme.TestFixture.testFixtureHelper()",
                "tctracer_fqs": "acme.TestFixture.testFixtureHelper()",
                "testlinker_fqs": "acme.TestFixture.testFixtureHelper()",
            },
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return csv_path

    def write_sample_review_fixture(self, directory_name: str = "sample-review") -> Path:
        temp_dir = REPOSITORY_ROOT / "workspace" / "test" / "history-viewer" / directory_name
        temp_dir.mkdir(parents=True, exist_ok=True)
        csv_path = temp_dir / "sample-project.csv"
        fieldnames = ["project", "tool", "from_name", "to_name", "from_url", "to_url", "sampled", "label", "tags", "notes"]
        rows = [
            {
                "project": "sample-project",
                "tool": "historyFinder",
                "from_name": "testAlpha",
                "to_name": "makeAlpha",
                "from_url": "https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
                "to_url": "https://github.com/acme/sample/blob/abc/src/main/Alpha.java#L20",
                "sampled": "1",
                "label": "",
                "tags": "#old #keep",
                "notes": "",
            },
            {
                "project": "sample-project",
                "tool": "historyFinder",
                "from_name": "testBeta",
                "to_name": "makeBeta",
                "from_url": "https://github.com/acme/sample/blob/abc/src/test/BetaTest.java#L11",
                "to_url": "https://github.com/acme/sample/blob/abc/src/main/Beta.java#L22",
                "sampled": "0",
                "label": "1",
                "tags": "old,beta",
                "notes": "existing",
            },
        ]
        with csv_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        sibling_path = temp_dir / "sibling.csv"
        with sibling_path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerow(
                {
                    "project": "sample-project",
                    "tool": "historyFinder",
                    "from_name": "testGamma",
                    "to_name": "makeGamma",
                    "from_url": "https://github.com/acme/sample/blob/abc/src/test/GammaTest.java#L12",
                    "to_url": "https://github.com/acme/sample/blob/abc/src/main/Gamma.java#L24",
                    "sampled": "1",
                    "label": "1",
                    "tags": "#sibling #old",
                    "notes": "",
                }
            )
        return csv_path

    def call_app(
        self,
        app: object,
        *,
        path: str,
        query: str = "",
        method: str = "GET",
        body: bytes = b"",
    ) -> str:
        environ = {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "wsgi.input": BytesIO(body),
            "CONTENT_LENGTH": str(len(body)),
            "CONTENT_TYPE": "application/x-www-form-urlencoded",
            "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8765",
            "wsgi.url_scheme": "http",
        }
        status_holder: list[str] = []

        def start_response(status: str, _headers: list[tuple[str, str]]) -> None:
            status_holder.append(status)

        response_body = b"".join(app(environ, start_response)).decode("utf-8")
        self.assertEqual("200 OK", status_holder[0])
        return response_body

    def test_parse_method_url_extracts_project_path_and_line(self) -> None:
        parsed = parse_method_url(
            "https://github.com/cucumber/cucumber-jvm/blob/4d9dd9304fe05e15c445c6f3b4d0e364d7c70223/"
            "cucumber-core/src/test/java/io/cucumber/core/plugin/UTF8PrintWriterTest.java#L17"
        )

        self.assertEqual("cucumber-jvm", parsed.project)
        self.assertEqual("cucumber-core/src/test/java/io/cucumber/core/plugin/UTF8PrintWriterTest.java", parsed.file_path)
        self.assertEqual(17, parsed.line)

    def test_format_commit_datetime_uses_readable_24_hour_output(self) -> None:
        parsed = parse_commit_datetime("07/03/21 11:16 AM")

        self.assertEqual("2021 March 7, 11:16", format_commit_datetime(parsed, ""))

    def test_change_type_chips_use_per_type_classes(self) -> None:
        self.assertEqual("type-body", change_type_chip_class("Body"))
        self.assertEqual("type-introduction", change_type_chip_class("Introduction"))
        self.assertEqual("type-annotation", change_type_chip_class("Yannotationchnage"))

        chip_html = render_change_chip("Body")
        self.assertIn('class="chip type-body"', chip_html)
        self.assertIn(">Body<", chip_html)

    def test_truncate_display_text_keeps_prefix_and_ellipsis(self) -> None:
        value = "testRejectionWithFallbackRequestContextWithSemaphoreIsolatedAsynchronousObservable"

        self.assertEqual(
            "testRejectionWithFallbackRequestC...",
            truncate_display_text(value),
        )

    def test_build_change_count_summary_uses_shared_helper_categories(self) -> None:
        from_raw = {
            "changeHistoryDetails": {
                "a1": {"type": "Ybodychange", "diff": "x"},
                "a2": {"type": "Yintroduced", "diff": ""},
            }
        }
        to_raw = {
            "changeHistoryDetails": {
                "b1": {"type": "Ybodychange", "diff": "x"},
                "b2": {"type": "Ybodychange", "diff": "y"},
            }
        }

        summary = build_change_count_summary(from_raw, to_raw)
        summary_map = {label: (test_count, prod_count) for label, test_count, prod_count in summary}

        self.assertEqual("Return type", change_count_label("ch_return_type"))
        self.assertEqual((2, 2), summary_map["All commits"])
        self.assertEqual((1, 2), summary_map["Commits with diff"])
        self.assertEqual((1, 2), summary_map["Body"])
        self.assertEqual((1, 0), summary_map["Introduction"])
        self.assertIn("&uarr; 2", render_change_count_trend(3, 1))
        self.assertIn("&darr; 2", render_change_count_trend(1, 3))
        self.assertIn("trend-flat", render_change_count_trend(2, 2))

        html_output = render_change_count_summary_table(summary)
        self.assertIn("Change count summary", html_output)
        self.assertIn("<th>Test</th>", html_output)
        self.assertIn("<th>Production</th>", html_output)
        self.assertIn("<th>Trend</th>", html_output)

    def test_render_diff_html_uses_split_rows_with_colors(self) -> None:
        diff_text = "@@ -1,2 +1,2 @@\n-return 1;\n+return 2;\n // sharedLine\n"

        rows = parse_unified_diff(diff_text)
        html_output = render_diff_html(diff_text, modal_id="diff-modal-test", title="Example.java")

        self.assertTrue(any(row["kind"] == "change" for row in rows))
        self.assertIn("diff-cell-del", html_output)
        self.assertIn("diff-cell-add", html_output)
        self.assertIn("Open split view", html_output)
        self.assertIn('id="diff-modal-test"', html_output)
        self.assertIn("Split Diff View", html_output)
        self.assertIn("Word diff", html_output)
        self.assertIn("Word View", html_output)
        self.assertIn("Example.java", html_output)
        self.assertIn("github-split", html_output)
        self.assertIn("Source versions", html_output)
        self.assertIn("diff-inline-del", html_output)
        self.assertIn("diff-inline-add", html_output)
        self.assertIn('class="syntax-keyword"', html_output)
        self.assertIn('class="syntax-number"', html_output)
        self.assertIn('data-scroll-direction="left"', html_output)
        self.assertIn('data-scroll-direction="right"', html_output)
        self.assertNotIn("diff-unified-prefix", html_output)
        self.assertNotIn(">±<", html_output)

    def test_parse_commit_datetime_supports_year_month_day_24_hour_input(self) -> None:
        parsed = parse_commit_datetime("20/12/16 23:30 PM")

        self.assertIsNotNone(parsed)
        self.assertEqual("2016 December 20, 23:30", format_commit_datetime(parsed, ""))

    def test_parse_commit_datetime_prefers_day_month_year_when_first_number_cannot_be_month(self) -> None:
        parsed = parse_commit_datetime("25/02/14 22:56 PM")

        self.assertIsNotNone(parsed)
        self.assertEqual("2014 February 25, 22:56", format_commit_datetime(parsed, ""))

    def test_parse_commit_datetime_supports_midnight_with_am_marker(self) -> None:
        parsed = parse_commit_datetime("07/07/16 00:07 AM")

        self.assertIsNotNone(parsed)
        self.assertEqual("2016 July 7, 00:07", format_commit_datetime(parsed, ""))

    def test_parse_commit_datetime_prefers_day_month_year_for_ambiguous_numeric_dates(self) -> None:
        parsed = parse_commit_datetime("11/02/10 10:10 AM")

        self.assertIsNotNone(parsed)
        self.assertEqual("2010 February 11, 10:10", format_commit_datetime(parsed, ""))

    def test_load_historyfinder_from_direct_json_file(self) -> None:
        temp_file = REPOSITORY_ROOT / "workspace" / "test" / "history-viewer" / "historyfinder-direct.json"
        temp_file.parent.mkdir(parents=True, exist_ok=True)
        source_history = self.repository.load_history_from_url(HF_SAMPLE_URL, tool="historyFinder")
        temp_file.write_text(json.dumps(source_history.raw), encoding="utf-8")

        history = self.repository.load_history_from_file(temp_file)

        self.assertEqual("historyFinder", history.tool)
        self.assertEqual("println", history.function_name)
        self.assertEqual(17, history.function_start_line)
        self.assertTrue(history.entries)
        self.assertTrue(history.entries[0].diff_url.startswith("https://github.com/cucumber/cucumber-jvm/compare/"))

    def test_load_historyfinder_from_url_resolves_tar_member(self) -> None:
        history = self.repository.load_history_from_url(
            HF_SAMPLE_URL,
            tool="historyFinder",
        )

        self.assertEqual("println", history.function_name)
        self.assertEqual("cucumber-jvm", history.project)
        self.assertGreaterEqual(len(history.entries), 1)

    def test_load_codeshovel_from_url_resolves_tar_member(self) -> None:
        history = self.repository.load_history_from_url(
            "https://github.com/apache/ant/blob/3ffea30ee459d9fc4b9a005d418a192157e0e3ac/"
            "src/tutorial/tasks-start-writing/src/HelloWorldTest.java#L49",
            tool="codeShovel",
        )

        self.assertEqual("testMessage", history.function_name)
        self.assertEqual("ant", history.project)
        self.assertEqual("Ybodychange", history.entries[0].change_types[0])

    def test_write_revision_links_and_update_note(self) -> None:
        temp_csv = REPOSITORY_ROOT / "workspace" / "test" / "history-viewer" / "cucumber-jvm-copy.csv"
        temp_csv.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SAMPLE_CSV, temp_csv)

        row_count = self.repository.write_revision_links(temp_csv, base_url="http://127.0.0.1:8765")
        self.assertGreater(row_count, 0)

        with temp_csv.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            first_row = next(reader)
            self.assertIn("revision_url", reader.fieldnames)
            self.assertIn("sample_csv=", first_row["revision_url"])
            self.assertIn("from_url=", first_row["revision_url"])
            self.assertIn("%23L17", first_row["revision_url"])

        updated = self.repository.update_sample_note(
            temp_csv,
            from_url=first_row["from_url"],
            to_url=first_row["to_url"],
            notes="Strong same-commit coupling",
            tags="same-commit,strong-signal",
            label="1",
        )
        self.assertEqual("Strong same-commit coupling", updated.notes)
        self.assertEqual("#same-commit #strong-signal", updated.tags)
        self.assertEqual("1", updated.values["label"])

        with temp_csv.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual("Strong same-commit coupling", rows[0]["notes"])
        self.assertEqual("#same-commit #strong-signal", rows[0]["tags"])
        self.assertEqual("1", rows[0]["label"])

    def test_sample_review_label_tags_and_folder_tag_rename(self) -> None:
        csv_path = self.write_sample_review_fixture("sample-review-repository")
        row = self.repository.read_sample_rows(csv_path)[0]

        updated = self.repository.update_sample_note(
            csv_path,
            from_url=row.values["from_url"],
            to_url=row.values["to_url"],
            notes="accepted",
            tags="old,reviewed",
            label="0",
        )

        self.assertEqual("0", updated.values["label"])
        self.assertEqual("#old #reviewed", updated.values["tags"])
        with self.assertRaises(ValueError):
            self.repository.update_sample_note(
                csv_path,
                from_url=row.values["from_url"],
                to_url=row.values["to_url"],
                notes="accepted",
                tags="old",
                label="2",
            )

        self.assertEqual(["#beta", "#old", "#reviewed", "#sibling"], self.repository.collect_sample_tags(csv_path))
        result = self.repository.rename_sample_tag_in_folder(csv_path, old_tag="old", new_tag="renamed")

        self.assertEqual(2, result["files_updated"])
        self.assertEqual(3, result["rows_updated"])
        self.assertEqual("#old", result["old_tag"])
        self.assertEqual("#renamed", result["new_tag"])
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual("#renamed #reviewed", rows[0]["tags"])
        self.assertEqual("#renamed #beta", rows[1]["tags"])
        with (csv_path.parent / "sibling.csv").open("r", encoding="utf-8", newline="") as handle:
            sibling_rows = list(csv.DictReader(handle))
        self.assertEqual("#sibling #renamed", sibling_rows[0]["tags"])

    def test_sample_tag_rename_rejects_blank_or_multi_token_tags(self) -> None:
        csv_path = self.write_sample_review_fixture("sample-review-invalid-rename")

        with self.assertRaises(ValueError):
            self.repository.rename_sample_tag_in_folder(csv_path, old_tag="", new_tag="renamed")
        with self.assertRaises(ValueError):
            self.repository.rename_sample_tag_in_folder(csv_path, old_tag="old extra", new_tag="renamed")

    def test_ground_truth_summaries_group_by_test_method_and_completion(self) -> None:
        csv_path = self.write_ground_truth_fixture("ground-truth-summary")

        project_summary = self.repository.summarize_ground_truth_projects(csv_path.parent)[0]
        method_summaries = self.repository.summarize_ground_truth_test_methods(csv_path)

        self.assertEqual("sample-project", project_summary.project)
        self.assertEqual(3, project_summary.total_rows)
        self.assertEqual(2, project_summary.test_method_count)
        self.assertEqual(1, project_summary.completed_test_method_count)
        alpha_summary = next(method for method in method_summaries if method.from_name == "testAlpha")
        self.assertEqual(2, alpha_summary.candidate_count)
        self.assertEqual(1, alpha_summary.labelled_count)
        self.assertEqual(1, alpha_summary.truth_count)
        self.assertFalse(alpha_summary.is_complete)

    def test_update_ground_truth_label_targets_row_index_and_adds_note_column(self) -> None:
        csv_path = self.write_ground_truth_fixture("ground-truth-update")
        candidates = self.repository.read_ground_truth_candidates(
            csv_path,
            from_url="https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
        )

        updated = self.repository.update_ground_truth_label(
            csv_path,
            row_index=candidates[1].row_index,
            from_url=candidates[1].values["from_url"],
            to_url=candidates[1].values["to_url"],
            label="0",
            note="not production ground truth",
        )

        self.assertEqual("0", updated.values["label"])
        self.assertEqual("not production ground truth", updated.values["notes"])
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual("1", rows[0]["label"])
        self.assertEqual("0", rows[1]["label"])
        self.assertIn("notes", rows[1])
        self.assertEqual("not production ground truth", rows[1]["notes"])

    def test_ground_truth_routes_render_project_method_and_detail_pages(self) -> None:
        csv_path = self.write_ground_truth_fixture("ground-truth-routes")
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))

        project_body = self.call_app(
            app,
            path="/ground-truth",
            query=urlencode({"ground_truth_dir": str(csv_path.parent)}),
        )
        self.assertIn("Projects ready for labelling", project_body)
        self.assertIn("sample-project.csv", project_body)
        self.assertIn("Links", project_body)
        self.assertNotIn("Test Methods</th>", project_body)
        self.assertIn("1/2", project_body)

        method_body = self.call_app(
            app,
            path="/ground-truth",
            query=urlencode({"ground_truth_csv": str(csv_path)}),
        )
        self.assertIn("Test Methods", method_body)
        self.assertIn("testAlpha", method_body)
        self.assertIn("Method", method_body)
        self.assertIn("<th>URL</th>", method_body)
        self.assertNotIn(">Candidates</th>", method_body)
        self.assertIn(">Truth</th>", method_body)
        self.assertIn("1/2", method_body)
        self.assertIn("<td class=\"number-cell\">1</td>", method_body)
        self.assertIn(">Open</a>", method_body)
        self.assertIn("ground-truth-delete-method", method_body)
        self.assertIn("Back to projects", method_body)
        self.assertIn("<th style=\"text-transform:none; letter-spacing:0;\">Tags</th>", method_body)
        self.assertIn("<th style=\"text-transform:none; letter-spacing:0;\">Notes</th>", method_body)
        self.assertIn("#existing", method_body)

        detail_body = self.call_app(
            app,
            path="/ground-truth/detail",
            query=urlencode(
                {
                    "ground_truth_csv": str(csv_path),
                    "from_url": "https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
                }
            ),
        )
        self.assertIn("Called Production Methods", detail_body)
        self.assertIn("<th>Artifact</th>", detail_body)
        self.assertIn("production", detail_body)
        self.assertIn("Update All", detail_body)
        self.assertIn("Add Entry", detail_body)
        self.assertIn("All 0", detail_body)
        self.assertIn("All 1", detail_body)
        self.assertIn("Reset", detail_body)
        self.assertLess(detail_body.index("ground-truth-add-entry-toggle"), detail_body.index("ground-truth-bulk-label"))
        self.assertIn("<th>Tags</th>", detail_body)
        self.assertIn("<th>Notes</th>", detail_body)
        self.assertIn("<th>Delete</th>", detail_body)
        self.assertIn("ground-truth-delete-candidate", detail_body)
        self.assertIn("#existing", detail_body)
        self.assertIn("<summary>Details</summary>", detail_body)
        self.assertIn("<td class=\"number-cell\">1</td>", detail_body)
        self.assertIn('value="0"', detail_body)
        self.assertLess(detail_body.index('value="0"'), detail_body.index('value="1"'))

    def test_ground_truth_delete_apis_remove_method_and_candidate_rows(self) -> None:
        csv_path = self.write_ground_truth_fixture("ground-truth-delete-api")
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))

        candidate_payload = urlencode(
            {
                "ground_truth_csv": str(csv_path),
                "from_url": "https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
                "to_url": "https://github.com/acme/sample/blob/abc/src/main/Alpha.java#L30",
            }
        ).encode("utf-8")
        candidate_body = self.call_app(
            app,
            path="/api/ground-truth-delete-candidate",
            method="POST",
            body=candidate_payload,
        )
        candidate_response = json.loads(candidate_body)
        self.assertTrue(candidate_response["ok"])
        self.assertEqual(1, candidate_response["deleted_count"])

        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(2, len(rows))
        self.assertNotIn("https://github.com/acme/sample/blob/abc/src/main/Alpha.java#L30", [row["to_url"] for row in rows])

        method_payload = urlencode(
            {
                "ground_truth_csv": str(csv_path),
                "from_url": "https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
            }
        ).encode("utf-8")
        method_body = self.call_app(
            app,
            path="/api/ground-truth-delete-method",
            method="POST",
            body=method_payload,
        )
        method_response = json.loads(method_body)
        self.assertTrue(method_response["ok"])
        self.assertEqual(1, method_response["deleted_count"])

        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(["testBeta"], [row["from_name"] for row in rows])

    def test_ground_truth_method_search_and_append_candidate_use_method_csv(self) -> None:
        csv_path = self.write_ground_truth_fixture("ground-truth-append-api")
        data_directory = csv_path.parent / "workspace-data"
        self.write_method_fixture(data_directory)
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(data_directory))

        search_body = self.call_app(
            app,
            path="/api/ground-truth-method-search",
            query=urlencode({"ground_truth_csv": str(csv_path), "q": "fixture", "mode": "name"}),
        )
        search_response = json.loads(search_body)
        self.assertTrue(search_response["ok"])
        self.assertEqual("#test-code", search_response["options"][0]["artifact"])

        file_search_body = self.call_app(
            app,
            path="/api/ground-truth-method-search",
            query=urlencode({"ground_truth_csv": str(csv_path), "q": "NewUtility.java", "mode": "file"}),
        )
        file_search_response = json.loads(file_search_body)
        self.assertTrue(file_search_response["ok"])
        self.assertEqual("newUtility", file_search_response["options"][0]["name"])

        append_payload = urlencode(
            {
                "ground_truth_csv": str(csv_path),
                "from_url": "https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
                "method_row_index": "1",
            }
        ).encode("utf-8")
        append_body = self.call_app(
            app,
            path="/api/ground-truth-add-candidate",
            method="POST",
            body=append_payload,
        )
        append_response = json.loads(append_body)
        self.assertTrue(append_response["ok"])

        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual("testFixtureHelper", rows[2]["to_name"])
        self.assertEqual("testBeta", rows[3]["from_name"])
        self.assertEqual("#test-code #test-case-method", rows[2]["from_artifact"])
        self.assertEqual("1", rows[2]["to_call_depth"])
        self.assertEqual("", rows[2]["label"])
        self.assertEqual("", rows[2]["tags"])
        self.assertEqual("", rows[2]["notes"])

    def test_ground_truth_detail_script_renders_linked_search_result_with_artifact_and_fqs(self) -> None:
        csv_path = self.write_ground_truth_fixture("ground-truth-search-result-render")
        detail_body = self.call_app(
            create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY)),
            path="/ground-truth/detail",
            query=urlencode(
                {
                    "ground_truth_csv": str(csv_path),
                    "from_url": "https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
                }
            ),
        )

        self.assertIn('const name = document.createElement("a");', detail_body)
        self.assertIn("name.href = option.url;", detail_body)
        self.assertIn('<option value="file">File</option>', detail_body)
        self.assertIn('meta.textContent = option.artifact || "";', detail_body)
        self.assertIn('fqs.textContent = option.fqs || "";', detail_body)
        self.assertNotIn('meta.textContent = `${option.artifact || "artifact"} ${option.fqs || option.url}`;', detail_body)

    def test_ground_truth_update_api_returns_progress(self) -> None:
        csv_path = self.write_ground_truth_fixture("ground-truth-api")
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))
        candidates = self.repository.read_ground_truth_candidates(
            csv_path,
            from_url="https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
        )
        payload = urlencode(
            {
                "ground_truth_csv": str(csv_path),
                "row_index": str(candidates[1].row_index),
                "from_url": candidates[1].values["from_url"],
                "to_url": candidates[1].values["to_url"],
                "label": "1",
                "notes": "accepted",
                "tags": "reviewed accepted",
            }
        ).encode("utf-8")

        body = self.call_app(app, path="/api/ground-truth-label", method="POST", body=payload)
        response = json.loads(body)

        self.assertTrue(response["ok"])
        self.assertEqual(2, response["labelled_count"])
        self.assertEqual(2, response["candidate_count"])
        self.assertTrue(response["complete"])

    def test_sample_review_apis_persist_label_and_rename_folder_tags(self) -> None:
        csv_path = self.write_sample_review_fixture("sample-review-api")
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))
        rows = self.repository.read_sample_rows(csv_path)
        note_payload = urlencode(
            {
                "sample_csv": str(csv_path),
                "from_url": rows[0].values["from_url"],
                "to_url": rows[0].values["to_url"],
                "label": "1",
                "tags": "old,api",
                "notes": "updated through api",
            }
        ).encode("utf-8")

        note_body = self.call_app(app, path="/api/notes", method="POST", body=note_payload)
        note_response = json.loads(note_body)

        self.assertTrue(note_response["ok"])
        self.assertEqual("1", note_response["label"])
        self.assertEqual("#old #api", note_response["tags"])

        rename_payload = urlencode(
            {
                "sample_csv": str(csv_path),
                "old_tag": "old",
                "new_tag": "api-renamed",
            }
        ).encode("utf-8")
        rename_body = self.call_app(app, path="/api/sample-tags/rename", method="POST", body=rename_payload)
        rename_response = json.loads(rename_body)

        self.assertTrue(rename_response["ok"])
        self.assertEqual(2, rename_response["files_updated"])
        self.assertEqual(3, rename_response["rows_updated"])
        with csv_path.open("r", encoding="utf-8", newline="") as handle:
            updated_rows = list(csv.DictReader(handle))
        self.assertEqual("#api-renamed #api", updated_rows[0]["tags"])
        self.assertEqual("1", updated_rows[0]["label"])

    def test_ground_truth_batch_update_api_returns_progress(self) -> None:
        csv_path = self.write_ground_truth_fixture("ground-truth-batch-api")
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))
        candidates = self.repository.read_ground_truth_candidates(
            csv_path,
            from_url="https://github.com/acme/sample/blob/abc/src/test/AlphaTest.java#L10",
        )
        payload = urlencode(
            {
                "ground_truth_csv": str(csv_path),
                "from_url": candidates[0].values["from_url"],
                "updates": json.dumps(
                    [
                        {
                            "row_index": str(candidate.row_index),
                            "from_url": candidate.values["from_url"],
                            "to_url": candidate.values["to_url"],
                            "label": "0",
                            "notes": f"batch note {index}",
                            "tags": f"batch-{index}",
                        }
                        for index, candidate in enumerate(candidates)
                    ]
                ),
            }
        ).encode("utf-8")

        body = self.call_app(app, path="/api/ground-truth-labels", method="POST", body=payload)
        response = json.loads(body)

        self.assertTrue(response["ok"])
        self.assertEqual(2, response["updated_count"])
        self.assertEqual(2, response["labelled_count"])
        self.assertEqual(2, response["candidate_count"])
        self.assertTrue(response["complete"])

    def test_find_related_production_methods_uses_t2p_change_before_fallbacks(self) -> None:
        with SAMPLE_CSV.open("r", encoding="utf-8", newline="") as handle:
            first_row = next(csv.DictReader(handle))

        related_methods, searched_labels = self.repository.find_related_production_methods(
            project=first_row["project"],
            from_url=first_row["from_url"],
            tool="historyFinder",
            sample_csv=str(SAMPLE_CSV),
        )

        self.assertTrue(related_methods)
        self.assertEqual("t2p-link/omc--nc--ncc", related_methods[0].source_label)
        self.assertEqual("t2p-link/omc--nc--ncc", searched_labels[0])

    def test_related_source_options_include_requested_directory_order(self) -> None:
        options = self.repository.related_source_options(tool="historyFinder", sample_csv=str(SAMPLE_CSV))

        self.assertEqual(
            [
                "t2p-link/ncc",
                "t2p-tech",
                "t2p-link/gpt-oss-120b",
                "t2p-link/gpt-oss-20b",
                "t2p-link/lc",
                "t2p-link/lcba",
                "t2p-link/max",
                "t2p-link/nc",
                "t2p-link/omc",
                "t2p-link/omc--nc",
                "t2p-link/omc--nc--ncc",
                "t2p-link/omc--nc--ncc--lcba",
                "t2p-link/omc--nc--ncc--max",
                "t2p-link/qwen-2d5b",
                "t2p-candidate-filtered",
                "callgraph",
            ],
            options,
        )

    def test_find_calling_test_methods_uses_t2p_change_before_fallbacks(self) -> None:
        with SAMPLE_CSV.open("r", encoding="utf-8", newline="") as handle:
            first_row = next(csv.DictReader(handle))

        calling_methods, searched_labels = self.repository.find_calling_test_methods(
            project=first_row["project"],
            to_url=first_row["to_url"],
            tool="historyFinder",
            sample_csv=str(SAMPLE_CSV),
        )

        self.assertTrue(calling_methods)
        self.assertEqual("t2p-link/omc--nc--ncc", calling_methods[0].source_label)
        self.assertEqual("t2p-link/omc--nc--ncc", searched_labels[0])
        self.assertEqual(first_row["from_url"], calling_methods[0].from_url)

    def test_revision_route_renders_comparison_page(self) -> None:
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/revision",
            "QUERY_STRING": (
                "tool=historyFinder&sample_csv="
                f"{SAMPLE_CSV}"
                "&from_url=https%3A%2F%2Fgithub.com%2Fcucumber%2Fcucumber-jvm%2Fblob%2F4d9dd9304fe05e15c445c6f3b4d0e364d7c70223%2F"
                "cucumber-core%2Fsrc%2Ftest%2Fjava%2Fio%2Fcucumber%2Fcore%2Fplugin%2FUTF8PrintWriterTest.java%23L17"
                "&to_url=https%3A%2F%2Fgithub.com%2Fcucumber%2Fcucumber-jvm%2Fblob%2F4d9dd9304fe05e15c445c6f3b4d0e364d7c70223%2F"
                "cucumber-core%2Fsrc%2Fmain%2Fjava%2Fio%2Fcucumber%2Fcore%2Fplugin%2FUTF8PrintWriter.java%23L29"
            ),
            "wsgi.input": BytesIO(b""),
            "CONTENT_LENGTH": "0",
            "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8765",
            "wsgi.url_scheme": "http",
        }

        status_holder: list[str] = []

        def start_response(status: str, _headers: list[tuple[str, str]]) -> None:
            status_holder.append(status)

        body = b"".join(app(environ, start_response)).decode("utf-8")

        self.assertEqual("200 OK", status_holder[0])
        self.assertIn("Revision Viewer", body)
        self.assertIn("Save label, notes, and tags back to the sampled CSV", body)
        self.assertIn('name="label" value="0"', body)
        self.assertIn('name="label" value="1"', body)
        self.assertIn('id="sample-tag-options"', body)
        self.assertIn('class="sample-tags-input"', body)
        self.assertIn('class="pinned-tags-field"', body)
        self.assertIn(".pinned-tags-field {\n  position: fixed;", body)
        self.assertIn('input.closest(".pinned-tags-field") || spaceBelow < menuHeight', body)
        self.assertIn("rect.top - Math.min(menuHeight, availableHeight) - gap", body)
        self.assertNotIn('class="timeline-tag-picker"', body)
        self.assertNotIn('class="timeline-tag-select"', body)
        self.assertNotIn("timeline-tag-add", body)
        self.assertNotIn("Add Existing Tag", body)
        self.assertIn("Rename Tag", body)
        self.assertIn('id="sample-tag-rename-form"', body)
        self.assertIn(f'href="/sample?sample_csv={quote(str(SAMPLE_CSV), safe="")}"', body)
        self.assertIn("UTF8PrintWriterTest.java:17", body)
        self.assertIn("Tested Production Methods", body)
        self.assertIn("Calling Test Methods", body)
        self.assertIn("t2p-link/omc--nc--ncc", body)
        self.assertIn('name="related_source"', body)
        self.assertIn('name="calling_source"', body)
        self.assertIn("Change count summary", body)
        self.assertIn("<th>Change Type</th>", body)
        self.assertIn("<th>Production</th>", body)
        self.assertIn("<th>Trend</th>", body)
        self.assertIn("Open This Revision With Tool", body)
        self.assertIn("codeShovel", body)
        self.assertIn("historyFinder (current)", body)
        self.assertIn(".eyebrow {\n  color: var(--accent);\n  letter-spacing: 0;\n  text-transform: none;", body)
        self.assertIn("th {\n  color: var(--muted);\n  font-size: 0.82rem;\n  text-transform: none;", body)
        self.assertNotIn("<th>Method</th>", body)
        self.assertNotIn("<th>Link</th>", body)
        self.assertNotIn("<th>File</th>", body)
        self.assertNotIn("Actual Source", body)

    def test_revision_route_uses_first_source_option_as_real_default(self) -> None:
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/revision",
            "QUERY_STRING": (
                "tool=historyFinder&sample_csv="
                f"{SAMPLE_CSV}"
                "&from_url=https%3A%2F%2Fgithub.com%2Fcucumber%2Fcucumber-jvm%2Fblob%2F4d9dd9304fe05e15c445c6f3b4d0e364d7c70223%2F"
                "cucumber-core%2Fsrc%2Ftest%2Fjava%2Fio%2Fcucumber%2Fcore%2Fplugin%2FUTF8PrintWriterTest.java%23L17"
                "&to_url=https%3A%2F%2Fgithub.com%2Fcucumber%2Fcucumber-jvm%2Fblob%2F4d9dd9304fe05e15c445c6f3b4d0e364d7c70223%2F"
                "cucumber-core%2Fsrc%2Fmain%2Fjava%2Fio%2Fcucumber%2Fcore%2Fplugin%2FUTF8PrintWriter.java%23L29"
            ),
            "wsgi.input": BytesIO(b""),
            "CONTENT_LENGTH": "0",
            "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8765",
            "wsgi.url_scheme": "http",
        }

        status_holder: list[str] = []

        def start_response(status: str, _headers: list[tuple[str, str]]) -> None:
            status_holder.append(status)

        body = b"".join(app(environ, start_response)).decode("utf-8")

        self.assertEqual("200 OK", status_holder[0])
        self.assertIn('<option value="t2p-link/ncc" selected>', body)
        self.assertIn("Loaded from <span class=\"mono\">t2p-link/ncc</span>", body)

    def test_sample_directory_route_lists_csv_files(self) -> None:
        csv_path = self.write_sample_review_fixture("sample-directory-route")
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))

        body = self.call_app(app, path="/sample", query=urlencode({"sample_dir": str(csv_path.parent)}))

        self.assertIn("Projects with T2P Links", body)
        self.assertIn("sample-project", body)
        self.assertIn("Projects", body)
        self.assertIn("<h1>Projects with T2P Links</h1>", body)
        self.assertIn("Total Projects", body)
        self.assertIn("<strong>2</strong>", body)
        self.assertIn("<strong>2 (66.7%)/3</strong>", body)
        self.assertIn("<strong>1 (50.0%)/2</strong>", body)
        self.assertIn('onchange="this.form.submit()"', body)
        self.assertNotIn("Apply Filter", body)
        self.assertIn("<th>Project</th>", body)
        self.assertIn("<th class=\"number-cell\">Sample</th>", body)
        self.assertIn("<th class=\"number-cell\">Progress</th>", body)
        self.assertIn("1 (50.0%)/2", body)
        self.assertIn("0 (0.0%)/1", body)
        self.assertNotIn("<th>Path</th>", body)

        all_body = self.call_app(
            app,
            path="/sample",
            query=urlencode({"sample_dir": str(csv_path.parent), "count_scope": "all"}),
        )
        self.assertIn("<strong>2 (66.7%)/3</strong>", all_body)
        self.assertIn("<strong>2 (66.7%)/3</strong>", all_body)
        self.assertIn("1 (50.0%)/2", all_body)
        self.assertIn("1 (100.0%)/1", all_body)

    def test_sample_browser_defaults_to_sampled_links_and_renders_t2p_columns(self) -> None:
        csv_path = self.write_sample_review_fixture("sample-browser-route")
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))

        body = self.call_app(app, path="/sample", query=urlencode({"sample_csv": str(csv_path)}))

        self.assertIn("T2P Links", body)
        self.assertIn("<h1>sample-project</h1>", body)
        self.assertIn("Total Links", body)
        self.assertIn("<strong>2</strong>", body)
        self.assertIn("<strong>1 (50.0%)/2</strong>", body)
        self.assertIn("<strong>0 (0.0%)/1</strong>", body)
        self.assertIn('onchange="this.form.submit()"', body)
        self.assertIn("Showing 1-1 of 1 sampled links (2 total links in this CSV).", body)
        self.assertIn("testAlpha", body)
        self.assertNotIn("testBeta", body)
        self.assertIn("<th class=\"number-cell\">Sample</th>", body)
        self.assertIn("<td class=\"number-cell\">1</td>", body)
        self.assertIn(">Open</a>", body)
        self.assertNotIn("<th>Tool</th>", body)
        self.assertNotIn("Write revision_url column", body)
        self.assertNotIn("Open revision", body)
        self.assertNotIn("Apply Filter", body)

        all_body = self.call_app(
            app,
            path="/sample",
            query=urlencode({"sample_csv": str(csv_path), "sample_filter": "all"}),
        )
        self.assertIn("Showing 1-2 of 2 all links (2 total links in this CSV).", all_body)
        self.assertIn("testBeta", all_body)
        self.assertIn("<strong>1 (50.0%)/2</strong>", all_body)

    def test_history_json_api_returns_raw_history(self) -> None:
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/history-json",
            "QUERY_STRING": (
                "tool=historyFinder"
                "&from_url=https%3A%2F%2Fgithub.com%2Fcucumber%2Fcucumber-jvm%2Fblob%2F4d9dd9304fe05e15c445c6f3b4d0e364d7c70223%2F"
                "cucumber-core%2Fsrc%2Ftest%2Fjava%2Fio%2Fcucumber%2Fcore%2Fplugin%2FUTF8PrintWriterTest.java%23L17"
                "&side=from"
            ),
            "wsgi.input": BytesIO(b""),
            "CONTENT_LENGTH": "0",
            "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8765",
            "wsgi.url_scheme": "http",
        }

        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = headers

        body = b"".join(app(environ, start_response)).decode("utf-8")

        self.assertEqual("200 OK", captured["status"])
        self.assertIn('"functionName": "println"', body)
        self.assertTrue(any(header == ("Content-Type", "application/json; charset=utf-8") for header in captured["headers"]))

    def test_history_json_api_can_force_download(self) -> None:
        app = create_app(workspace_directory=str(WORKSPACE_DIRECTORY), data_directory=str(EXPERIMENT_DIRECTORY))
        environ = {
            "REQUEST_METHOD": "GET",
            "PATH_INFO": "/api/history-json",
            "QUERY_STRING": (
                "tool=historyFinder"
                "&to_url=https%3A%2F%2Fgithub.com%2Fcucumber%2Fcucumber-jvm%2Fblob%2F4d9dd9304fe05e15c445c6f3b4d0e364d7c70223%2F"
                "cucumber-core%2Fsrc%2Fmain%2Fjava%2Fio%2Fcucumber%2Fcore%2Fplugin%2FUTF8PrintWriter.java%23L29"
                "&side=to&download=1"
            ),
            "wsgi.input": BytesIO(b""),
            "CONTENT_LENGTH": "0",
            "SERVER_NAME": "127.0.0.1",
            "SERVER_PORT": "8765",
            "wsgi.url_scheme": "http",
        }

        captured: dict[str, object] = {}

        def start_response(status: str, headers: list[tuple[str, str]]) -> None:
            captured["status"] = status
            captured["headers"] = headers

        _body = b"".join(app(environ, start_response)).decode("utf-8")

        self.assertEqual("200 OK", captured["status"])
        self.assertTrue(any(header[0] == "Content-Disposition" and header[1].endswith(".json\"") for header in captured["headers"]))


if __name__ == "__main__":
    unittest.main()
