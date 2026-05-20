import json
import logging
import os
import tarfile
import warnings
from pathlib import Path
import pandas as pd
import mhc.util as util
from ptc.constants import MethodChangeType
from ptc.util.helper import extract_change_count
from mhc.config import EXPERIMENT_DIRECTORY

CHANGE_COLUMNS = [
    "ch_all",
    "ch_diff",
    *[f"ch_{change_type.name.lower()}" for change_type in MethodChangeType],
]


def iter_tool_history_directories(history_root: Path) -> list[Path]:
    if not history_root.exists():
        return []

    return sorted(path for path in history_root.iterdir() if path.is_dir())


def order_change_columns(df: pd.DataFrame) -> pd.DataFrame:
    metadata_columns = [column for column in df.columns if not column.startswith("ch_")]
    change_columns = [column for column in CHANGE_COLUMNS if column in df.columns]
    extra_change_columns = [
        column
        for column in df.columns
        if column.startswith("ch_") and column not in change_columns
    ]
    return df[metadata_columns + change_columns + extra_change_columns]


def main() -> None:
    experiment_directory = Path(EXPERIMENT_DIRECTORY)
    repository_df = pd.read_csv(experiment_directory / "project.csv")
    repository_name_map = {row["project"]: row for row in repository_df.to_dict(orient="records")}
    history_root = experiment_directory / "method-history-gz"

    for tool_directory in iter_tool_history_directories(history_root):
        tool_name = tool_directory.name
        processed_count = 0
        skipped_count = 0
        empty_history_count = 0
        invalid_history_count = 0

        for zip_file in tool_directory.rglob("*.tar.gz"):
            method_history_list = []
            repository_name = zip_file.name[:-len(".tar.gz")]
            if repository_name in repository_name_map:
                print(f"Processing: {repository_name} [{tool_name}]")
                repository_url = repository_name_map[repository_name]["url"]
                repository_hash = repository_name_map[repository_name]["updated_hash"]
                try:
                    tar_cm = tarfile.open(zip_file, "r:gz")
                except Exception:
                    logging.warning("Skipping unreadable archive: %s", zip_file)
                    skipped_count += 1
                    continue
                with tar_cm as tar:
                    try:
                        members = tar.getmembers()
                    except EOFError:
                        logging.warning("Truncated archive (EOFError), skipping: %s", zip_file)
                        skipped_count += 1
                        continue
                    for member in members:
                        if member.isfile() and member.name.endswith(".json"):
                            _, base_file = member.name.split("/", maxsplit=1)
                            file_content = tar.extractfile(member)
                            if file_content is not None:
                                try:
                                    raw_history = file_content.read()
                                    if not raw_history.strip():
                                        empty_history_count += 1
                                        continue
                                    history_json = json.loads(raw_history)
                                except json.JSONDecodeError:
                                    invalid_history_count += 1
                                    continue
                                except Exception:
                                    logging.exception(
                                        "Unexpected error loading history json for %s %s",
                                        tool_name,
                                        member,
                                    )
                                    continue
                                change_history = extract_change_count(history_json)

                                method_url = util.convert_method_file_to_method_url(
                                    repository_url, repository_hash, base_file
                                )
                                method_history = {
                                    "url": method_url,
                                    "tool_name": tool_name,
                                    "method_file": base_file
                                }
                                method_history.update(change_history)
                                method_history_list.append(method_history)
                method_file = util.format_method_list_file(str(experiment_directory), repository_name)
                if os.path.exists(method_file):
                    method_list_df = pd.read_csv(
                        method_file,
                        keep_default_na=False,
                        na_filter=False,
                        low_memory=False,
                    )
                    repository_change_history_file = experiment_directory / "method-history" / tool_name / f"{repository_name}.csv"
                    os.makedirs(repository_change_history_file.parent, exist_ok=True)
                    repository_change_history_df = pd.merge(
                        method_list_df,
                        pd.DataFrame(method_history_list),
                        on="url",
                        how="inner",
                    )
                    order_change_columns(repository_change_history_df).to_csv(
                        repository_change_history_file,
                        index=False,
                    )
                    processed_count += 1
                else:
                    print(f"Skipping: {repository_name} [{tool_name}] (missing method file)")
                    warnings.warn(f"Missing method history file for {tool_name} {repository_name}")
                    skipped_count += 1
            else:
                print(f"Skipping: {repository_name} [{tool_name}] (not in project.csv)")
                skipped_count += 1

        print(
            f"generate_change summary [{tool_name}]: "
            f"processed={processed_count}, skipped={skipped_count}, "
            f"empty_history={empty_history_count}, invalid_history={invalid_history_count}"
        )


if __name__ == "__main__":
    main()
