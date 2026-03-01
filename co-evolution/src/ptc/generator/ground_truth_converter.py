from pathlib import Path
import pandas as pd
from mhc.config import *
import warnings
fanout_dir = Path(f"{CACHE_DIRECTORY}/data/fan-out")
ground_truth_dir = Path(f"{CACHE_DIRECTORY}/data/ground-truth")
output_dir = Path(f"{CACHE_DIRECTORY}/data/t2p-ground-truth")
output_dir.mkdir(parents=True, exist_ok=True)

for gt_file in ground_truth_dir.glob("*.csv"):
    fanout_file = fanout_dir / gt_file.name

    if fanout_file.exists():
        gt_df = pd.read_csv(gt_file)
        gt_df.rename(columns={"project": "repo_name", "test-fqn": "from_fqn", "tested-method-fqn": "to_fqn" }, inplace=True)
        fanout_df = pd.read_csv(fanout_file)

        merged_df = gt_df.merge(
            fanout_df,
            how="left",
            left_on=["repo_name", "from_fqn", "to_fqn"],
            right_on=["repo_name", "from_fqn", "to_fqn"],
            suffixes=(None, None)
        ).drop(columns=[], errors="ignore")

        merged_df.to_csv(output_dir / gt_file.name, index=False)
    else:
        warnings.warn(f"Skipping {gt_file.name}: no matching fan-out file found")