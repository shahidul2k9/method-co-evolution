from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from mhc.command_util import build_experiment_parser, resolve_experiment_paths
from ptc.plot.method_history_runtime_table import escape_latex, resolve_output_file, resolve_path


DEFAULT_STATISTICS_INPUT = Path("data") / "main" / "method-call-statistics.csv"
DEFAULT_GROUND_TRUTH_DIRECTORY = Path("data") / "t2plinker" / "t2p-ground-truth"
DEFAULT_OUTPUT = Path("figure") / "t2plinker-ground-truth-statistics-table.tex"
STATISTICS_COLUMNS = {"project", "prod_methods", "tests"}
GROUND_TRUTH_COLUMNS = {"from_url", "to_url", "candidate", "label", "tags"}
TABLE_COLUMNS = [
    "project",
    "prod_methods",
    "tests",
    "method_calls",
    "median_method_calls",
    "ground_truth_links",
]
IMPLICIT_PRODUCTION_METHOD_TAG = "#implicit-production-method"


def build_parser():
    parser = build_experiment_parser(
        "Generate a LaTeX table summarizing T2PLinker ground-truth statistics.",
        include_tools=False,
        include_projects=False,
        include_strategies=False,
        include_project_directory=True,
        include_output_directory=True,
    )
    parser.add_argument(
        "--method-call-statistics-file",
        default=None,
        help="Defaults to <project-directory>/data/main/method-call-statistics.csv.",
    )
    parser.add_argument(
        "--ground-truth-directory",
        default=None,
        help="Defaults to <project-directory>/data/t2plinker/t2p-ground-truth.",
    )
    parser.add_argument(
        "--output-file",
        default=None,
        help=(
            "Generated LaTeX file. Relative paths resolve from the experiment directory. "
            "Defaults to its figure/t2plinker-ground-truth-statistics-table.tex."
        ),
    )
    return parser


def validate_columns(df: pd.DataFrame, required_columns: set[str], label: str) -> None:
    missing_columns = sorted(required_columns - set(df.columns))
    if missing_columns:
        raise ValueError(f"{label} CSV is missing required column(s): {', '.join(missing_columns)}")


def has_exact_tag(value: object, tag: str) -> bool:
    return tag in str(value).split()


def calculate_ground_truth_statistics(ground_truth_df: pd.DataFrame) -> dict[str, float | int]:
    validate_columns(ground_truth_df, GROUND_TRUTH_COLUMNS, "Ground-truth")
    pairs = ground_truth_df[["from_url", "to_url", "candidate", "label", "tags"]].copy()

    candidate = pd.to_numeric(pairs["candidate"], errors="coerce")
    eligible = pairs[
        candidate.eq(1)
        & ~pairs["tags"].map(lambda tags: has_exact_tag(tags, IMPLICIT_PRODUCTION_METHOD_TAG))
    ][["from_url", "to_url"]].drop_duplicates()

    tests = pairs["from_url"].drop_duplicates()
    calls_per_test = eligible.groupby("from_url")["to_url"].nunique().reindex(tests, fill_value=0)
    median_method_calls = float(calls_per_test.median()) if not calls_per_test.empty else np.nan

    label = pd.to_numeric(pairs["label"], errors="coerce")
    ground_truth_links = pairs[label.eq(1)][["from_url", "to_url"]].drop_duplicates()
    return {
        "method_calls": len(eligible),
        "median_method_calls": median_method_calls,
        "ground_truth_links": len(ground_truth_links),
    }


def build_statistics_table(
    method_statistics_df: pd.DataFrame,
    ground_truth_files: list[Path],
) -> pd.DataFrame:
    validate_columns(method_statistics_df, STATISTICS_COLUMNS, "Method-call statistics")
    if not ground_truth_files:
        raise ValueError("No ground-truth CSV files were found.")

    method_statistics = method_statistics_df.copy()
    method_statistics["_project_key"] = method_statistics["project"].astype(str).str.casefold()
    duplicate_projects = method_statistics.loc[
        method_statistics["_project_key"].duplicated(keep=False), "project"
    ].astype(str)
    if not duplicate_projects.empty:
        raise ValueError(
            "Method-call statistics contains duplicate case-insensitive project name(s): "
            + ", ".join(sorted(duplicate_projects.unique()))
        )
    method_statistics = method_statistics.set_index("_project_key")

    rows = []
    for ground_truth_file in sorted(ground_truth_files, key=lambda path: path.stem.casefold()):
        project = ground_truth_file.stem
        project_key = project.casefold()
        if project_key not in method_statistics.index:
            raise ValueError(f"Missing method-call statistics row for project {project!r}.")

        method_row = method_statistics.loc[project_key]
        ground_truth_df = pd.read_csv(
            ground_truth_file, keep_default_na=False, na_filter=False, low_memory=False
        )
        rows.append(
            {
                "project": project,
                "prod_methods": int(float(method_row["prod_methods"])),
                "tests": int(float(method_row["tests"])),
                **calculate_ground_truth_statistics(ground_truth_df),
            }
        )

    return pd.DataFrame(rows, columns=TABLE_COLUMNS)


def format_count(value: object) -> str:
    return f"{int(float(value)):,}"


def format_median(value: object) -> str:
    return "--" if pd.isna(value) else f"{float(value):,.1f}"


def render_latex_table(table_df: pd.DataFrame) -> str:
    rows = []
    for _, row in table_df.iterrows():
        rows.append(
            " & ".join(
                [
                    escape_latex(row["project"]),
                    format_count(row["prod_methods"]),
                    format_count(row["tests"]),
                    format_count(row["method_calls"]),
                    format_median(row["median_method_calls"]),
                    format_count(row["ground_truth_links"]),
                ]
            )
            + r" \\"
        )

    total_values = [
        "Total",
        format_count(table_df["prod_methods"].sum()),
        format_count(table_df["tests"].sum()),
        format_count(table_df["method_calls"].sum()),
        format_median(pd.to_numeric(table_df["median_method_calls"], errors="coerce").median()),
        format_count(table_df["ground_truth_links"].sum()),
    ]
    rows.extend(
        [
            r"\midrule",
            rf"\textbf{{{total_values[0]}}} & " + " & ".join(total_values[1:]) + r" \\",
        ]
    )
    body = "\n".join(rows)
    return rf"""\begin{{table*}}[t]
\centering
\caption{{T2PLinker ground-truth dataset statistics. Method calls exclude
non-candidates and implicit production methods.}}
\label{{tab:t2plinker-ground-truth-statistics}}
\begin{{tabular}}{{lrrrrr}}
\toprule
\textbf{{Project}} & \textbf{{Production Methods}} & \textbf{{Test Methods}} &
\textbf{{Method Calls}} & \textbf{{Median Method Calls}} &
\textbf{{Ground Truth Links}} \\
\midrule
{body}
\bottomrule
\end{{tabular}}
\end{{table*}}
"""


def main(argv: list[str] | None = None) -> Path:
    args = build_parser().parse_args(argv)
    project_directory = Path(args.project_directory)
    experiment_directory = resolve_experiment_paths(
        args.workspace_directory, args.experiment_name
    ).experiment_directory
    method_statistics_file = resolve_path(
        project_directory, args.method_call_statistics_file, DEFAULT_STATISTICS_INPUT
    )
    ground_truth_directory = resolve_path(
        project_directory, args.ground_truth_directory, DEFAULT_GROUND_TRUTH_DIRECTORY
    )
    output_file = resolve_output_file(
        project_directory,
        experiment_directory,
        args.output_directory,
        args.output_file,
        DEFAULT_OUTPUT,
    )

    if not method_statistics_file.exists():
        raise FileNotFoundError(f"Method-call statistics CSV not found: {method_statistics_file}")
    if not ground_truth_directory.is_dir():
        raise FileNotFoundError(f"Ground-truth directory not found: {ground_truth_directory}")

    method_statistics_df = pd.read_csv(method_statistics_file)
    table_df = build_statistics_table(method_statistics_df, list(ground_truth_directory.glob("*.csv")))
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(render_latex_table(table_df), encoding="utf-8")
    print(f"Wrote T2PLinker ground-truth statistics table: {output_file}")
    return output_file


if __name__ == "__main__":
    main()
