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

TABLE_COLUMNS = ["project", "p-value", "d-value", "N", "S", "M", "L"]


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


def render_latex_table(tool: str, table_df: pd.DataFrame) -> str:
    rows = []
    for _, row in order_projects(table_df).iterrows():
        rows.append(
            " & ".join(
                [
                    escape_latex(row["project"]),
                    format_number(row["mwu_p"]),
                    format_number(row["mwu_d"]),
                    escape_latex(row["N"]),
                    escape_latex(row["S"]),
                    escape_latex(row["M"]),
                    escape_latex(row["L"]),
                ]
            )
            + r" \\"
        )

    body = "\n".join(rows)
    return rf"""\documentclass{{article}}
\usepackage[margin=1in]{{geometry}}
\usepackage{{booktabs}}
\usepackage{{longtable}}

\begin{{document}}

\section*{{Revision MWU Diff Table: {escape_latex(tool)}}}

\begin{{longtable}}{{lrrrrrr}}
\toprule
{escape_latex(TABLE_COLUMNS[0])} & {escape_latex(TABLE_COLUMNS[1])} & {escape_latex(TABLE_COLUMNS[2])} & {escape_latex(TABLE_COLUMNS[3])} & {escape_latex(TABLE_COLUMNS[4])} & {escape_latex(TABLE_COLUMNS[5])} & {escape_latex(TABLE_COLUMNS[6])} \\
\midrule
\endfirsthead
\toprule
{escape_latex(TABLE_COLUMNS[0])} & {escape_latex(TABLE_COLUMNS[1])} & {escape_latex(TABLE_COLUMNS[2])} & {escape_latex(TABLE_COLUMNS[3])} & {escape_latex(TABLE_COLUMNS[4])} & {escape_latex(TABLE_COLUMNS[5])} & {escape_latex(TABLE_COLUMNS[6])} \\
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
    stats_file = experiment_directory / "aggregate" / "revision_mwu.csv"
    selected_tools, selected_projects, _ = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
    )

    if not stats_file.exists():
        print(f"Stats file not found: {stats_file}")
        return

    df = pd.read_csv(stats_file, keep_default_na=False, na_values=[""])
    required_columns = {"project", "tool", "change", "mwu_p", "mwu_d", "N", "S", "M", "L"}
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

        tex_file = figure_directory / f"revision_mwu--{tool}.tex"
        tex_file.write_text(render_latex_table(tool, tool_df), encoding="utf-8")
        compile_latex(tex_file)


if __name__ == "__main__":
    main()
