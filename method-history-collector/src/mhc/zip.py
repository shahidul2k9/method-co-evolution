import gzip
import logging
import os
import shutil
import tarfile
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

def merge_folder_into_tar_gz(folder_path: str) -> None:
    taken_files = set()
    abs_folder_path = os.path.abspath(folder_path)
    tar_path = f"{abs_folder_path}.tar.gz"
    tmp_tar_path = f"{tar_path}.tmp"

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
        # 2. Add everything from folder
        if os.path.exists(folder_path):
            for root, _, files in os.walk(abs_folder_path):
                for f in files:
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, start=os.path.dirname(abs_folder_path))
                    if rel_path not in taken_files:
                        out_tar.add(abs_path, arcname=rel_path)
                        taken_files.add(str(rel_path))

    # 3. Atomic replace
    os.replace(tmp_tar_path, tar_path)
    if os.path.exists(abs_folder_path):
        shutil.rmtree(abs_folder_path)
