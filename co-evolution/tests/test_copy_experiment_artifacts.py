import sys
import tempfile
import unittest
from importlib import import_module
from pathlib import Path

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from ptc.migration.copy_experiment_artifacts import (
    collect_copy_operations,
    execute_copy_operations,
    load_destination_projects,
    run_migration,
)


class CopyExperimentArtifactsTest(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp_directory.name)
        self.source = self.workspace / "experiment" / "source"
        self.destination = self.workspace / "experiment" / "destination"
        self.source.mkdir(parents=True)
        self.destination.mkdir(parents=True)
        pd.DataFrame({"project": ["alpha", "beta", "alpha"]}).to_csv(
            self.destination / "project.csv", index=False
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def _write(self, path: Path, content: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)

    def test_load_destination_projects_requires_project_column_and_deduplicates(self):
        self.assertEqual(["alpha", "beta"], load_destination_projects(self.destination))

        pd.DataFrame({"name": ["alpha"]}).to_csv(self.destination / "project.csv", index=False)
        with self.assertRaisesRegex(ValueError, "missing 'project' column"):
            load_destination_projects(self.destination)

        (self.destination / "project.csv").write_text("")
        with self.assertRaisesRegex(ValueError, "project index is invalid"):
            load_destination_projects(self.destination)

    def test_collect_and_execute_copies_selected_artifacts_and_nested_history(self):
        for artifact in ("class", "method", "callgraph", "fanin"):
            self._write(self.source / artifact / "alpha.csv", f"{artifact}-alpha")
            self._write(self.source / artifact / "other.csv", f"{artifact}-other")
        self._write(self.source / "method-history-gz" / "historyFinder" / "alpha.tar.gz", "history")
        self._write(self.source / "method-history-gz" / "historyFinder" / "other.tar.gz", "other")
        self._write(self.source / "method-history-gz" / "historyFinder" / "alpha.tar.gz.lock", "lock")
        self._write(self.source / "method-history-gz" / ".cache" / "alpha.tar.gz", "hidden")

        operations = collect_copy_operations(self.source, self.destination, ["alpha"])
        results = execute_copy_operations(operations)

        self.assertEqual(5, sum(result.status == "copied" for result in results))
        self.assertEqual(
            "history",
            (self.destination / "method-history-gz" / "historyFinder" / "alpha.tar.gz").read_text(),
        )
        self.assertFalse((self.destination / "class" / "other.csv").exists())
        self.assertFalse((self.destination / "method-history-gz" / "historyFinder" / "alpha.tar.gz.lock").exists())
        self.assertFalse((self.destination / "method-history-gz" / ".cache" / "alpha.tar.gz").exists())

    def test_collect_reports_missing_archive_for_each_visible_history_tool(self):
        self._write(self.source / "method-history-gz" / "historyFinder" / "other.tar.gz", "other")

        operations = collect_copy_operations(self.source, self.destination, ["alpha"])
        results = execute_copy_operations(operations)

        history_results = [result for result in results if result.operation.artifact == "method-history-gz"]
        self.assertEqual(1, len(history_results))
        self.assertEqual("missing", history_results[0].status)
        self.assertEqual("alpha.tar.gz", history_results[0].operation.source.name)

    def test_execute_reports_missing_skips_existing_and_replaces(self):
        self._write(self.source / "class" / "alpha.csv", "source")
        self._write(self.destination / "class" / "alpha.csv", "destination")
        operations = collect_copy_operations(self.source, self.destination, ["alpha"])

        results = execute_copy_operations(operations)
        self.assertEqual(1, sum(result.status == "skipped" for result in results))
        self.assertEqual(3, sum(result.status == "missing" for result in results))
        self.assertEqual("destination", (self.destination / "class" / "alpha.csv").read_text())

        results = execute_copy_operations(operations, replace=True)
        self.assertEqual(1, sum(result.status == "copied" for result in results))
        self.assertEqual("source", (self.destination / "class" / "alpha.csv").read_text())

    def test_dry_run_does_not_create_files(self):
        self._write(self.source / "class" / "alpha.csv", "source")
        operations = collect_copy_operations(self.source, self.destination, ["alpha"])

        results = execute_copy_operations(operations, dry_run=True)

        self.assertEqual(1, sum(result.status == "planned" for result in results))
        self.assertFalse((self.destination / "class" / "alpha.csv").exists())

    def test_run_migration_rejects_invalid_experiments(self):
        with self.assertRaisesRegex(ValueError, "must differ"):
            run_migration(self.workspace, "source", "source")
        with self.assertRaisesRegex(FileNotFoundError, "source experiment"):
            run_migration(self.workspace, "missing", "destination")
        with self.assertRaisesRegex(FileNotFoundError, "destination experiment"):
            run_migration(self.workspace, "source", "missing")

    def test_migrate_compatibility_module_exposes_main(self):
        compatibility_module = import_module("ptc.migrate.copy_experiment_artifacts")

        self.assertTrue(callable(compatibility_module.main))


if __name__ == "__main__":
    unittest.main()
