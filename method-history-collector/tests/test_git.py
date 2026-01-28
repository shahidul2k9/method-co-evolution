import unittest
import os
import pandas as pd
from mhc import git_repository as git
from mhc.config import *


class GitTestCase(unittest.TestCase):
    # def test_commit_count(self):
    #     repository_df = pd.read_csv(os.path.join(CACHE_DIRECTORY, "data/repository/repository.csv"))
    #
    #     def get_commit_count(row):
    #         try:
    #             repository_path = f"{CACHE_DIRECTORY}/repository/{row['name']}"
    #             git.clone_and_checkout_commit(
    #                 row["url"],
    #                 repository_path,
    #                 row["hash"])
    #             commits = git.get_all_commit_info(repository_path, row["hash"])
    #             return len(commits)
    #         except Exception as e:
    #             print(e)
    #             return 0
    #
    #     repository_df["commits"] = repository_df.apply(
    #         get_commit_count,
    #         axis=1)
    #     repository_df.to_csv(os.path.join(CACHE_DIRECTORY, "data/repository/repository.csv"), index=False)
    #
    #

    def test_update_repository_info(self):
        repository_df = pd.read_csv(os.path.join(CACHE_DIRECTORY, "data/repository/repository.csv"))
        updated_repos = []
        for index, row in repository_df.iterrows():
            meta = git.get_repo_metadata(row["url"], os.getenv("GITHUB_API_KEY"))
            meta["name"] = row["name"]
            meta["source"] = row["source"]
            meta["url"] = row["url"]
            updated_repos.append(meta)

        updated_repo_df = pd.DataFrame(updated_repos)
        updated_repo_df = updated_repo_df[
            "name",
            "source",
            "stars",
            "forks",
            "watchers",
            "contributors",
            "commits",
            "updated_at",
            "created_at",
            "url",
            "created_hash",
            "updated_hash",
            "branch"
        ]
        updated_repo_df.to_csv(os.path.join(CACHE_DIRECTORY, "data/repository/repository-v2.csv"), index=False)


if __name__ == '__main__':
    unittest.main()
