import os
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from constants import CODE_SHOVEL_UNSUPPORTED_CHANGES
from mhc.config import DATA_DIRECTORY, CACHE_DIRECTORY


def ecdf_with_rank(series):
    s = series.sort_values()
    y = s.rank(method="max", pct=True)
    return s, y


def ecdf(a):
    x, counts = np.unique(a, return_counts=True)
    cusum = np.cumsum(counts)
    return x, cusum / cusum[-1]


styles = ["-", "--", "-.", ":", "--", "--", "-.", ":"]
marks = ["^", "d", "o", "v", "p", "s", "<", ">"]
width = [4, 4, 4, 4, 3, 3, 3, 3]
marks_size = [10, 10, 12, 14, 20, 10, 12, 15]
marker_color = ['r', 'b', 'brown', '#c994c7', '#0F52BA', '#ff7518', '#6CA939', '#636363']
gaps = [3, 3, 6, 5, 5, 4, 4, 4]
code_shovel_unsupported_change_set = {f"ch_{change_type.name.lower()}" for change_type in
                                      CODE_SHOVEL_UNSUPPORTED_CHANGES}
history_repository_dfs = [pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False) for
                          repository_history_file in list(Path(f"{DATA_DIRECTORY}/history").rglob("*.csv"))[:]]
df = pd.concat(history_repository_dfs)
df["method_type"] = df["method_type"].map(lambda mt: "test" if mt == "test_util" else mt)
df = df.sort_values(by="name", key=lambda s: s.str.lower())

ch_cols = [c for c in df.columns if c.startswith("ch_")]
method_types = sorted(df["method_type"].unique())
tools = sorted(df["tool_name"].unique())

for tool in tools:
    tool_df = df[df["tool_name"] == tool]

    projects = sorted(
        tool_df["name"].unique(),
        key=lambda x: x.lower()
    )
    projects.append("ALL PROJECTS")
    n_rows = len(projects)
    n_cols = len(ch_cols)

    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(4 * n_cols, 3.2 * n_rows),
        sharey=True
    )

    if n_rows == 1:
        axes = [axes]

    for repository_index, project in enumerate(projects):
        if project == "ALL PROJECTS":
            pdf = tool_df
        else:
            pdf = tool_df[tool_df["name"] == project]

        for change_index, ch in enumerate(ch_cols):
            ax = axes[repository_index][change_index] if n_cols > 1 else axes[repository_index]

            for mtype, g in pdf.groupby("method_type"):
                # x, y = ecdf_with_rank(g[ch])
                x, y = ecdf(g[ch])
                ax.plot(x, y, linewidth=width[change_index % len(width)], ls=styles[change_index % len(styles)],
                        label=mtype)
            ax.set_xlabel(ch.replace("ch_", "").capitalize(), fontsize=24)
            # ax.tick_params(axis="both", labelsize=18)

            if tool == 'codeShovel' and ch in code_shovel_unsupported_change_set:
                ax.text(
                    0.5, 0.5, "NA",
                    ha="center", va="center",
                    fontsize=26,
                    transform=ax.transAxes
                )
            if change_index == 0:
                ax.legend(loc="lower right", fontsize=20)

            if change_index == 0:
                ax.set_ylabel(f"{project}", fontsize=24)
            ax.grid(True, alpha=0.25)

    # fig.suptitle(
    #     f"ECDF of Method Changes per Project — Tool: {tool}",
    #     fontsize=20,
    #     x=0.01,
    #     ha="left",
    #     y=0.98
    # )

    # handles, labels = axes[0][0].get_legend_handles_labels()
    # fig.legend(handles, labels, loc="upper left", ncol=len(method_types) + 1, bbox_to_anchor=(0,1))

    fig.tight_layout()
    fig_file = f"{CACHE_DIRECTORY}/figure/method-change-cdf-{tool}.pdf"
    os.makedirs(os.path.dirname(fig_file), exist_ok=True)
    fig.savefig(fig_file,
                bbox_inches="tight")
    plt.close(fig)
