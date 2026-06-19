from __future__ import annotations

from pathlib import Path

import pandas as pd
from mhc.command_util import build_experiment_parser, resolve_experiment_paths


DEFAULT_INPUT = Path("data") / "research-question" / "rq1" / "method-level-revision-history-metric.csv"
DEFAULT_OUTPUT = Path("figure") / "method-history-runtime-table.tex"
RUNTIME_SUFFIX = "_runtime"
STATISTICS = ("mean", "median", "max")
EXCLUDED_RUNTIME_TOOLS = {"intelliJ"}
TOOL_NAMES = {
    "historyFinder": "HistoryFinder",
    "codeShovel": "CodeShovel",
    "codeTracker": "CodeTracker",
    "intelliJ": "IntelliJ",
    "gitLineRange": "GitLineRange",
    "gitFuncName": "GitFuncName",
}


def build_parser():
    parser = build_experiment_parser(
        "Generate a LaTeX table summarizing method-history tool runtimes.",
        include_tools=False,
        include_projects=False,
        include_strategies=False,
        include_project_directory=True,
        include_output_directory=True,
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="Runtime metric CSV. Defaults to <project-directory>/data/research-question/rq1/method-level-revision-history-metric.csv.",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help=(
            "Generated LaTeX file. Relative paths resolve from the experiment directory. "
            "Defaults to <workspace-directory>/experiment/<experiment-name>/figure/"
            "method-history-runtime-table.tex."
        ),
    )
    return parser


def display_tool_name(tool: str) -> str:
    return TOOL_NAMES.get(tool, tool)


def escape_latex(value: object) -> str:
    text = str(value)
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


def calculate_runtime_statistics(df: pd.DataFrame) -> pd.DataFrame:
    runtime_columns = [column for column in df.columns if column.endswith(RUNTIME_SUFFIX)]
    if not runtime_columns:
        raise ValueError(f"No columns ending with {RUNTIME_SUFFIX!r} were found.")

    rows = []
    for column in runtime_columns:
        tool = column[: -len(RUNTIME_SUFFIX)]
        if tool in EXCLUDED_RUNTIME_TOOLS:
            continue

        runtimes_ms = pd.to_numeric(df[column], errors="coerce").dropna()
        if runtimes_ms.empty:
            raise ValueError(f"Runtime column contains no numeric values: {column}")

        runtimes_seconds = runtimes_ms / 1000
        rows.append(
            {
                "tool": tool,
                "mean": runtimes_seconds.mean(),
                "median": runtimes_seconds.median(),
                "max": runtimes_seconds.max(),
            }
        )

    return pd.DataFrame(rows, columns=["tool", *STATISTICS])


def format_runtime(value: float, *, bold: bool = False) -> str:
    formatted = f"{value:.2f}"
    return rf"\textbf{{{formatted}}}" if bold else formatted


def render_latex_table(stats_df: pd.DataFrame) -> str:
    minimums = {statistic: stats_df[statistic].min() for statistic in STATISTICS}
    rows = []
    for _, row in stats_df.iterrows():
        values = [
            format_runtime(
                row[statistic],
                bold=bool(row[statistic] == minimums[statistic]),
            )
            for statistic in STATISTICS
        ]
        rows.append(
            f"{escape_latex(display_tool_name(row['tool']))} & "
            + " & ".join(values)
            + r" \\"
        )

    body = "\n".join(rows)
    return rf"""\begin{{tabular}}{{lrrr}}
\toprule
\textbf{{Tool}} & \textbf{{Mean}} & \textbf{{Median}} & \textbf{{Max}} \\
\midrule
{body}
\bottomrule
\end{{tabular}}
"""


def resolve_path(project_directory: Path, explicit_path: str | None, default_path: Path) -> Path:
    if explicit_path is None:
        return project_directory / default_path
    path = Path(explicit_path)
    return path if path.is_absolute() else project_directory / path


def resolve_output_file(
    project_directory: Path,
    experiment_directory: Path,
    output_directory: str | None,
    output_file: str | None,
    default_output: Path,
) -> Path:
    if output_directory is not None and output_file is not None:
        raise ValueError("--output-directory and --output-file cannot be used together.")
    if output_directory is not None:
        return resolve_path(project_directory, output_directory, Path()) / default_output.name
    return resolve_path(experiment_directory, output_file, default_output)


def main(argv: list[str] | None = None) -> Path:
    args = build_parser().parse_args(argv)
    project_directory = Path(args.project_directory)
    experiment_directory = resolve_experiment_paths(
        args.workspace_directory,
        args.experiment_name,
    ).experiment_directory
    input_file = resolve_path(project_directory, args.input_file, DEFAULT_INPUT)
    output_file = resolve_output_file(
        project_directory,
        experiment_directory,
        args.output_directory,
        args.output_file,
        DEFAULT_OUTPUT,
    )

    if not input_file.exists():
        raise FileNotFoundError(f"Runtime metric CSV not found: {input_file}")

    metric_df = pd.read_csv(input_file)
    stats_df = calculate_runtime_statistics(metric_df)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(render_latex_table(stats_df), encoding="utf-8")
    print(f"Wrote runtime table: {output_file}")
    return output_file


if __name__ == "__main__":
    main()
