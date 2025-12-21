import os
import pandas as pd
from urllib.parse import urlparse
import json
DATA_DIRECTORY = ".cache/data"

# %% Create Test Method Oracle for the CodeShovel and HistoryFinder repositories


all_test_method_df = pd.DataFrame()
for repository_file in ["code-shovel-repository.csv", "history-finder-repository.csv"]:
    repository_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/{repository_file}")
    for repository in repository_df["name"].tolist():
        method_file = f"{DATA_DIRECTORY}/method/{repository}--method.csv"
        if os.path.exists(method_file):
            method_df = pd.read_csv(method_file)
            test_method_df = method_df[method_df["method_type"] == "test"]

            if len(test_method_df) > 0:
                all_test_method_df = pd.concat([all_test_method_df, test_method_df.sample(1)])
                print(f"{repository}: {len(test_method_df)}/{len(method_df)}")
            else:
                print(f"Missing test methods {repository}: {len(method_df)}")
        else:
            print(f"Missing file {repository}: {method_file}")
all_test_method_df.to_csv(f"{DATA_DIRECTORY}/test-method-oracle.csv", index=False)

# %%
method_df = pd.read_csv(f"{DATA_DIRECTORY}/test-method-oracle.csv")
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
        output_stream.write(json.dumps(json_history))
    counter += 1

