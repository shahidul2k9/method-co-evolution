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

tools = sorted(os.listdir(f"{DATA_DIRECTORY}/pt-change"))
for tool in tools:
    for link_strategy in sorted(os.listdir(f"{DATA_DIRECTORY}/pt-change/{tool}")):

        history_repository_dfs = [pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False) for
                                  repository_history_file in
                                  list(Path(f"{DATA_DIRECTORY}/pt-change/{tool}/{link_strategy}").rglob("*.csv"))[
                                      :int(os.getenv("METHOD_EVOLUTION_EXPERIMENT_REPOSITORY_COUNT", -1))]]
        df = pd.concat(history_repository_dfs)
        CALLER_CALLEE_PREFIXES = ["caller_", "callee_"]
        for prefix in CALLER_CALLEE_PREFIXES:
            df[f"{prefix}method_type"] = df[f"{prefix}method_type"].map(lambda mt: "test" if mt == "test_util" else mt)

        ch_cols = [c[len("caller_"):] for c in df.columns if c.startswith("caller_ch_")]
        method_types = sorted(df["caller_method_type"].unique())

        tool_df = df[df["tool_name"] == tool]

        projects = sorted(
            tool_df["repo_name"].unique(),
            key=lambda x: x.lower()
        )

        projects.append(ALL_REPOSITORY)
        projects.append(CHANGE_CORRELATION)
        n_rows = len(projects)
        n_cols = len(ch_cols)

        fig, axes = plt.subplots(
            n_rows, n_cols,
            figsize=(4 * n_cols, 3.2 * n_rows)
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
                pdf = tool_df[tool_df["repo_name"] == project]

            correlation = {"repo_name": project}
            for change_index, ch in enumerate(ch_cols):
                ax = axes[repository_index][change_index] if n_cols > 1 else axes[repository_index]

                if tool == 'codeShovel' and ch in code_shovel_unsupported_change_set:
                    ax.text(
                        0.5, 0.5, "NA",
                        ha="center", va="center",
                        fontsize=26,
                        transform=ax.transAxes
                    )
                else:
                    if project == CHANGE_CORRELATION:
                        x, y = ecdf(pdf[ch])
                        ax.plot(x, y, linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                                ls=GRAPH_STYLES[change_index % len(GRAPH_STYLES)])
                    else:
                        g = pdf[(pdf["caller_method_type"] == "test") & (pdf["callee_method_type"] == "production")]
                        x, y = g[f"callee_{ch}"], g[f"caller_{ch}"]

                        ax.scatter(x.values, y.values, linewidth=GRAPH_WIDTHS[change_index % len(GRAPH_WIDTHS)],
                                   ls=GRAPH_STYLES[change_index % len(GRAPH_STYLES)])
                        # ax.xaxis.set_major_locator(MaxNLocator(integer=True))
                        # ax.yaxis.set_major_locator(MaxNLocator(integer=True))
                        if (x > 0).any():
                            ax.set_xscale("log")

                        if (y > 0).any():
                            ax.set_yscale("log")

                        if change_index == 0:
                            ax.set_xlabel("production".capitalize(), fontsize=20)
                            ax.set_ylabel("test".capitalize(), fontsize=20)
                        if x.std() == 0 or y.std() == 0:
                            correlation[ch] = np.nan
                        else:
                            correlation[ch] = x.corr(y, method="kendall")
                    ax.set_title(f"{ch.replace('ch_', '')}".capitalize(), fontsize=24)


                if change_index == 0:
                    ax.text(-0.5, 0.5, project, transform=ax.transAxes,
                            rotation=90, va='center', ha='center', fontsize=24)
                ax.grid(True, alpha=0.25)
            correlations.append(correlation)

        fig.tight_layout()
        fig_file = f"{CACHE_DIRECTORY}/figure/pt-change-scatter--{tool}--{link_strategy}.pdf"
        os.makedirs(os.path.dirname(fig_file), exist_ok=True)
        fig.savefig(fig_file,
                    bbox_inches="tight")
        plt.close(fig)
