import os
import pandas as pd
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