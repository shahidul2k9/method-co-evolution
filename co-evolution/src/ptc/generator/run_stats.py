from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import warnings


@dataclass
class GenerationStats:
    module_name: str
    recreated: int = 0
    skipped_existing: int = 0
    skipped_missing_input: int = 0
    deleted_stale: int = 0
    missing_stale: int = 0
    empty_output: int = 0
    rows_written: int = 0

    def record_write(self, rows: int | None = None) -> None:
        self.recreated += 1
        if rows is not None:
            self.rows_written += rows

    def record_empty_output(self) -> None:
        self.empty_output += 1

    def print_summary(self) -> None:
        print(
            f"{self.module_name} summary: "
            f"recreated={self.recreated}, "
            f"skipped_existing={self.skipped_existing}, "
            f"skipped_missing_input={self.skipped_missing_input}, "
            f"deleted_stale={self.deleted_stale}, "
            f"missing_stale={self.missing_stale}, "
            f"empty_output={self.empty_output}, "
            f"rows_written={self.rows_written}"
        )


def should_generate(output_file: Path, *, replace: bool, label: str, stats: GenerationStats) -> bool:
    if output_file.exists() and not replace:
        print(f"Skipping existing: {label}")
        stats.skipped_existing += 1
        return False
    return True


def unlink_stale_output(output_file: Path, *, reason: str, stats: GenerationStats) -> None:
    stats.skipped_missing_input += 1
    if output_file.exists():
        output_file.unlink()
        stats.deleted_stale += 1
        warnings.warn(f"{reason}; deleted stale output: {output_file}")
    else:
        stats.missing_stale += 1
        warnings.warn(f"{reason}; no stale output found: {output_file}")


def record_written_csv(output_file: Path, stats: GenerationStats, rows: int | None = None) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    stats.record_write(rows)
