from __future__ import annotations

import os
import warnings

import pandas as pd

from mhc.command_util import (
    build_experiment_parser,
    parse_name_list,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_revision_types,
    resolve_smell_detector,
    select_revision_columns,
)
from ptc.generator.artifact_revision_mww import SIZE_MARKER_COLUMNS
from ptc.generator.t2p_test_smell_prevalence import ALL_SMELLS, OUTPUT_FILE_NAME
from ptc.generator.t2p_test_smell_revision import CHANGE_COLUMNS, REVISION_GROUP_ORDER
from ptc.plot_util import man_utest

OUTPUT_FILE = "test-smell-prevalence-mww.csv"
STAT_COLUMNS = [
    "groups",
    "strategy",
    "tool",
    "smell_detector",
    "change",
    "size",
    "g1_size",
    "g2_size",
    "mww_u1",
    "mww_u2",
    "mww_p",
    "d_value",
    "d_sign",
    "effect_size",
    "N",
    "S",
    "M",
    "L",
]


def build_parser():
    parser = build_experiment_parser(
        "Compare test-smell prevalence distributions between two revision groups.",
        include_revision_types=True,
        include_smell_detector=True,
        include_projects=False,
        projects_help=None,
        strategies_help="Comma-separated strategy names to include. Defaults to ME_STRATEGIES.",
        revision_types_help="Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
    )
    parser.add_argument(
        "--revision-groups",
        dest="revision_groups",
        type=str,
        default=",".join(REVISION_GROUP_ORDER[:2]),
        help="Exactly two comma-separated revision groups to compare. Order is preserved.",
    )
    return parser


def selected_two_revision_groups(value: str | list[str] | None) -> list[str]:
    selected = parse_name_list(value)
    if selected is None:
        selected = list(REVISION_GROUP_ORDER[:2])
    known_groups = set(REVISION_GROUP_ORDER)
    unknown = [group for group in selected if group not in known_groups]
    if unknown:
        raise ValueError(f"Unknown revision group(s): {', '.join(unknown)}")
    if len(selected) != 2:
        raise ValueError("--revision-groups must include exactly two groups.")
    return selected


def build_stat_row(
    prevalence_df: pd.DataFrame,
    *,
    group1: str,
    group2: str,
    strategy: str,
    tool: str,
    smell_detector: str,
    change: str,
) -> dict | None:
    pair_df = prevalence_df[
        (prevalence_df["strategy"] == strategy)
        & (prevalence_df["tool"] == tool)
        & (prevalence_df["smell_detector"] == smell_detector)
        & (prevalence_df["change"] == change)
        & (prevalence_df["smell"] != ALL_SMELLS)
    ].copy()
    g1_values = pd.to_numeric(
        pair_df[pair_df["revision_group"] == group1]["smell_n"],
        errors="coerce",
    ).dropna()
    g2_values = pd.to_numeric(
        pair_df[pair_df["revision_group"] == group2]["smell_n"],
        errors="coerce",
    ).dropna()
    if g1_values.empty or g2_values.empty:
        return None

    mww_u1, mww_p, d_value, mww_size = man_utest(g1_values, g2_values)
    mww_u2 = len(g1_values) * len(g2_values) - mww_u1
    d_sign = "+" if d_value > 0 else ("-" if d_value < 0 else "=")
    marker_values = {column: "" for column in SIZE_MARKER_COLUMNS.values()}
    marker_column = SIZE_MARKER_COLUMNS.get(mww_size)
    if marker_column is not None:
        marker_values[marker_column] = "x"

    return {
        "groups": f"{group1},{group2}",
        "strategy": strategy,
        "tool": tool,
        "smell_detector": smell_detector,
        "change": change,
        "size": len(pair_df),
        "g1_size": len(g1_values),
        "g2_size": len(g2_values),
        "mww_u1": round(mww_u1, 2),
        "mww_u2": round(mww_u2, 2),
        "mww_p": round(mww_p, 2),
        "d_value": round(d_value, 2),
        "d_sign": d_sign,
        "effect_size": mww_size,
        **marker_values,
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    input_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    if not input_file.exists():
        warnings.warn(f"File not found, skipping: {input_file}")
        return

    selected_tools, _, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        strategies=args.strategies,
    )
    selected_changes = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    group1, group2 = selected_two_revision_groups(args.revision_groups)

    prevalence_df = pd.read_csv(input_file, keep_default_na=False, na_filter=False)
    if prevalence_df.empty:
        rows = []
    else:
        rows = []
        frame = prevalence_df[
            (prevalence_df["smell_detector"] == smell_detector)
            & (prevalence_df["revision_group"].isin([group1, group2]))
        ].copy()
        if selected_tools is not None:
            frame = frame[frame["tool"].isin(selected_tools)]
        if selected_strategies is not None:
            frame = frame[frame["strategy"].isin(selected_strategies)]
        if selected_changes:
            frame = frame[frame["change"].isin(selected_changes)]

        grouping = frame[["strategy", "tool", "smell_detector", "change"]].drop_duplicates()
        for row in grouping.itertuples(index=False):
            stat_row = build_stat_row(
                frame,
                group1=group1,
                group2=group2,
                strategy=row.strategy,
                tool=row.tool,
                smell_detector=row.smell_detector,
                change=row.change,
            )
            if stat_row is not None:
                rows.append(stat_row)

    output_file = experiment_directory / "aggregate" / OUTPUT_FILE
    os.makedirs(output_file.parent, exist_ok=True)
    output_df = pd.DataFrame(rows, columns=STAT_COLUMNS)
    if not output_df.empty:
        output_df = output_df.sort_values(["strategy", "tool", "smell_detector", "change"]).reset_index(drop=True)
    output_df.to_csv(output_file, index=False)
    print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
