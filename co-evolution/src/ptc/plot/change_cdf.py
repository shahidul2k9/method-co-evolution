import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from graph_util import *
from mhc.config import DATA_DIRECTORY, CACHE_DIRECTORY
from ptc.constants import *

code_shovel_unsupported_change_set = {f"ch_{change_type.name.lower()}" for change_type in
                                      CODE_SHOVEL_UNSUPPORTED_CHANGES}
history_repository_dfs = [pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False) for
                          repository_history_file in list(Path(f"{DATA_DIRECTORY}/history").rglob("*.csv"))[:]]
df = pd.concat(history_repository_dfs)
df["method_type"] = df["method_type"].map(lambda mt: "test" if mt == "test_util" else mt)
df = df.sort_values(by="repo_name", key=lambda s: s.str.lower())

ch_cols = [c for c in df.columns if c.startswith("ch_")]
method_types = sorted(df["method_type"].unique())
tools = sorted(df["tool_name"].unique())

for tool in tools:
    tool_df = df[df["tool_name"] == tool]
    # print(tool)
    # print(tool_df["repo_name"].unique())
    projects = sorted(
        tool_df["repo_name"]
        .dropna() # investigate nan
        .astype(str)
        .unique(),
        key=lambda x: x.lower()
    )
    projects.append(ALL_REPOSITORY)
    n_rows = len(projects)
    n_cols = len(ch_cols)

    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(4 * n_cols, 3.2 * n_rows))

    if n_rows == 1:
        axes = [axes]

    for repository_index, project in enumerate(projects):
        if project == ALL_REPOSITORY:
            pdf = tool_df
        else:
            pdf = tool_df[tool_df["repo_name"] == project]

        for change_index, ch in enumerate(ch_cols):
            ax = axes[repository_index][change_index] if n_cols > 1 else axes[repository_index]

            max_x = 0
            for mtype, g in pdf.groupby("method_type"):
                x, y = ecdf(g[ch])
                max_x = max(max(x), max_x)
                ax.plot(x, y, linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                        ls=GRAPH_STYLES[change_index % len(GRAPH_STYLES)],
                        label=mtype)
            ax.set_xlabel(ch.replace("ch_", "").capitalize(), fontsize=24)
            if max_x > 50:
                ax.set_xscale("log")
            ax.tick_params(axis="both", labelsize=18)

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
