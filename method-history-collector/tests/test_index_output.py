import io
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SRC_DIRECTORY = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from mhc.method_history_jar_runner import update_repository_index


def _write_tar_gz(tar_path: Path, members: dict[str, str]) -> None:
    tar_path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "w:gz") as archive:
        for member_name, content in members.items():
            data = content.encode("utf-8")
            tar_info = tarfile.TarInfo(name=member_name)
            tar_info.size = len(data)
            archive.addfile(tar_info, io.BytesIO(data))


class TestIndexOutput(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
