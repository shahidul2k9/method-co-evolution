import os
import tarfile
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
