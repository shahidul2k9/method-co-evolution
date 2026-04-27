import argparse
import os
from pathlib import Path

from mhc.config import CACHE_DIRECTORY
from mhc.zip import merge_folder_into_tar_gz


def repair_archives(history_directories: list[Path]) -> int:
    repaired_count = 0
    failed_count = 0

    for history_directory in history_directories:
        if not history_directory.exists():
            print(f"[WARN] Missing directory: {history_directory}")
            continue

        for root, _, files in os.walk(history_directory):
            for filename in files:
                if not filename.endswith(".tar.gz"):
                    continue

                archive_path = Path(root) / filename
                folder_path = archive_path.with_name(filename[: -len(".tar.gz")])
                print(folder_path)
                try:
                    merge_folder_into_tar_gz(str(folder_path))
                    repaired_count += 1
                except Exception as exc:
                    failed_count += 1
                    print(f"[ERROR] {folder_path}: {exc}")

    print(f"[INFO] Repaired archives: {repaired_count}")
    print(f"[INFO] Failed archives: {failed_count}")
    return 1 if failed_count else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="One-time repair for duplicate method-history tar.gz members."
    )
    parser.add_argument(
        "history_directories",
        nargs="*",
        type=Path,
        default=[
            Path(CACHE_DIRECTORY) / "history" / "historyFinder",
            Path(CACHE_DIRECTORY) / "history" / "codeShovel",
        ],
        help="History tool directories to repair.",
    )
    args = parser.parse_args()

    return repair_archives([path.resolve() for path in args.history_directories])


if __name__ == "__main__":
    raise SystemExit(main())
