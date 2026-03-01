from pathlib import Path
import pandas as pd
from mhc.config import *
import warnings
from mhc.util import *
fanout_dir = Path(f"{CACHE_DIRECTORY}/data/fan-out")
ground_truth_dir = Path(f"{CACHE_DIRECTORY}/data/ground-truth")
output_dir = Path(f"{CACHE_DIRECTORY}/data/t2p-ground-truth")
output_dir.mkdir(parents=True, exist_ok=True)

for gt_file in ground_truth_dir.glob("*.csv"):
    fanout_file = fanout_dir / gt_file.name

    if fanout_file.exists():
        try:
            gt_df = pd.read_csv(gt_file)
            gt_df.rename(
                columns={
                    "project": "repo_name",
                    "test-fqn": "from_fqn",
                    "tested-method-fqn": "to_fqn",
                },
                inplace=True,
            )
            fanout_df = pd.read_csv(fanout_file)

            merged_df = gt_df.merge(
                fanout_df,
                how="left",
                on=["repo_name", "from_fqn", "to_fqn"],
            )

            merged_df = convert_float_int_columns_to_nullable_int(merged_df)
            merged_df.to_csv(output_dir / gt_file.name, index=False)
        except:
            warnings.warn(f"Could not convert {gt_file}")

    else:
        warnings.warn(f"Skipping {gt_file.name}: no matching fan-out file found")