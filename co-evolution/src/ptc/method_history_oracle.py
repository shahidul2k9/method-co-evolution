import os
import pandas as pd
from urllib.parse import urlparse
import json
import numpy as np

DATA_DIRECTORY = ".cache/data"

# %% Create Test Method Oracle for the CodeShovel and HistoryFinder repositories


all_taken_test_method_df = pd.read_csv(f"{DATA_DIRECTORY}/oracle/test-method-oracle.csv")
all_test_method_df = pd.DataFrame()
for repository_file in ["code-shovel-repository.csv", "history-finder-repository.csv"]:
    repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/{repository_file}")
    for repository in repository_df["name"].tolist():
        method_file = f"{DATA_DIRECTORY}/method/{repository}--method.csv"
        if os.path.exists(method_file):
            method_df = pd.read_csv(method_file)
            test_method_df = method_df[method_df["method_type"] == "test"]
            taken_test_method_df = all_taken_test_method_df[all_taken_test_method_df["url"].str.contains(f"/{repository}/")]
            if len(taken_test_method_df) > 0:
                all_test_method_df = pd.concat([all_test_method_df, taken_test_method_df])
            if len(test_method_df) > 0 and len(taken_test_method_df) < 3:
                all_test_method_df = pd.concat([all_test_method_df, test_method_df.sample(3 - len(taken_test_method_df), random_state=np.random.randint(0, 2**32 - 1))])
                print(f"{repository}: {len(test_method_df)}/{len(method_df)}")
            else:
                print(f"Missing test methods {repository}: {len(method_df)}")
        else:
            print(f"Missing file {repository}: {method_file}")
all_test_method_df.to_csv(f"{DATA_DIRECTORY}/oracle/test-method-oracle.csv", index=False)

# %%
method_df = pd.read_csv(f"{DATA_DIRECTORY}/oracle/test-method-oracle.csv")
counter = 1001
for row in method_df.itertuples():
    parsed_url = urlparse(row.url)
    parts = parsed_url.path.split("/")
    owner_name = parts[1]
    repository_name = parts[2]
    class_name = parts[-2].split(".")[0]
    file = f"{counter}-{repository_name}-{class_name}-{row.method_name}.json"

    json_history = {
        "repositoryName": repository_name,
        "repositoryUrl": f"{parsed_url.scheme}://{parsed_url.hostname}/{owner_name}/{repository_name}.git",
        "startCommitHash": row.hash,
        "file": row.file,
        "language": "Java",
        "elementType": "method",
        "element": row.method_name,
        "startLine": row.start_line,
        "endLine": row.end_line,
        "commits": []
    }
    oracle_file_path = f"{DATA_DIRECTORY}/oracle/{file}"
    os.makedirs(os.path.dirname(oracle_file_path), exist_ok=True)
    with open(oracle_file_path, "w") as output_stream:
        output_stream.write(json.dumps(json_history, indent=4))
    counter += 1

# %%
import pandas as pd
import subprocess
df = pd.read_csv(f"{DATA_DIRECTORY}/oracle/test-method-oracle.csv")
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
df = pd.read_csv(f"{DATA_DIRECTORY}/method/jgit--method.csv")
df["url"] = df["url"].astype(str).str.replace(
    "https://gerrit.googlesource.com/",
    "https://github.com/eclipse-jgit/",
    regex=False
)
df.to_csv(f"{DATA_DIRECTORY}/method/jgit--method.csv", index=False)