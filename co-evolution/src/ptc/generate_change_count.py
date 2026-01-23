import json
import logging
import os
import re
import tarfile
from pathlib import Path
import pandas as pd
import mhc.util as util
from ptc.constants import MethodChangeType
from mhc.config import *

repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")

repository_name_map = {row["name"]: row for row in repository_df.to_dict(orient="records")}

for tooName in os.listdir(f"{CACHE_DIRECTORY}/history"):
    for zip_file in Path(f"{CACHE_DIRECTORY}/history/{tooName}").rglob("*.tar.gz"):
        method_history_list = []
        repository_name = zip_file.name[:-len(".tar.gz")]
        repository_url = repository_name_map[repository_name]["url"]
        repository_hash = repository_name_map[repository_name]["hash"]
        with tarfile.open(zip_file, "r:gz") as tar:
            for file in tar.getmembers():
                if file.isfile() and file.name.endswith(".json"):
                    _, base_file = file.name.split("/", maxsplit=1)
                    file_content = tar.extractfile(file)
                    if file_content is not None:
                        try:
                            history_json = json.load(file_content)
                        except Exception as e:
                            logging.error(f"Error loading history json for {tooName} {file}")
                            continue
                        change_commits = history_json["changeHistoryDetails"]
                        change_history = {ct.value: 0 for ct in MethodChangeType}
                        diff_commit_count = 0
                        # print(change_history)
                        for commit_hash, commit_detail in change_commits.items():
                            changes = [p.strip() for p in re.split(r'[(),]', commit_detail['type']) if p.strip()]
                            for change_type in changes:
                                change_history[change_type] += 1
                            if "diff" in commit_detail and commit_detail['diff']:
                                diff_commit_count += 1
                            elif "subchanges" in commit_detail:
                                for subchange in commit_detail['subchanges']:
                                    if "diff" in subchange and subchange['diff']:
                                        diff_commit_count += 1

                        method_url = util.convert_method_file_to_method_url(repository_url, repository_hash, base_file)
                        method_history = {"url": method_url,
                                          "tool_name": tooName,
                                          "method_file": base_file,
                                          "ch_all": len(change_commits),
                                          "ch_diff": diff_commit_count}
                        for key, value in change_history.items():
                            method_history[f"ch_{MethodChangeType(key).name.lower()}"] = value
                        method_history_list.append(method_history)
        method_list_df = pd.read_csv(util.format_method_list_file(DATA_DIRECTORY, repository_name),
                                     keep_default_na=False, na_filter=False)
        repository_change_history_file = f"{DATA_DIRECTORY}/history/{tooName}/{repository_name}--history.csv"
        os.makedirs(os.path.dirname(repository_change_history_file), exist_ok=True)
        pd.merge(method_list_df, pd.DataFrame(method_history_list), on="url", how="inner").to_csv(
            repository_change_history_file, index=False)
