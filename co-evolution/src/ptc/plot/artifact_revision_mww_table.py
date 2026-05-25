import os
import shutil
import subprocess
import warnings
from pathlib import Path

import pandas as pd

from ptc.constants import ALL_REPOSITORY
from ptc.plot_util import (
    build_experiment_plot_parser,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)

TABLE_COLUMNS = ["project", "p-value", "d-value", "+/-", "N", "S", "M", "L"]


def build_parser():
    return build_experiment_plot_parser(
        "Render revision MWU diff tables.",
        include_strategies=False,
    )


def escape_latex(value: object) -> str:
    text = "" if pd.isna(value) else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(character, character) for character in text)


def format_number(value: object) -> str:
    if pd.isna(value):
        return ""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return str(value)


def order_projects(df: pd.DataFrame) -> pd.DataFrame:
    project_order = {ALL_REPOSITORY: 1}
    return (
        df.assign(_project_order=df["project"].map(project_order).fillna(0))
        .sort_values(
            ["_project_order", "project"],
            key=lambda series: series.astype(str).str.lower() if series.name == "project" else series,
        )
        .drop(columns=["_project_order"])
    )


_EFFECT_SIZE_HEADER = r"\multicolumn{4}{c}{\textit{Effect size band (Cliff's~$\delta$)}}"
# Effect size band thresholds follow Romano et al. for Cliff's delta:
#   N = negligible: |d| < 0.147,  S = small: 0.147 <= |d| < 0.33,
#   M = medium: 0.33 <= |d| < 0.474,  L = large: |d| >= 0.474
# Exactly one band column is marked ``x'' per row; the rest are blank.
_EFFECT_SIZE_NOTE = (
    r"Effect size bands follow Romano et al.\ thresholds for Cliff's~$\delta$: "
    r"\textbf{N}~negligible ($|\delta| < 0.147$), "
    r"\textbf{S}~small ($0.147 \le |\delta| < 0.33$), "
    r"\textbf{M}~medium ($0.33 \le |\delta| < 0.474$), "
    r"\textbf{L}~large ($|\delta| \ge 0.474$). "
    r"Exactly one band column is marked \texttt{x} per row."
)


def render_latex_table(tool: str, table_df: pd.DataFrame) -> str:
    rows = []
    for _, row in order_projects(table_df).iterrows():
        rows.append(
            " & ".join(
                [
                    escape_latex(row["project"]),
                    format_number(row["mww_p"]),
                    format_number(row["d_value"]),
                    escape_latex(row["d_sign"]),
                    escape_latex(row["N"]),
                    escape_latex(row["S"]),
                    escape_latex(row["M"]),
                    escape_latex(row["L"]),
                ]
            )
            + r" \\"
        )

    body = "\n".join(rows)
    # +/- and N S M L use equal-width centred columns; @{} removes trailing padding so L sits at the far right.
    _E = r">{\centering\arraybackslash}p{2em}"
    col_spec = rf"l r r {_E} {_E} {_E} {_E} {_E}@{{}}"
    header_row = (
        rf"{escape_latex(TABLE_COLUMNS[0])} & "
        rf"{escape_latex(TABLE_COLUMNS[1])} & "
        rf"{escape_latex(TABLE_COLUMNS[2])} & "
        rf" & "
        rf"{_EFFECT_SIZE_HEADER} \\"
    )
    subheader_row = (
        rf" & & & "
        rf"{escape_latex(TABLE_COLUMNS[3])} & "
        rf"{escape_latex(TABLE_COLUMNS[4])} & "
        rf"{escape_latex(TABLE_COLUMNS[5])} & "
        rf"{escape_latex(TABLE_COLUMNS[6])} & "
        rf"{escape_latex(TABLE_COLUMNS[7])} \\"
    )
    return rf"""\documentclass{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage{{array}}
\usepackage{{booktabs}}
\usepackage{{longtable}}

\begin{{document}}

\section*{{Mann–Whitney U test for production and test code revisions}}

Two-sided Mann--Whitney U test comparing the number of revision of \textbf{{main-code}} methods versus \textbf{{test-code}} methods
per project.
Each row reports the two-sided $p$-value and Cliff's~$\delta$ effect size ($d$).
{_EFFECT_SIZE_NOTE}

\begin{{longtable}}{{{col_spec}}}
\toprule
{header_row}
\cmidrule(l){{5-8}}
{subheader_row}
\midrule
\endfirsthead
\toprule
{header_row}
\cmidrule(l){{5-8}}
{subheader_row}
\midrule
\endhead
{body}
\bottomrule
\end{{longtable}}

\end{{document}}
"""


def compile_latex(tex_file: Path) -> None:
    latex_engine = shutil.which("pdflatex")
    if latex_engine is None:
        warnings.warn(f"pdflatex not found; generated LaTeX only: {tex_file}")
        return

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


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    stats_file = experiment_directory / "aggregate" / "artifact-revision-mww.csv"
    selected_tools, selected_projects, _ = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
    )

    if not stats_file.exists():
        print(f"Stats file not found: {stats_file}")
        return

    df = pd.read_csv(stats_file, keep_default_na=False, na_values=[""])
    required_columns = {"project", "tool", "change", "mww_p", "d_value", "d_sign", "N", "S", "M", "L"}
    missing_columns = sorted(required_columns - set(df.columns))
    if missing_columns:
        raise ValueError(f"Missing required revision MWU column(s): {', '.join(missing_columns)}")

    df = df[df["change"] == "diff"].copy()
    projects = select_named_items(
        list(dict.fromkeys(df["project"].dropna())),
        selected_projects,
        item_label="project",
        strict=False,
    )
    if ALL_REPOSITORY in set(df["project"]):
        projects.append(ALL_REPOSITORY)
    df = df[df["project"].isin(projects)].copy()
    if df.empty:
        print("No revision MWU diff rows found.")
        return

    tools = select_named_items(
        sorted(df["tool"].dropna().unique(), key=str.lower),
        selected_tools,
        item_label="tool",
    )
    figure_directory = experiment_directory / "figure"
    os.makedirs(figure_directory, exist_ok=True)

    for tool in tools:
        tool_df = df[df["tool"] == tool].copy()
        if tool_df.empty:
            continue

        tex_file = figure_directory / f"artifact-revision-mww--{tool}.tex"
        tex_file.write_text(render_latex_table(tool, tool_df), encoding="utf-8")
        compile_latex(tex_file)


if __name__ == "__main__":
    main()
