import os
import pandas as pd

# %% Create Test Method Oracle for the Code Shovel listed repositories
CODE_SHOVEL_REPOSITORIES = ["checkstyle", "commons-lang", "flink", "hibernate-orm", "javaparser", "jgit", "junit4",
                            "junit5", "okhttp", "spring-framework", "commons-io", "elasticsearch", "hadoop",
                            "hibernate-search", "intellij-community", "jetty", "lucene-solr", "mockito", "pmd",
                            "spring-boot"]
print(len(CODE_SHOVEL_REPOSITORIES))
DATA_DIRECTORY = ".cache/data"

all_test_method_df = pd.DataFrame()
for repository in CODE_SHOVEL_REPOSITORIES:
    method_file = os.path.join(DATA_DIRECTORY, f"{repository}--method.csv")
    if os.path.exists(method_file):
        method_df = pd.read_csv(method_file)
        method_df["repository"] = repository * len(method_df)
        test_method_df = method_df[method_df["method_type"] == "test"]

        if len(test_method_df) > 0:
            all_test_method_df = pd.concat([all_test_method_df, test_method_df.sample(1)])
            print(f"{repository}: {len(test_method_df)}/{len(method_df)}")
all_test_method_df.to_csv(os.path.join(DATA_DIRECTORY, "test-method-oracle.csv"), index=False)
# all_test_method_df[["repository", "file", "method_name", "start_line"]].to_csv(
#     os.path.join(DATA_DIRECTORY, "test-method-oracle.csv"), index=False)
