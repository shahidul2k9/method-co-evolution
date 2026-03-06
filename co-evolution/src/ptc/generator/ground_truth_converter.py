from pathlib import Path
import pandas as pd
from mhc.config import *
import warnings
from mhc.util import *

fanout_dir = Path(f"{CACHE_DIRECTORY}/data/fan-out")
ground_truth_dir = Path(f"{CACHE_DIRECTORY}/data/ground-truth")
output_dir = Path(f"{CACHE_DIRECTORY}/data/t2p-ground-truth")
unmatched_dir = Path(f"{CACHE_DIRECTORY}/data/t2p-ground-truth-missing")
output_dir.mkdir(parents=True, exist_ok=True)
unmatched_dir.mkdir(parents=True, exist_ok=True)

for gt_file in ground_truth_dir.glob("*.csv"):
    fanout_file = fanout_dir / gt_file.name

    if fanout_file.exists():
        try:
            gt_df = pd.read_csv(gt_file)
            gt_df.rename(
                columns={
                    "test-fqn": "from_fqs_alt",
                    "tested-method-fqn": "to_fqs_alt",
                },
                inplace=True,
            )

            fanout_df = pd.read_csv(fanout_file)

            # First merge (strict match)
            merged_df = gt_df.merge(
                fanout_df,
                how="left",
                on=["project", "from_fqs_alt", "to_fqs_alt"],
                indicator=True,
            )

            # Rows that did NOT match
            unmatched_df = merged_df[merged_df["_merge"] == "left_only"].copy()

            # Drop merge indicator
            merged_df.drop(columns=["_merge"], inplace=True)

            # Save the normal merged result
            merged_df = convert_float_int_columns_to_nullable_int(merged_df)
            merged_df.to_csv(output_dir / gt_file.name, index=False)

            # ---- Second merge for unmatched (fallback on from_fqn only) ----
            if not unmatched_df.empty:
                unmatched_df = unmatched_df[gt_df.columns]  # keep original GT columns

                recovered_df = unmatched_df.merge(
                    fanout_df,
                    how="left",
                    on=["project", "from_fqs_alt"],
                )

                recovered_df = convert_float_int_columns_to_nullable_int(recovered_df)

                recovered_df.to_csv(
                    unmatched_dir / f"{gt_file.name}",
                    index=False,
                )

        except Exception as e:
            warnings.warn(f"Could not convert {gt_file}: {e}")

    else:
        warnings.warn(f"Skipping {gt_file.name}: no matching fan-out file found")