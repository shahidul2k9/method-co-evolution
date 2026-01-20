import pandas as pd
import os
from pathlib import Path
import tarfile
import json
from ptc.constants import MethodChangeType
cache_dir = os.environ.get("METHOD_CO_EVOLUTION_CACHE_DIRECTORY")


for tooName in os.listdir(f"{cache_dir}/history"):
    if not tooName.startswith("historyFinder"):
        continue
    for zip_file in Path(f"{cache_dir}/history/{tooName}").rglob("*.tar.gz"):
        method_history_list = []
        repository_name = zip_file.stem
        with tarfile.open(zip_file, "r:gz") as tar:
            for file in tar.getmembers():
                if file.isfile() and file.name.endswith(".json"):
                    _, base_file  = file.name.split("/", maxsplit= 1)
                    file_content = tar.extractfile(file)
                    if file_content is not None:
                        history_json = json.load(file_content)
                        change_commits = history_json["commits"]
                        change_history = {ct.value: 0 for ct in MethodChangeType}
                        change_history["all"] =  len(change_commits)


                        for commit in change_commits:
                            for change_type in commit["changeTags"]:
                                change_history[change_type.lower()] += 1
                        method_history = {"history_file" : base_file}
                        for key, value in change_history.items():
                            method_history[f"change_{key}"] = value
                            method_history_list.append(method_history)
        repository_change_history_file = f"{cache_dir}/data/history/{tooName}/{repository_name}--history.csv"
        os.makedirs(os.path.dirname(repository_change_history_file), exist_ok=True)
        pd.DataFrame(method_history_list).to_csv(repository_change_history_file, index=False)





