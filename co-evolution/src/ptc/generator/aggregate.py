import csv
from pathlib import Path

import pandas as pd

from mhc.util import aggregate_csv_files

__all__ = ["aggregate_csv_files", "aggregate_direct_csv_files"]


def _detect_csv_separator(file: Path) -> str:
    sample = file.read_text(errors="ignore")[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;").delimiter
    except csv.Error:
        first_line = sample.splitlines()[0] if sample else ""
        return ";" if first_line.count(";") > first_line.count(",") else ","


def aggregate_direct_csv_files(
    input_dir: str | Path,
    output_file_name: str,
    output_dir: str | Path | None = None,
) -> None:
    if output_dir is None:
        from mhc.config import EXPERIMENT_DIRECTORY

        output_dir = Path(EXPERIMENT_DIRECTORY) / "aggregate"

    dfs = []
    for file in sorted(Path(input_dir).glob("*.csv")):
        try:
            df = pd.read_csv(
                file,
                sep=_detect_csv_separator(file),
                keep_default_na=False,
                na_filter=False,
                low_memory=False,
            )
        except Exception as exc:
            print(f"Warning: skipping unreadable CSV file {file}: {exc}")
            continue

        if not df.empty:
            dfs.append(df)

    if not dfs:
        return

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    pd.concat(dfs, ignore_index=True).to_csv(output_path / output_file_name, index=False)
