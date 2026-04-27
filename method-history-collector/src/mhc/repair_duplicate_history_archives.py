import argparse
import os
import tarfile
from pathlib import Path
from mhc.config import CACHE_DIRECTORY

from mhc.zip import file_lock


def repair_folder_into_tar_gz(folder_path: str, include_suffixes: tuple[str, ...] = (".json",)) -> None:
    taken_files = set()
    abs_folder_path = os.path.abspath(folder_path)
    tar_path = f"{abs_folder_path}.tar.gz"
    tmp_tar_path = f"{tar_path}.tmp"
    lock_path = f"{tar_path}.lock"
    files_to_merge: list[tuple[str, str]] = []
    empty_files_to_remove: list[str] = []

    with file_lock(lock_path):
        if os.path.exists(folder_path):
            for root, _, files in os.walk(abs_folder_path):
                for filename in files:
                    if include_suffixes and not filename.endswith(include_suffixes):
                        continue
                    abs_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(abs_path, start=os.path.dirname(abs_folder_path))
                    if os.path.getsize(abs_path) == 0:
                        empty_files_to_remove.append(abs_path)
                        continue
                    files_to_merge.append((abs_path, rel_path))

        with tarfile.open(tmp_tar_path, "w:gz") as out_tar:
            if os.path.exists(tar_path):
                with tarfile.open(tar_path, "r:gz") as in_tar:
                    for member in in_tar.getmembers():
                        if member.size == 0:
                            continue
                        fileobj = in_tar.extractfile(member)
                        if member.name not in taken_files:
                            if fileobj is not None:
                                out_tar.addfile(member, fileobj)
                            else:
                                out_tar.addfile(member)
                            taken_files.add(member.name)

            for abs_path, rel_path in files_to_merge:
                if rel_path not in taken_files and os.path.exists(abs_path):
                    out_tar.add(abs_path, arcname=rel_path)
                    taken_files.add(rel_path)

        os.replace(tmp_tar_path, tar_path)

        for abs_path, _ in files_to_merge:
            if os.path.exists(abs_path):
                os.remove(abs_path)
        for abs_path in empty_files_to_remove:
            if os.path.exists(abs_path):
                os.remove(abs_path)


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
                    repair_folder_into_tar_gz(str(folder_path))
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
