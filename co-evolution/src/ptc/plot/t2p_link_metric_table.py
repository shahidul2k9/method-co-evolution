from __future__ import annotations

from pathlib import Path

import pandas as pd
from mhc.command_util import (
    build_experiment_parser,
    resolve_experiment_filters,
    resolve_experiment_paths,
    select_named_items,
)
from ptc.plot.method_history_runtime_table import resolve_output_file, resolve_path


DEFAULT_OUTPUT = Path("figure") / "t2p-link-metric-table.tex"
DATASET_LABELS = {
    "tctracer-2020": r"TCTracer ICSE~\cite{white_establishing_2020}",
    "tctracer-plus": r"TCTracer ESE~\cite{white_tctracer_2022}",
    "testlinker-plus": r"TestLinker TSE~\cite{sun_method-level_2024}",
    "t2plinker": "Ours",
    "t2plinker-plus": "All",
}
STRATEGY_LABELS = {
    "nc": "NC",
    "ncc": "NCC",
    "omc": "OMC",
    "lcs-u": "LCS-U",
    "lcs-b": "LCS-B",
    "leven": "Leven",
    "lcba": "LCBA",
    "tarantula": "Tarantula",
    "tfidf": "TFIDF",
    "combined": "Combined",
    "testlinkerv2": "TESTLINKER",
}
COUNT_COLUMNS = ("tp", "fp", "fn")
METRIC_COLUMNS = ("precision", "recall", "f1", "map", "auc")
REQUIRED_COLUMNS = {"project", "experiment", "strategy", *COUNT_COLUMNS, *METRIC_COLUMNS}


def build_parser():
    parser = build_experiment_parser(
        "Generate a LaTeX table of average test-to-production link metrics.",
        include_tools=False,
        include_projects=False,
        include_strategies=True,
        include_project_directory=True,
        include_output_directory=True,
        strategies_help="Comma-separated strategy names to include, in display order.",
    )
    parser.add_argument(
        "--input-file",
        default=None,
        help="Metric CSV. Defaults to <workspace-directory>/t2p_link_overall_metric.csv.",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help=(
            "Generated LaTeX file. Relative paths resolve from the experiment directory. "
            "Defaults to <workspace-directory>/experiment/<experiment-name>/figure/"
            "t2p-link-metric-table.tex."
        ),
    )
    return parser


def select_average_rows(metric_df: pd.DataFrame, strategies: list[str]) -> pd.DataFrame:
    missing_columns = sorted(REQUIRED_COLUMNS - set(metric_df.columns))
    if missing_columns:
        raise ValueError(f"Missing required metric column(s): {', '.join(missing_columns)}")

    unknown_strategies = [strategy for strategy in strategies if strategy not in STRATEGY_LABELS]
    if unknown_strategies:
        raise ValueError(
            "Missing display mapping for strategy name(s): "
            + ", ".join(unknown_strategies)
        )

    rows = []
    for experiment in DATASET_LABELS:
        project = f"avg-{experiment}"
        experiment_df = metric_df[
            (metric_df["experiment"] == experiment)
            & (metric_df["project"] == project)
        ]
        if experiment_df.empty:
            raise ValueError(f"Missing aggregate metric row(s) for dataset {experiment!r}.")

        available_strategies = list(dict.fromkeys(experiment_df["strategy"].astype(str)))
        selected_strategies = select_named_items(
            available_strategies,
            strategies,
            item_label=f"strategy for dataset {experiment}",
        )
        indexed_df = experiment_df.drop_duplicates(subset=["strategy"], keep="first").set_index("strategy")
        for strategy in selected_strategies:
            row = indexed_df.loc[strategy].copy()
            row["experiment"] = experiment
            row["strategy"] = strategy
            rows.append(row)

    return pd.DataFrame(rows).reset_index(drop=True)


def format_count(value: object) -> str:
    if pd.isna(value):
        return "--"
    return str(int(float(value)))


def format_metric(value: object, *, bold: bool = False) -> str:
    if pd.isna(value):
        return "--"
    formatted = f"{float(value):.2f}"
    return rf"\textbf{{{formatted}}}" if bold else formatted


def render_latex_table(table_df: pd.DataFrame) -> str:
    dataset_blocks = []
    for experiment, dataset_label in DATASET_LABELS.items():
        dataset_df = table_df[table_df["experiment"] == experiment]
        maximums = {
            column: pd.to_numeric(dataset_df[column], errors="coerce").max()
            for column in METRIC_COLUMNS
        }
        rows = []
        for row_index, (_, row) in enumerate(dataset_df.iterrows()):
            dataset_cell = (
                rf"\multirow{{{len(dataset_df)}}}{{*}}{{{dataset_label}}}"
                if row_index == 0
                else ""
            )
            metric_values = [
                format_metric(
                    row[column],
                    bold=bool(
                        not pd.isna(row[column])
                        and float(row[column]) == maximums[column]
                    ),
                )
                for column in METRIC_COLUMNS
            ]
            rows.append(
                " & ".join(
                    [
                        dataset_cell,
                        STRATEGY_LABELS[row["strategy"]],
                        *(format_count(row[column]) for column in COUNT_COLUMNS),
                        *metric_values,
                    ]
                )
                + r" \\"
            )
        dataset_blocks.append("\n".join(rows))

    body = "\n\\midrule\n".join(dataset_blocks)
    return rf"""\begin{{tabular}}{{llrrrrrrrr}}
\toprule
\textbf{{Dataset}} & \textbf{{Strategy}} & \textbf{{TP}} & \textbf{{FP}} &
\textbf{{FN}} & \textbf{{Precision}} & \textbf{{Recall}} & \textbf{{F1}} &
\textbf{{MAP}} & \textbf{{AUC}} \\
\midrule
{body}
\bottomrule
\end{{tabular}}
"""


def main(argv: list[str] | None = None) -> Path:
    args = build_parser().parse_args(argv)
    project_directory = Path(args.project_directory)
    paths = resolve_experiment_paths(args.workspace_directory, args.experiment_name)
    input_file = (
        paths.workspace_directory / "t2p_link_overall_metric.csv"
        if args.input_file is None
        else resolve_path(project_directory, args.input_file, Path())
    )
    output_file = resolve_output_file(
        project_directory,
        paths.experiment_directory,
        args.output_directory,
        args.output_file,
        DEFAULT_OUTPUT,
    )
    _, _, selected_strategies = resolve_experiment_filters(strategies=args.strategies)
    if not selected_strategies:
        raise ValueError("At least one strategy is required via --strategies or ME_STRATEGIES.")
    if not input_file.exists():
        raise FileNotFoundError(f"T2P link metric CSV not found: {input_file}")

    metric_df = pd.read_csv(input_file)
    table_df = select_average_rows(metric_df, selected_strategies)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(render_latex_table(table_df), encoding="utf-8")
    print(f"Wrote T2P link metric table: {output_file}")
    return output_file


if __name__ == "__main__":
    main()
