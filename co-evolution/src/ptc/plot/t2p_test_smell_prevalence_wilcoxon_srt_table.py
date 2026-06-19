from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from mhc.command_util import (
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_revision_types,
    resolve_smell_detector,
    select_revision_columns,
)
from ptc.generator.t2p_test_smell_prevalence_wilcoxon_srt import OUTPUT_FILE
from ptc.generator.t2p_test_smell_revision import CHANGE_COLUMNS
from ptc.plot.method_history_runtime_table import resolve_path
from ptc.plot_util import build_experiment_plot_parser

OUTPUT_FILE_PREFIX = "t2p-test-smell-prevalence-wilcoxon-srt-table"
LOC_GROUP_ORDER = ["ALL", "S", "M", "L", "XL"]
LOC_GROUP_LABELS = {
    "ALL": "All",
    "S": "Small",
    "M": "Medium",
    "L": "Large",
    "XL": "Extra-large",
}
NUMERIC_COLUMNS = ["size", "g1_size", "g2_size", "w_stat", "w_p", "d_value"]


def build_parser():
    return build_experiment_plot_parser(
        "Render the RQ4 test-smell Wilcoxon signed-rank and Cliff's delta table.",
        include_projects=False,
        include_revision_types=True,
        include_smell_detector=True,
        include_project_directory=True,
        include_output_directory=True,
    )


def escape_latex(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    return text.replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")


def numeric_table_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in NUMERIC_COLUMNS:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce")
    return output


def loc_group_order(value: object) -> int:
    group = str(value)
    try:
        return LOC_GROUP_ORDER.index(group)
    except ValueError:
        return len(LOC_GROUP_ORDER)


def format_number(value: object, spec: str, *, missing: str = "--") -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return missing
    return format(float(number), spec)


def format_p(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return "--"
    return r"$<.001$" if number < 0.001 else f"{number:.3f}"


def render_latex_table(frame: pd.DataFrame) -> str:
    frame = numeric_table_frame(frame)
    if not frame.empty:
        frame = frame.assign(_loc_order=frame["loc_group"].map(loc_group_order)).sort_values("_loc_order")

    rows = []
    for _, row in frame.iterrows():
        rows.append(
            f"{escape_latex(LOC_GROUP_LABELS.get(str(row['loc_group']), row['loc_group']))} & "
            f"{format_p(row['w_p'])} & {format_number(row['d_value'], '+.2f')} & "
            f"{escape_latex(row['d_sign'])} & {escape_latex(row['effect_size'])} \\\\"
        )
    body = "\n".join(rows)
    return rf"""\begin{{tabular}}{{lrrll}}
\toprule
\textbf{{Group}} & \textbf{{$p$}} & \textbf{{Cliff's $\delta$}} & \textbf{{Sign}} & \textbf{{Effect}} \\
\midrule
{body}
\bottomrule
\end{{tabular}}
"""


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    project_directory = Path(args.project_directory)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    output_directory = (
        resolve_path(project_directory, args.output_directory, Path())
        if args.output_directory is not None
        else experiment_directory / "figure"
    )
    input_file = experiment_directory / "aggregate" / OUTPUT_FILE
    if not input_file.exists():
        print(f"Wilcoxon/SRT file not found: {input_file}")
        return

    selected_tools, _, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_types = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )

    frame = pd.read_csv(input_file, keep_default_na=False, na_filter=False)
    frame = frame[frame["smell_detector"] == smell_detector].copy()
    if selected_tools is not None:
        frame = frame[frame["tool"].isin(selected_tools)]
    if selected_strategies is not None:
        frame = frame[frame["strategy"].isin(selected_strategies)]
    if revision_types:
        frame = frame[frame["change"].isin(revision_types)]

    for row in frame[["strategy", "tool", "smell_detector", "change"]].drop_duplicates().itertuples(index=False):
        table_df = frame[
            (frame["strategy"] == row.strategy)
            & (frame["tool"] == row.tool)
            & (frame["smell_detector"] == row.smell_detector)
            & (frame["change"] == row.change)
        ].copy()
        output_file = (
            output_directory
            / f"{OUTPUT_FILE_PREFIX}--{row.tool}--{row.strategy}--{row.smell_detector}--{row.change}.tex"
        )
        os.makedirs(output_file.parent, exist_ok=True)
        output_file.write_text(render_latex_table(table_df), encoding="utf-8")
        print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
