from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pandas as pd

from mhc.command_util import (
    load_test_smell_names,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_smell_detector,
)
from ptc.generator.t2p_test_smell_association import DEFAULT_CHANGE, OUTPUT_FILE_NAME, selected_revision_group_pairs
from ptc.generator.t2p_test_smell_prevalence import PSEUDO_SMELLS
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
    parser.add_argument(
        "--output-type",
        choices=("tex", "pdf"),
        default="tex",
        help="Output format. 'tex' writes the tabular fragment; 'pdf' writes a standalone compiled PDF.",
    )
    return parser


def selected_revision_group_pair(value: str) -> tuple[str, str]:
    pairs = selected_revision_group_pairs(value)
    if len(pairs) != 1:
        raise ValueError("--revision-group-pair must contain exactly one focal,baseline pair.")
    return pairs[0]


def pair_suffix(focal_group: str, baseline_group: str, *, include_default: bool = False) -> str:
    if not include_default and (focal_group, baseline_group) == (REVISION_GROUP_3, REVISION_GROUP_1):
        return ""
    return f"--{focal_group}-{baseline_group}"


def has_explicit_revision_group_pair(argv: list[str] | None) -> bool:
    arguments = sys.argv[1:] if argv is None else argv
    return "--revision-group-pair" in arguments


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


def render_latex_table(
    frame: pd.DataFrame,
    smell_names: dict[str, str],
    *,
    baseline_group: str = REVISION_GROUP_1,
    focal_group: str = REVISION_GROUP_3,
) -> str:
    frame = numeric_table_frame(frame)
    individual = frame[~frame["smell"].isin(PSEUDO_SMELLS)].sort_values("difference_pp", ascending=False)
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
\textbf{{Test smell}} & \textbf{{{baseline_group} \%}} & \textbf{{{focal_group} \%}} & \textbf{{$\Delta$ pp}} &
\textbf{{OR [95\% CI]}} & \textbf{{$p_{{BH}}$}} & \textbf{{MH OR}} & \textbf{{MH $p_{{BH}}$}} \\
\midrule
{body}
\bottomrule
\end{{tabular}}
"""


def render_standalone_latex_table(table_latex: str) -> str:
    return rf"""\documentclass{{article}}
\usepackage[landscape,margin=0.5in]{{geometry}}
\usepackage{{booktabs}}
\usepackage{{graphicx}}

\begin{{document}}
\pagestyle{{empty}}

\begin{{center}}
\resizebox{{\textwidth}}{{!}}{{%
{table_latex}
}}
\end{{center}}

\end{{document}}
"""


def compile_latex_pdf(tex_file: Path) -> Path:
    latex_engine = shutil.which("pdflatex")
    if latex_engine is None:
        raise SystemExit("pdflatex not found; install a LaTeX distribution or use --output-type tex.")
    subprocess.run(
        [
            latex_engine,
            "-interaction=nonstopmode",
            "-halt-on-error",
            tex_file.name,
        ],
        cwd=tex_file.parent,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return tex_file.with_suffix(".pdf")


def write_table_output(output_file: Path, table_latex: str, output_type: str) -> None:
    os.makedirs(output_file.parent, exist_ok=True)
    if output_type == "tex":
        output_file.write_text(table_latex, encoding="utf-8")
        print(f"Wrote {output_file}")
        return

    output_stem = output_file.stem
    build_directory = output_file.parent / "build" / output_stem
    os.makedirs(build_directory, exist_ok=True)
    build_tex_file = build_directory / f"{output_stem}.tex"
    build_tex_file.write_text(render_standalone_latex_table(table_latex), encoding="utf-8")
    build_pdf_file = compile_latex_pdf(build_tex_file)
    shutil.copy2(build_pdf_file, output_file)
    print(f"Wrote {output_file}")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    include_default_pair_suffix = has_explicit_revision_group_pair(argv)
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
        frame = frame.copy()
        frame["baseline_group"] = frame["baseline_group"].map(normalize_revision_group)
        frame["focal_group"] = frame["focal_group"].map(normalize_revision_group)
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
        output_stem = (
            f"t2p-test-smell-association-table--{row.tool}--{row.strategy}--{row.smell_detector}"
            f"--{row.change}{pair_suffix(focal_group, baseline_group, include_default=include_default_pair_suffix)}"
        )
        output_file = output_directory / f"{output_stem}.{args.output_type}"
        table_latex = render_latex_table(
            table_df,
            smell_names,
            baseline_group=baseline_group,
            focal_group=focal_group,
        )
        write_table_output(output_file, table_latex, args.output_type)


if __name__ == "__main__":
    main()
