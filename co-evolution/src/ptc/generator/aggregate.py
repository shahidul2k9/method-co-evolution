from pathlib import Path

import pandas as pd

from mhc.util import aggregate_csv_files

__all__ = ["aggregate_csv_files", "aggregate_direct_csv_files"]


def aggregate_direct_csv_files(
    input_dir: str | Path,
    output_file_name: str,
    output_dir: str | Path | None = None,
) -> None:
    if output_dir is None:
        from mhc.config import EXPERIMENT_DIRECTORY

        output_dir = Path(EXPERIMENT_DIRECTORY) / "aggregate"

    dfs = [
        pd.read_csv(file, keep_default_na=False, na_filter=False, low_memory=False)
        for file in Path(input_dir).glob("*.csv")
    ]
    dfs = [df for df in dfs if not df.empty]

    if not dfs:
        return

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    pd.concat(dfs, ignore_index=True).to_csv(output_path / output_file_name, index=False)
