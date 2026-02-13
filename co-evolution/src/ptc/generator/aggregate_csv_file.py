from mhc.config import *
import pandas as pd
from pathlib import Path
def aggregate_csv_files(input_dir: str, output_file_name: str):
    dfs = [pd.read_csv(file, keep_default_na=False, na_filter=False) for
           file in list(Path(input_dir).rglob("*.csv"))]
    if len(dfs) > 0:
        df =  pd.concat(dfs)
        df.to_csv(f"{DATA_DIRECTORY}/aggregate/{output_file_name}", index=False)

aggregate_csv_files(f"{DATA_DIRECTORY}/pt-link", "pt-link.csv")

for tooName in os.listdir(f"{DATA_DIRECTORY}/pt-change"):
    for link_strategy in os.listdir(f"{DATA_DIRECTORY}/pt-change/{tooName}"):
        # print(f"{DATA_DIRECTORY}/pt-change/{tooName}/{link_strategy}")
        aggregate_csv_files(f"{DATA_DIRECTORY}/pt-change/{tooName}/{link_strategy}", f"pt-change--{tooName}--{link_strategy}.csv")
