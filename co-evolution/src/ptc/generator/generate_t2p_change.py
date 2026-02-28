import warnings
from pathlib import Path

import pandas as pd

from mhc.config import *
from ptc.constants import MethodChangeType

tool_dirs = [
    name for name in os.listdir(f"{DATA_DIRECTORY}/history")
    if os.path.isdir(os.path.join(f"{DATA_DIRECTORY}/history", name))
]
for tooName in tool_dirs:
    for change_file in Path(f"{DATA_DIRECTORY}/history", tooName).rglob("*.csv"):
        change_df = pd.read_csv(change_file, keep_default_na=False, na_filter=False)
        change_df = change_df[
            ["url", "ch_all", "ch_diff"] + [f"ch_{change_type.name.lower()}" for change_type in MethodChangeType]]

        repository_name = change_file.stem
        t2p_strategy_dirs = [
            name for name in os.listdir(f"{DATA_DIRECTORY}/t2p-link")
            if os.path.isdir(os.path.join(f"{DATA_DIRECTORY}/t2p-link", name))
        ]
        for t2p_strategy in t2p_strategy_dirs:
            t2p_file = f"{DATA_DIRECTORY}/t2p-link/{t2p_strategy}/{change_file.name}"
            if os.path.exists(t2p_file):
                t2p_confidence_df = pd.read_csv(t2p_file, keep_default_na=False, na_filter=False)

                t2p_change_df = (t2p_confidence_df.merge(change_df.add_prefix("from_"), on="from_url", how="inner")
                                 .merge(change_df.add_prefix("to_"), on="to_url", how="inner"))

                t2p_change_file = f"{DATA_DIRECTORY}/t2p-change/{tooName}/{t2p_strategy}/{change_file.name}"
                os.makedirs(os.path.dirname(t2p_change_file), exist_ok=True)
                change_df.to_csv(t2p_change_file, index=False)
            else:
                warnings.warn(f"{t2p_file} does not exist")
