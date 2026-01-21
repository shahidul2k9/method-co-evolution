import unittest
import os
import pandas as pd
from mhc import git_repository as git


class GtTestCase(unittest.TestCase):
    def setUp(self):
        self.cache_dir = os.environ.get("METHOD_CO_EVOLUTION_CACHE_DIRECTORY")

    def test_commit_count(self):
        repository_df = pd.read_csv(os.path.join(self.cache_dir, "data/repository/repository.csv"))

        def get_commit_count(row):
            try:
                repository_path = f"{self.cache_dir}/repository/{row["name"]}"
                git.clone_and_checkout_commit(
                    row["url"],
                    repository_path,
                    row["hash"])
                commits = git.get_all_commit_info(repository_path, row["hash"])
                return len(commits)
            except Exception as e:
                print(e)
                return 0

        repository_df["commits"] = repository_df.apply(
            get_commit_count,
            axis=1)
        repository_df.to_csv(os.path.join(self.cache_dir, "data/repository/repository.csv"), index=False)


if __name__ == '__main__':
    unittest.main()
