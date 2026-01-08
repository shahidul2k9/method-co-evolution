import os
import tarfile
import shutil
from typing import Set

def load_zip_index(tar_path: str) -> Set[str]:
    """
    Load tar member names into a set.
    """
    try:
        with tarfile.open(tar_path, "r:gz") as tar:
            return set(tar.getnames())
    except tarfile.TarError as e:
        raise e

def zip_folder(folder: str) -> None:
    tar_path = f"{folder}.tar.gz"

    print(f"[INFO] Zipping -> {tar_path}")

    with tarfile.open(tar_path, "w:gz") as tar:
        tar.add(folder, arcname=os.path.basename(folder))

def merge_folder_into_tar_gz(folder_path: str) -> None:
    if os.path.exists(folder_path):
        folder_path = os.path.abspath(folder_path)
        tar_path = f"{folder_path}.tar.gz"
        tmp_tar_path = f"{tar_path}.tmp"

        with tarfile.open(tmp_tar_path, "w:gz") as out_tar:

            # 1. Copy existing tar.gz content
            if os.path.exists(tar_path):
                with tarfile.open(tar_path, "r:gz") as in_tar:
                    for member in in_tar.getmembers():
                        fileobj = in_tar.extractfile(member)
                        if fileobj is not None:
                            out_tar.addfile(member, fileobj)
                        else:
                            out_tar.addfile(member)

            # 2. Add everything from folder
            for root, _, files in os.walk(folder_path):
                for f in files:
                    abs_path = os.path.join(root, f)
                    rel_path = os.path.relpath(abs_path, start=folder_path)
                    out_tar.add(abs_path, arcname=rel_path)

        # 3. Atomic replace
        os.replace(tmp_tar_path, tar_path)

        # 4. Remove the entire folder
        shutil.rmtree(folder_path)
