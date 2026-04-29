import fcntl
import gzip
import logging
import os
import tarfile
from contextlib import contextmanager
from pathlib import Path
from typing import Set


def load_zip_index(tar_path: str) -> Set[str]:
    """
    Load tar member names into a set.
    """
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            return set(tar.getnames())
    except (tarfile.TarError, gzip.BadGzipFile, OSError, EOFError) as exc:
        logging.warning("Skipping unreadable tar.gz archive %s: %s", tar_path, exc)
        return set()

def zip_folder(folder: str) -> None:
    tar_path = f"{folder}.tar.gz"

    print(f"[INFO] Zipping -> {tar_path}")

    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(folder, arcname=os.path.basename(folder))

@contextmanager
def file_lock(lock_path: str):
    Path(lock_path).parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def merge_folder_into_tar_gz(folder_path: str, include_suffixes: tuple[str, ...] = (".json",)) -> None:
    taken_files = set()
    abs_folder_path = os.path.abspath(folder_path)
    tar_path = f"{abs_folder_path}.tar.gz"
    tmp_tar_path = f"{tar_path}.tmp"
    lock_path = f"{tar_path}.lock"
    files_to_merge: list[tuple[str, str]] = []

    with file_lock(lock_path):
        if os.path.exists(folder_path):
            for root, _, files in os.walk(abs_folder_path):
                for filename in files:
                    if include_suffixes and not filename.endswith(include_suffixes):
                        continue
                    abs_path = os.path.join(root, filename)
                    rel_path = os.path.relpath(abs_path, start=os.path.dirname(abs_folder_path))
                    files_to_merge.append((abs_path, rel_path))

        # 1. Copy existing tar.gz content
        with tarfile.open(tmp_tar_path, "w:gz") as out_tar:
            if os.path.exists(tar_path):
                with tarfile.open(tar_path, "r:gz") as in_tar:
                    for member in in_tar.getmembers():
                        fileobj = in_tar.extractfile(member)
                        if member.name not in taken_files:
                            if fileobj is not None:
                                out_tar.addfile(member, fileobj)
                            else:
                                out_tar.addfile(member)
                            taken_files.add(member.name)
            # 2. Add current completed files from folder snapshot
            for abs_path, rel_path in files_to_merge:
                if rel_path not in taken_files and os.path.exists(abs_path):
                    out_tar.add(abs_path, arcname=rel_path)
                    taken_files.add(rel_path)

        # 3. Atomic replace
        os.replace(tmp_tar_path, tar_path)

        # 4. Delete only files merged from this snapshot; preserve directories and new files.
        for abs_path, _ in files_to_merge:
            if os.path.exists(abs_path):
                os.remove(abs_path)


def remove_file_if_exists(file_path: str) -> None:
    try:
        os.remove(file_path)
    except FileNotFoundError:
        pass


def remove_files_with_suffix(folder_path: str, suffix: str) -> None:
    if os.path.isdir(folder_path):
        for root, _, files in os.walk(folder_path):
            for filename in files:
                if filename.endswith(suffix):
                    remove_file_if_exists(os.path.join(root, filename))


def remove_empty_directory_tree(folder_path: str) -> None:
    if os.path.isdir(folder_path):
        for root, dirs, _ in os.walk(folder_path, topdown=False):
            for dirname in dirs:
                directory = os.path.join(root, dirname)
                try:
                    os.rmdir(directory)
                except OSError:
                    pass
        try:
            os.rmdir(folder_path)
        except OSError:
            pass
