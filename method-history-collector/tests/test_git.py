import unittest

import pandas as pd

from mhc import git_repository as git
from mhc.config import *


class GitTestCase(unittest.TestCase):
    def test_commit_count(self):
        repository_df = pd.read_csv(os.path.join(CACHE_DIRECTORY, "data/repository/repository.csv"))

        def get_commit_count(row):
            try:
                repository_path = f"{CACHE_DIRECTORY}/repository/{row['name']}"
                git.clone_and_checkout_commit(
                    row["url"],
                    repository_path,
                    row["updated_hash"])
                commits = git.get_all_commit_info(repository_path, row["updated_hash"])
                return len(commits)
            except Exception as e:
                print(e)
                return 0

        repository_df["commits"] = repository_df.apply(
            get_commit_count,
            axis=1)
        repository_df.to_csv(os.path.join(CACHE_DIRECTORY, "data/repository/repository.csv"), index=False)


if __name__ == '__main__':
    unittest.main()
