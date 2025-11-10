import os.path

import pandas as pd

from mhc.method_history_collector import MethodHistoryCollector

# import MethodHistoryCollector
df = pd.read_csv("../../../data/repository.csv")
# url_df = pd.read_csv("../../../.cache/49ChosenProjects.csv")
# name_map = dict(zip(url_df.name, url_df.url))
# print(name_map)
# org_49_map = {}
# with open("../../../.cache/repository-mapping.yml") as f:
#     for line in f.readlines():
#         name, url = list(map(str.strip, line.split(':', 1)))
#         org_49_map[name] = url
# print(org_49_map)
# name_map.update(org_49_map)
# df = df.assign(url=df.name.map(name_map))


# for column in df.columns:
#     if column in ['contributor', 'star']:
#         df[column] =df[column].astype(int)
#     else:
#         df[column] = df[column].astype(str)
# print(df.dtypes)
# df = df.reindex(columns=['name', 'contributor', 'star', 'hash', 'url' ])
# df.to_csv("../../../.cache/repository.csv", index=False)


cache_dir = '../../../.cache'
method_collector = MethodHistoryCollector(cache_dir, os.path.join(cache_dir, 'repository'), cache_dir, os.path.join(cache_dir, 'lib'))
repositories = df['name'].tolist()[:1]
method_collector.scan_method(repositories)
method_collector.collect_method_history(repositories, ['codeShovel'])
