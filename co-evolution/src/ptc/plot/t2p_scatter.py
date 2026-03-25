import os
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

import mhc.util as util
from ptc.plot_util import *
from mhc.config import DATA_DIRECTORY, CACHE_DIRECTORY
from ptc.constants import *

code_shovel_unsupported_change_set = {f"ch_{change_type.name.lower()}" for change_type in
                                      CODE_SHOVEL_UNSUPPORTED_CHANGES}

tools = util.sorted_directory_names(f"{DATA_DIRECTORY}/t2p-change")
for tool in tools:
    for link_strategy in util.sorted_directory_names(f"{DATA_DIRECTORY}/t2p-change/{tool}"):

        history_repository_dfs = [pd.read_csv(repository_history_file, keep_default_na=False, na_filter=False) for
                                  repository_history_file in
                                  list(Path(f"{DATA_DIRECTORY}/t2p-change/{tool}/{link_strategy}").rglob("*.csv"))[
                                      :int(os.getenv("METHOD_EVOLUTION_EXPERIMENT_REPOSITORY_COUNT", -1))]]
        history_repository_dfs = [d for d in history_repository_dfs if not d.empty ]
        if history_repository_dfs:
            df = pd.concat(history_repository_dfs)
            print(tool, link_strategy)
            for prefix in ["from_", "to_"]:
                df[f"{prefix}artifact"] = df[f"{prefix}artifact"].map(lambda mt: "test" if mt == "test_util" else mt)

            change_cols = [c[len("from_"):] for c in df.columns if c.startswith("from_ch_")]
            tool_df = df

            projects = sorted(
                tool_df["project"].unique(),
                key=lambda x: x.lower()
            )

            projects.append(ALL_REPOSITORY)
            n_rows = len(projects)
            n_cols = len(change_cols)

            fig, axes = plt.subplots(
                n_rows, n_cols,
                figsize=(4 * n_cols, 3.2 * n_rows)
            )

            if n_rows == 1:
                axes = [axes]

            for repository_index, project in enumerate(projects):
                if project == ALL_REPOSITORY:
                    pdf = tool_df
                else:
                    pdf = tool_df[tool_df["project"] == project]

                for change_index, change in enumerate(change_cols):
                    ax = axes[repository_index][change_index] if n_cols > 1 else axes[repository_index]
                    unsupported = tool == 'codeShovel' and change in code_shovel_unsupported_change_set
                    ax.set_title(f"{change.replace('ch_', '')}".capitalize(), fontsize=24)

                    if unsupported:
                        ax.text(
                            0.5, 0.5, "NA",
                            ha="center", va="center",
                            fontsize=26,
                            transform=ax.transAxes
                        )
                    else:
                        pair_df = pdf[[f"to_{change}", f"from_{change}"]].dropna()
                        x = pair_df[f"to_{change}"]
                        y = pair_df[f"from_{change}"]

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
                        if len(pair_df) < 2 or x.std() == 0 or y.std() == 0:
                            corr = np.nan
                        else:
                            corr = x.corr(y, method="kendall")


                    if change_index == 0:
                        ax.text(-0.5, 0.5, project, transform=ax.transAxes,
                                rotation=90, va='center', ha='center', fontsize=24)
                    ax.grid(True, alpha=0.25)

            fig.tight_layout()
            fig_file = f"{CACHE_DIRECTORY}/figure/t2p-scatter/t2p-scatter--{tool}--{link_strategy}.pdf"
            os.makedirs(os.path.dirname(fig_file), exist_ok=True)
            fig.savefig(fig_file,
                        bbox_inches="tight")
            plt.close(fig)
