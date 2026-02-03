import os
import unittest

import pandas as pd

from mhc.config import *


class RepositoryDatasetTestCase(unittest.TestCase):
    def __init__(self, *args, **kwargs):
        super(RepositoryDatasetTestCase, self).__init__(*args, **kwargs)
        self.repositories_df = pd.read_csv(f"{DATA_DIRECTORY}/repository/repository.csv")

    def test_repository_count(self):
        for dataset_name, repository_count in {"friesen": 49, "chowdhury": 49, "codeshovel": 20,
                                               "historyfinder": 20}.items():
            self.assertEqual(len(self.repositories_df[self.repositories_df["source"].str.contains(dataset_name)]),
                             repository_count, f"{dataset_name}")

    def test_repository_deduplication(self):
        self.assertEqual(len(set(self.repositories_df["repo_name"].tolist())), len(self.repositories_df), "Duplicate name")
        self.assertEqual(len(set(self.repositories_df["url"].tolist())), len(self.repositories_df), "Duplicate URL")


if __name__ == '__main__':
    unittest.main()
