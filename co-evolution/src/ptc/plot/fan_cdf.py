import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from graph_util import *
from mhc.config import DATA_DIRECTORY, CACHE_DIRECTORY
from ptc.constants import *

code_shovel_unsupported_change_set = {f"ch_{change_type.name.lower()}" for change_type in
                                      CODE_SHOVEL_UNSUPPORTED_CHANGES}

df = pd.concat([pd.read_csv(file, keep_default_na=False, na_filter=False) for
                file in list(Path(f"{DATA_DIRECTORY}/fan-in-out-count").rglob("*.csv"))[:]])
df["method_type"] = df["method_type"].map(lambda mt: "test" if mt == "test_util" else mt)

method_types = sorted(df["method_type"].unique())

projects = sorted(
    df["repo_name"].unique(),
    key=lambda x: x.lower()
)
projects.append(ALL_REPOSITORY)
in_out_types = ["fan_in", "fan_out"]
n_rows = len(projects)
n_cols = len(in_out_types)

fig, axes = plt.subplots(
    n_rows, n_cols,
    figsize=(4 * n_cols, 3.2 * n_rows),
    sharey=True
)

if n_rows == 1:
    axes = [axes]

for repository_index, project in enumerate(projects):
    if project == ALL_REPOSITORY:
        pdf = df
    else:
        pdf = df[df["repo_name"] == project]

    for change_index, ch in enumerate(in_out_types):
        ax = axes[repository_index][change_index] if n_cols > 1 else axes[repository_index]

        for mtype, g in pdf.groupby("method_type"):
            x, y = ecdf(g[ch])
            ax.plot(x, y, linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                    ls=GRAPH_STYLES[change_index % len(GRAPH_STYLES)],
                    label=mtype)
        ax.set_xscale("log")
        # ax.set_yscale("log")
        ax.set_xlabel(ch.replace("_", " ").capitalize(), fontsize=24)
        if change_index == 0:
            ax.legend(loc="lower right", fontsize=20)

        if change_index == 0:
            ax.set_ylabel(f"{project}", fontsize=24)
        ax.grid(True, alpha=0.25)

fig.tight_layout()
fig_file = f"{CACHE_DIRECTORY}/figure/fan-in-out-cdf.pdf"
os.makedirs(os.path.dirname(fig_file), exist_ok=True)
fig.savefig(fig_file,
            bbox_inches="tight")
plt.close(fig)
