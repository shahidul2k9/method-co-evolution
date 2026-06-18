from __future__ import annotations

import os
import warnings

import cliffs_delta
import pandas as pd
from scipy.stats import wilcoxon

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
from ptc.generator.run_stats import GenerationStats, record_written_csv, should_generate
from ptc.generator.t2p_test_smell_prevalence import ALL_SMELLS, OUTPUT_FILE_NAME
from ptc.generator.t2p_test_smell_revision import (
    CHANGE_COLUMNS,
    REVISION_GROUP_1,
    REVISION_GROUP_3,
    REVISION_GROUP_ORDER,
    normalize_revision_group,
)

OUTPUT_FILE = "t2p-test-smell-prevalence-wilcoxon-srt.csv"
DEFAULT_REVISION_GROUPS = [REVISION_GROUP_1, REVISION_GROUP_3]
STAT_COLUMNS = [
    "groups",
    "strategy",
    "tool",
    "smell_detector",
    "change",
    "loc_group",
    "size",
    "g1_size",
    "g2_size",
    "w_stat",
    "w_p",
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
        "Compare paired test-smell prevalence distributions between two revision groups.",
        include_revision_types=True,
        include_smell_detector=True,
        include_projects=False,
        include_replace=True,
        projects_help=None,
        strategies_help="Comma-separated strategy names to include. Defaults to ME_STRATEGIES.",
        revision_types_help="Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
    )
    parser.add_argument(
        "--revision-groups",
        dest="revision_groups",
        type=str,
        default=",".join(DEFAULT_REVISION_GROUPS),
        help="Exactly two comma-separated revision groups to compare. Order is preserved.",
    )
    return parser


def selected_two_revision_groups(value: str | list[str] | None) -> list[str]:
    selected = parse_name_list(value)
    if selected is None:
        selected = list(DEFAULT_REVISION_GROUPS)
    selected = [normalize_revision_group(group) for group in selected]
    known_groups = set(REVISION_GROUP_ORDER)
    unknown = [group for group in selected if group not in known_groups]
    if unknown:
        raise ValueError(f"Unknown revision group(s): {', '.join(unknown)}")
    if len(selected) != 2:
        raise ValueError("--revision-groups must include exactly two groups.")
    return selected


def paired_smell_values(pair_df: pd.DataFrame, group1: str, group2: str) -> pd.DataFrame:
    group_column = "rg_group" if "rg_group" in pair_df.columns else ("group" if "group" in pair_df.columns else "revision_group")
    g1_df = pair_df[pair_df[group_column] == group1][["smell", "smell_n"]].copy()
    g2_df = pair_df[pair_df[group_column] == group2][["smell", "smell_n"]].copy()
    g1_df["g1_smell_n"] = pd.to_numeric(g1_df["smell_n"], errors="coerce")
    g2_df["g2_smell_n"] = pd.to_numeric(g2_df["smell_n"], errors="coerce")
    paired_df = g1_df[["smell", "g1_smell_n"]].merge(
        g2_df[["smell", "g2_smell_n"]],
        on="smell",
        how="inner",
    )
    return paired_df.dropna(subset=["g1_smell_n", "g2_smell_n"])


def wilcoxon_signed_rank(g1_values: pd.Series, g2_values: pd.Series) -> tuple[float, float]:
    diff = g1_values.to_numpy() - g2_values.to_numpy()
    if (diff != 0).sum() == 0:
        return 0.0, 1.0
    stat, p_value = wilcoxon(
        g1_values,
        g2_values,
        alternative="two-sided",
        zero_method="wilcox",
    )
    return float(stat), float(p_value)


def build_stat_row(
    prevalence_df: pd.DataFrame,
    *,
    group1: str,
    group2: str,
    strategy: str,
    tool: str,
    smell_detector: str,
    change: str,
    loc_group: str = "ALL",
) -> dict | None:
    pair_df = prevalence_df[
        (prevalence_df["strategy"] == strategy)
        & (prevalence_df["tool"] == tool)
        & (prevalence_df["smell_detector"] == smell_detector)
        & (prevalence_df["change"] == change)
        & (prevalence_df["loc_group"] == loc_group)
        & (prevalence_df["smell"] != ALL_SMELLS)
    ].copy()
    paired_df = paired_smell_values(pair_df, group1, group2)
    if paired_df.empty:
        return None

    g1_values = paired_df["g1_smell_n"]
    g2_values = paired_df["g2_smell_n"]
    w_stat, w_p = wilcoxon_signed_rank(g1_values, g2_values)
    d_value, effect_size = cliffs_delta.cliffs_delta(g1_values, g2_values)
    d_sign = "+" if d_value > 0 else ("-" if d_value < 0 else "=")
    marker_values = {column: "" for column in SIZE_MARKER_COLUMNS.values()}
    marker_column = SIZE_MARKER_COLUMNS.get(effect_size)
    if marker_column is not None:
        marker_values[marker_column] = "x"

    return {
        "groups": f"{group1},{group2}",
        "strategy": strategy,
        "tool": tool,
        "smell_detector": smell_detector,
        "change": change,
        "loc_group": loc_group,
        "size": len(paired_df),
        "g1_size": len(paired_df),
        "g2_size": len(paired_df),
        "w_stat": round(w_stat, 2),
        "w_p": round(w_p, 2),
        "d_value": round(d_value, 2),
        "d_sign": d_sign,
        "effect_size": effect_size,
        **marker_values,
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("t2p_test_smell_prevalence_wilcoxon_srt")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    input_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    output_file = experiment_directory / "aggregate" / OUTPUT_FILE
    if not input_file.exists():
        warnings.warn(f"File not found, skipping: {input_file}")
        stats.skipped_missing_input += 1
        stats.print_summary()
        return
    if not should_generate(output_file, replace=args.replace, label=OUTPUT_FILE, stats=stats):
        stats.print_summary()
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
        group_column = "rg_group" if "rg_group" in prevalence_df.columns else (
            "group" if "group" in prevalence_df.columns else "revision_group"
        )
        if "loc_group" not in prevalence_df.columns:
            prevalence_df["loc_group"] = "ALL"
        frame = prevalence_df[
            (prevalence_df["smell_detector"] == smell_detector)
            & (prevalence_df[group_column].isin([group1, group2]))
        ].copy()
        if selected_tools is not None:
            frame = frame[frame["tool"].isin(selected_tools)]
        if selected_strategies is not None:
            frame = frame[frame["strategy"].isin(selected_strategies)]
        if selected_changes:
            frame = frame[frame["change"].isin(selected_changes)]

        grouping = frame[["strategy", "tool", "smell_detector", "change", "loc_group"]].drop_duplicates()
        for row in grouping.itertuples(index=False):
            stat_row = build_stat_row(
                frame,
                group1=group1,
                group2=group2,
                strategy=row.strategy,
                tool=row.tool,
                smell_detector=row.smell_detector,
                change=row.change,
                loc_group=row.loc_group,
            )
            if stat_row is not None:
                rows.append(stat_row)

    os.makedirs(output_file.parent, exist_ok=True)
    output_df = pd.DataFrame(rows, columns=STAT_COLUMNS)
    if not output_df.empty:
        output_df = output_df.sort_values(["strategy", "tool", "smell_detector", "change", "loc_group"]).reset_index(drop=True)
    output_df.to_csv(output_file, index=False)
    record_written_csv(output_file, stats, rows=len(output_df))
    print(f"Wrote {output_file}")
    stats.print_summary()


if __name__ == "__main__":
    main()
