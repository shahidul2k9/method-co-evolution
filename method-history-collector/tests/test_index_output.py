import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.method_history_jar_runner import execute_method_history_if_missing, update_repository_index
from mhc.zip import merge_folder_into_tar_gz


def _write_tar_gz(tar_path: Path, members: dict[str, str] | list[tuple[str, str]]) -> None:
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    member_items = members.items() if isinstance(members, dict) else members
    with tarfile.open(tar_path, "w:gz") as archive:
        for member_name, content in member_items:
            data = content.encode("utf-8")
            tar_info = tarfile.TarInfo(name=member_name)
            tar_info.size = len(data)
            archive.addfile(tar_info, io.BytesIO(data))


class TestIndexOutput(unittest.TestCase):
    def test_zero_merge_threshold_disables_intermediate_merge_only(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_directory = temp_path / "data"
            method_dir = data_directory / "method"
            method_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "expression": "method",
                        "name": "foo",
                        "start_line": 10,
                        "file": "src/Foo.java",
                    }
                ]
            ).to_csv(method_dir / "checkstyle.csv", index=False)

            repository_df = pd.DataFrame(
                [
                    {
                        "project": "checkstyle",
                        "url": "https://example.com/checkstyle",
                        "updated_hash": "abc123",
                    }
                ]
            )

            with (
                patch("mhc.method_history_jar_runner.ms.clone_and_checkout_commit"),
                patch("mhc.method_history_jar_runner.execute_cmd_method_history_jar"),
                patch("mhc.method_history_jar_runner.merge_folder_into_tar_gz") as mock_merge,
            ):
                execute_method_history_if_missing(
                    repository_df,
                    str(temp_path / "repository"),
                    str(data_directory),
                    str(temp_path / "cache"),
                    ["codeShovel"],
                    {"codeShovel": "codeShovel.jar"},
                    merge_threshold=0,
                )

            mock_merge.assert_called_once()

    def test_negative_merge_threshold_disables_all_merging(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            data_directory = temp_path / "data"
            method_dir = data_directory / "method"
            method_dir.mkdir(parents=True)
            pd.DataFrame(
                [
                    {
                        "expression": "method",
                        "name": "foo",
                        "start_line": 10,
                        "file": "src/Foo.java",
                    }
                ]
            ).to_csv(method_dir / "checkstyle.csv", index=False)

            repository_df = pd.DataFrame(
                [
                    {
                        "project": "checkstyle",
                        "url": "https://example.com/checkstyle",
                        "updated_hash": "abc123",
                    }
                ]
            )

            with (
                patch("mhc.method_history_jar_runner.ms.clone_and_checkout_commit"),
                patch("mhc.method_history_jar_runner.execute_cmd_method_history_jar"),
                patch("mhc.method_history_jar_runner.merge_folder_into_tar_gz") as mock_merge,
            ):
                execute_method_history_if_missing(
                    repository_df,
                    str(temp_path / "repository"),
                    str(data_directory),
                    str(temp_path / "cache"),
                    ["codeShovel"],
                    {"codeShovel": "codeShovel.jar"},
                    merge_threshold=-2,
                )

            mock_merge.assert_not_called()

    def test_update_repository_index_writes_into_data_aggregate_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            cache_directory = temp_path / "cache"
            data_directory = temp_path / "data"

            method_dir = data_directory / "method"
            method_dir.mkdir(parents=True)
            pd.DataFrame(
                [{"name": "a"}, {"name": "b"}, {"name": "c"}]
            ).to_csv(method_dir / "checkstyle.csv", index=False)

            _write_tar_gz(
                cache_directory / "history" / "codeShovel" / "checkstyle.tar.gz",
                {
                    "checkstyle/src/Foo--m1--1.json": "{}",
                    "checkstyle/src/Foo--m2--2.json": "{}",
                },
            )
            _write_tar_gz(
                data_directory / "fan-in" / "checkstyle.tar.gz",
                {
                    "checkstyle/A.csv": "value\n1\n",
                },
            )
            _write_tar_gz(
                data_directory / "fan-out" / "checkstyle.tar.gz",
                {
                    "checkstyle/A.csv": "value\n1\n",
                    "checkstyle/B.csv": "value\n2\n",
                },
            )

            repository_df = pd.DataFrame(
                [{"project": "checkstyle", "url": "https://example.com/checkstyle"}]
            )

            update_repository_index(repository_df, str(cache_directory), str(data_directory))

            output_file = data_directory / "aggregate" / "repository-history-index.csv"
            self.assertTrue(output_file.exists())

            output_df = pd.read_csv(output_file)
            self.assertEqual(["checkstyle"], output_df["project"].tolist())
            self.assertEqual([3], output_df["methods"].tolist())
            self.assertEqual([2], output_df["history_codeShovel"].tolist())
            self.assertEqual([1], output_df["fan-in"].tolist())
            self.assertEqual([2], output_df["fan-out"].tolist())

    def test_merge_folder_into_tar_gz_only_removes_merged_json_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "history" / "codeShovel" / "checkstyle"
            folder.mkdir(parents=True)
            merged_file = folder / "src" / "Foo--a--1.json"
            merged_file.parent.mkdir(parents=True)
            merged_file.write_text("{}", encoding="utf-8")
            temp_file = folder / "src" / "Foo--a--1.tmp"
            temp_file.write_text("partial", encoding="utf-8")

            merge_folder_into_tar_gz(str(folder))

            tar_path = Path(f"{folder}.tar.gz")
            self.assertTrue(tar_path.exists())
            self.assertFalse(merged_file.exists())
            self.assertTrue(temp_file.exists())
            self.assertTrue(folder.exists())

            with tarfile.open(tar_path, "r:gz") as archive:
                self.assertIn(
                    "checkstyle/src/Foo--a--1.json",
                    archive.getnames(),
                )

    def test_merge_folder_into_tar_gz_deduplicates_existing_archive_members(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "history" / "codeShovel" / "checkstyle"
            tar_path = Path(f"{folder}.tar.gz")
            _write_tar_gz(
                tar_path,
                [
                    ("checkstyle/src/Foo--a--1.json", '{"value": 1}'),
                    ("checkstyle/src/Foo--a--1.json", '{"value": 2}'),
                    ("checkstyle/src/Foo--b--2.json", '{"value": 3}'),
                ],
            )

            merge_folder_into_tar_gz(str(folder))

            with tarfile.open(tar_path, "r:gz") as archive:
                member_names = archive.getnames()

            self.assertEqual(1, member_names.count("checkstyle/src/Foo--a--1.json"))
            self.assertEqual(1, member_names.count("checkstyle/src/Foo--b--2.json"))


if __name__ == "__main__":
    unittest.main()
