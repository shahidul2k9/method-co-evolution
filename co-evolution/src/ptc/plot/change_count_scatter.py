import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from graph_util import *
from mhc.config import DATA_DIRECTORY, CACHE_DIRECTORY
from ptc.constants import *

CHANGE_CORRELATION = "Change Correlation"
code_shovel_unsupported_change_set = {f"ch_{change_type.name.lower()}" for change_type in
                                      CODE_SHOVEL_UNSUPPORTED_CHANGES}
history_repository_dfs = [pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False) for
                          repository_history_file in list(Path(f"{DATA_DIRECTORY}/pt-change-count").rglob("*.csv"))[
                              :int(os.getenv("METHOD_EVOLUTION_EXPERIMENT_REPOSITORY_COUNT", -1))]]
df = pd.concat(history_repository_dfs)
CALLER_CALLEE_PREFIXES = ["caller_", "callee_"]
for prefix in CALLER_CALLEE_PREFIXES:
    df[f"{prefix}method_type"] = df[f"{prefix}method_type"].map(lambda mt: "test" if mt == "test_util" else mt)

ch_cols = [c[len("caller_"):] for c in df.columns if c.startswith("caller_ch_")]
method_types = sorted(df["caller_method_type"].unique())
tools = sorted(df["caller_tool_name"].unique())

for tool in tools:
    tool_df = df[(df["caller_tool_name"] == tool) & (df["callee_tool_name"] == tool)]

    projects = sorted(
        tool_df["caller_name"].unique(),
        key=lambda x: x.lower()
    )

    projects.append(ALL_REPOSITORY)
    projects.append(CHANGE_CORRELATION)
    n_rows = len(projects)
    n_cols = len(ch_cols)

    fig, axes = plt.subplots(
        n_rows, n_cols,
        figsize=(4 * n_cols, 3.2 * n_rows),
        sharey=True
    )

    if n_rows == 1:
        axes = [axes]

    correlations = []
    for repository_index, project in enumerate(projects):
        if project == ALL_REPOSITORY:
            pdf = tool_df
        elif project == CHANGE_CORRELATION:
            pdf = pd.DataFrame(correlations)
        else:
            pdf = tool_df[tool_df["caller_name"] == project]

        correlation = {"name": project}
        for change_index, ch in enumerate(ch_cols):
            ax = axes[repository_index][change_index] if n_cols > 1 else axes[repository_index]

            if project == CHANGE_CORRELATION:
                ax.plot(range(len(pdf)), pdf[ch], linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                        ls=GRAPH_STYLES[change_index % len(GRAPH_STYLES)])
            else:
                g = pdf[(pdf["caller_method_type"] == "test") & (pdf["callee_method_type"] == "production")]
                x, y = g[f"callee_{ch}"], g[f"caller_{ch}"]

                ax.plot(x, y, linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                        ls=GRAPH_STYLES[change_index % len(GRAPH_STYLES)])

                ax.set_xlabel(f"production\n{ch.replace('ch_', '')}".capitalize(), fontsize=24)
                ax.set_ylabel("test".capitalize(), fontsize=24)
                correlation[ch] = corr = x.corr(y)
                correlations.append(correlation)

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

    fig.tight_layout()
    fig_file = f"{CACHE_DIRECTORY}/figure/change-count-scatter-{tool}.pdf"
    os.makedirs(os.path.dirname(fig_file), exist_ok=True)
    fig.savefig(fig_file,
                bbox_inches="tight")
    plt.close(fig)
