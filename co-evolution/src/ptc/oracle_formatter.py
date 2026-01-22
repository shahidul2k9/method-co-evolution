import os
from xml.etree.ElementTree import indent

import pandas as pd
from urllib.parse import urlparse
import json

from mhc.config import *

# %%
for file in filter(lambda x: x.endswith(".json"), os.listdir(f"{CACHE_DIRECTORY}/intelliJ-Raw")):
    with open(f"{CACHE_DIRECTORY}/intelliJ-Raw/{file}") as f:
        commits = map(lambda line: line.split()[0], f.readlines())
        commit_list = map(lambda commit_hash: {
            "commitHash": commit_hash,
            "changeTags": []
        }, commits)

        output = {
            "traceMap": {
                "intelliJ": {
                    "commits": list(commit_list)
                }
            }
        }
        os.makedirs("{CACHE_DIRECTORY}/intelliJ", exist_ok=True)
        with open(f"{CACHE_DIRECTORY}/intelliJ/{file}", "w") as f:
            f.write(json.dumps(output, sort_keys=True, indent=4))
