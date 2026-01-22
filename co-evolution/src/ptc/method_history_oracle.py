import os
import shutil

import pandas as pd
from urllib.parse import urlparse
import json
import numpy as np
from pathlib import Path
from mhc.config import *

TEST_METHOD_ORACLE_DIRECTORY = os.environ.get("TEST_METHOD_ORACLE_DIRECTORY")

# %% Create Test Method Oracle for the CodeShovel and HistoryFinder repositories


all_taken_test_method_df = pd.read_csv(f"{CACHE_DIRECTORY}/data/oracle/test-method-oracle.csv")
all_test_method_df = pd.DataFrame()
for repository_file in ["code-shovel-repository.csv", "history-finder-repository.csv"]:
    repository_df = pd.read_csv(f"{CACHE_DIRECTORY}/data/repository/{repository_file}")
    for row in repository_df.itertuples():
        repository = row.name
        url = row.url
        method_file = f"{CACHE_DIRECTORY}/data/method/{repository}--method.csv"
        taken_test_method_df = all_taken_test_method_df[all_taken_test_method_df["url"].str.startswith(url)]
        if len(taken_test_method_df) > 0:
            all_test_method_df = pd.concat([all_test_method_df, taken_test_method_df])
        if os.path.exists(method_file):
            method_df = pd.read_csv(method_file)
            test_method_df = method_df[method_df["method_type"] == "test"]
            if len(test_method_df) > 0 and len(taken_test_method_df) < 3:
                seed = np.random.randint(0, 2 ** 32 - 1)
                required_samples = 3 - len(taken_test_method_df)
                new_samples = test_method_df.sample(required_samples, random_state=seed)
                all_test_method_df = pd.concat([all_test_method_df, new_samples])
                print(f"{repository}: {len(test_method_df)}/{len(method_df)}")
                if len(new_samples) < required_samples:
                    print(f"Not enough test methods for {repository}: {len(new_samples)}/{required_samples}")
        else:
            print(f"Missing file {repository}: {method_file}")
all_test_method_df.to_csv(f"{CACHE_DIRECTORY}/data/oracle/test-method-oracle.csv", index=False)


# %% Generate Oracle Files
method_df = pd.read_csv(f"{CACHE_DIRECTORY}/data/oracle/test-method-oracle.csv")
counter = 1001
# target_oracle_directory = TEST_METHOD_ORACLE_DIRECTORY #f"{CACHE_DIRECTORY}/oracle_files"
target_oracle_directory = f"{CACHE_DIRECTORY}/oracle_files"
print(CACHE_DIRECTORY)
print(target_oracle_directory)
shutil.rmtree(target_oracle_directory, ignore_errors=True)
for row in method_df.itertuples():
    parsed_url = urlparse(row.url)
    parts = parsed_url.path.split("/")
    owner_name = parts[1]
    repository_name = parts[2]
    class_name = parts[-1].split(".")[0]
    file = f"{counter}-{repository_name}-{class_name}-{row.method_name}.json"

    json_history = {
        "repositoryName": repository_name,
        "repositoryUrl": f"{parsed_url.scheme}://{parsed_url.hostname}/{owner_name}/{repository_name}.git",
        "startCommitHash": row.hash,
        "file": row.file,
        "url": row.url,
        "language": "Java",
        "elementType": "method",
        "element": row.method_name,
        "startLine": row.start_line,
        "endLine": row.end_line,
        "commits": []
    }
    oracle_file_path = f"{target_oracle_directory}/{file}"
    os.makedirs(os.path.dirname(oracle_file_path), exist_ok=True)
    with open(oracle_file_path, "w") as output_stream:
        output_stream.write(json.dumps(json_history, indent=4))
    counter += 1

# %% Ensure at least 3 commit counts
files = list(map(lambda path: str(path), Path(TEST_METHOD_ORACLE_DIRECTORY).rglob("*.json")))
files = list(filter(lambda f: int(f.split("/")[-1].split("-")[0]) > 1000, files))
remove_urls = []
print(files)

for file in files:
    json_history = json.load(open(file))
    if len(json_history['commits']) < 3:
        # print(f"{len(json_history['commits'])}")
        # print(f"{json_history['file']}")
        remove_urls.append(json_history['url'])
        # shutil.rmtree(file)

print(f"Need to update {len(remove_urls)}/{len(files)}")
all_taken_test_method_df = pd.read_csv(f"{CACHE_DIRECTORY}/data/oracle/test-method-oracle.csv")
all_taken_test_method_df["url"] = all_taken_test_method_df["url"].astype(str)

all_blacklisted_test_method_df = pd.read_csv(f"{CACHE_DIRECTORY}/data/oracle/blacklist-test-method-oracle.csv")
all_blacklisted_test_method_df["url"] = all_blacklisted_test_method_df["url"].astype(str)


all_blacklisted_test_method_df = all_blacklisted_test_method_df[~all_blacklisted_test_method_df["url"].isin(remove_urls)]
all_blacklisted_test_method_df = pd.concat(
    [all_blacklisted_test_method_df, all_taken_test_method_df[all_taken_test_method_df["url"].isin(remove_urls)]])
all_blacklisted_test_method_df.to_csv(f"{CACHE_DIRECTORY}/data/oracle/blacklist-test-method-oracle.csv", index=False)

all_taken_test_method_df = all_taken_test_method_df[~all_taken_test_method_df["url"].isin(remove_urls)]
all_taken_test_method_df.to_csv(f"{CACHE_DIRECTORY}/data/oracle/test-method-oracle.csv", index=False)




# %%
import pandas as pd
import subprocess
df = pd.read_csv(f"{CACHE_DIRECTORY}/data/oracle/test-method-oracle.csv")
x,y = list(map(int, input("Enter project index range : ").split(":")))
urls = df["url"].to_list()
print("Range: {x}-{y}".format(x=x, y=y))
for url in urls[x:y]:
    print(url)
    subprocess.Popen([
        "chromium-browser",
        url
    ])

# %%
import pandas as pd
files = list(map(lambda path: str(path), Path(f"{CACHE_DIRECTORY}/data/method").rglob("*.csv")))
for file in files:
    print(f"processing {file}")
    df = pd.read_csv(file)
    df["url"] = df["url"].astype(str).str.replace(
        "/#L",
        "#L",
        regex=False
    )
    df.to_csv(file, index=False)
