from __future__ import annotations

import os
from pathlib import Path

import pandas as pd

from mhc.command_util import (
    load_test_smell_names,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_smell_detector,
)
from ptc.generator.t2p_test_smell_association import DEFAULT_CHANGE, OUTPUT_FILE_NAME
from ptc.generator.t2p_test_smell_prevalence import ALL_SMELLS
from ptc.generator.t2p_test_smell_revision import REVISION_GROUP_1, REVISION_GROUP_3, normalize_revision_group
from ptc.plot.method_history_runtime_table import resolve_path
from ptc.plot_util import build_experiment_plot_parser

NUMERIC_COLUMNS = [
    "baseline_percent",
    "focal_percent",
    "difference_pp",
    "odds_ratio",
    "odds_ratio_ci_low",
    "odds_ratio_ci_high",
    "fisher_p_adjusted",
    "mh_odds_ratio",
    "mh_p_adjusted",
]


def build_parser():
    parser = build_experiment_plot_parser(
        "Render the RQ4 test-smell association table.",
        include_projects=False,
        include_revision_types=False,
        include_smell_detector=True,
        include_project_directory=True,
        include_output_directory=True,
    )
    parser.add_argument("--change", default=DEFAULT_CHANGE)
    parser.add_argument(
        "--revision-group-pair",
        default=f"{REVISION_GROUP_3},{REVISION_GROUP_1}",
        help="Focal,baseline revision-group pair to render. Defaults to HTR,NTR.",
    )
    return parser


def selected_revision_group_pair(value: str) -> tuple[str, str]:
    names = [normalize_revision_group(part.strip()) for part in str(value).split(",") if part.strip()]
    if len(names) != 2:
        raise ValueError("--revision-group-pair must use focal,baseline format, for example HTR,NTR.")
    return names[0], names[1]


def escape_latex(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    return text.replace("\\", r"\textbackslash{}").replace("&", r"\&").replace("%", r"\%").replace("_", r"\_")


def numeric_table_frame(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for column in NUMERIC_COLUMNS:
        if column in output.columns:
            output[column] = pd.to_numeric(output[column], errors="coerce")
    return output


def format_number(value: object, spec: str, *, missing: str = "--") -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return missing
    return format(float(number), spec)


def format_p(value: object) -> str:
    number = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(number):
        return ""
    return r"$<.001$" if number < 0.001 else f"{number:.3f}"


def render_latex_table(frame: pd.DataFrame, smell_names: dict[str, str]) -> str:
    frame = numeric_table_frame(frame)
    individual = frame[frame["smell"] != ALL_SMELLS].sort_values("difference_pp", ascending=False)
    rows = []
    for _, row in individual.iterrows():
        smell = escape_latex(smell_names.get(row["smell"], row["smell"]))
        odds_ratio = format_number(row["odds_ratio"], ".2f")
        odds_ratio_low = format_number(row["odds_ratio_ci_low"], ".2f")
        odds_ratio_high = format_number(row["odds_ratio_ci_high"], ".2f")
        rows.append(
            f"{smell} & {format_number(row['baseline_percent'], '.1f')} & "
            f"{format_number(row['focal_percent'], '.1f')} & "
            f"{format_number(row['difference_pp'], '+.1f')} & {odds_ratio} "
            f"[{odds_ratio_low}, {odds_ratio_high}] & "
            f"{format_p(row['fisher_p_adjusted'])} & {format_number(row['mh_odds_ratio'], '.2f')} & "
            f"{format_p(row['mh_p_adjusted'])} \\\\"
        )
    body = "\n".join(rows)
    return rf"""\begin{{tabular}}{{lrrrrrrr}}
\toprule
\textbf{{Test smell}} & \textbf{{NTR \%}} & \textbf{{HTR \%}} & \textbf{{$\Delta$ pp}} &
\textbf{{OR [95\% CI]}} & \textbf{{$p_{{BH}}$}} & \textbf{{MH OR}} & \textbf{{MH $p_{{BH}}$}} \\
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
    input_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    if not input_file.exists():
        print(f"Association file not found: {input_file}")
        return
    selected_tools, _, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    focal_group, baseline_group = selected_revision_group_pair(args.revision_group_pair)
    frame = pd.read_csv(input_file, keep_default_na=False, na_filter=False)
    frame = frame[(frame["smell_detector"] == smell_detector) & (frame["change"] == args.change)]
    if {"baseline_group", "focal_group"}.issubset(frame.columns):
        frame = frame[
            (frame["baseline_group"] == baseline_group)
            & (frame["focal_group"] == focal_group)
        ]
    if "loc_group" in frame.columns:
        frame = frame[frame["loc_group"] == "ALL"]
    if selected_tools is not None:
        frame = frame[frame["tool"].isin(selected_tools)]
    if selected_strategies is not None:
        frame = frame[frame["strategy"].isin(selected_strategies)]
    smell_names = load_test_smell_names(smell_detector)
    for row in frame[["strategy", "tool", "smell_detector", "change"]].drop_duplicates().itertuples(index=False):
        table_df = frame[(frame["strategy"] == row.strategy) & (frame["tool"] == row.tool)]
        output_file = (
            output_directory
            / f"t2p-test-smell-association-table--{row.tool}--{row.strategy}--{row.smell_detector}--{row.change}.tex"
        )
        os.makedirs(output_file.parent, exist_ok=True)
        output_file.write_text(render_latex_table(table_df, smell_names), encoding="utf-8")
        print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
