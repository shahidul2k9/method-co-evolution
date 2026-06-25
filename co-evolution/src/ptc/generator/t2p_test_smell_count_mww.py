from __future__ import annotations

import os
import warnings

import cliffs_delta
import pandas as pd
from scipy.stats import mannwhitneyu

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    list_csv_files,
    non_negative_int,
    parse_name_list,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_min_t2p_links,
    resolve_revision_types,
    resolve_smell_detector,
    select_named_items,
    select_revision_columns,
)
from ptc.generator.artifact_revision_mww import SIZE_MARKER_COLUMNS
from ptc.generator.run_stats import GenerationStats, record_written_csv, should_generate
from ptc.generator.t2p_test_smell_loc_group import SIZE_GROUPS
from ptc.generator.t2p_test_smell_prevalence import (
    ALL_LOC_GROUP,
    load_smell_frames,
    loc_group_frame,
    unique_method_frame,
)
from ptc.generator.t2p_test_smell_revision import (
    CHANGE_COLUMNS,
    OUTPUT_DIRECTORY_NAME,
    REVISION_GROUP_1,
    REVISION_GROUP_2,
    REVISION_GROUP_3,
    REVISION_GROUP_ORDER,
    normalize_revision_group,
    output_directory,
)
from ptc.plot.t2p_test_smell_boxplot import unique_smell_count

OUTPUT_FILE = "t2p-test-smell-count-mww.csv"
DEFAULT_REVISION_GROUP_PAIRS = [
    (REVISION_GROUP_3, REVISION_GROUP_1),
    (REVISION_GROUP_3, REVISION_GROUP_2),
]
COUNT_MWW_COLUMNS = [
    "comparison",
    "strategy",
    "tool",
    "smell_detector",
    "change",
    "loc_group",
    "size",
    "g1",
    "g2",
    "g1_size",
    "g2_size",
    "g1_median",
    "g2_median",
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
        "Compare method-level unique test-smell counts between revision groups.",
        include_revision_types=True,
        include_smell_detector=True,
        include_replace=True,
        projects_help="Comma-separated project names to include. Defaults to ME_PROJECTS.",
        strategies_help="Comma-separated strategy names to include. Defaults to ME_STRATEGIES.",
        revision_types_help="Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
    )
    parser.add_argument(
        "--revision-group-pairs",
        dest="revision_group_pairs",
        type=str,
        default=";".join(",".join(pair) for pair in DEFAULT_REVISION_GROUP_PAIRS),
        help='Semicolon-separated revision group pairs, for example "HTR,NTR;HTR,ATR".',
    )
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum generated linked test-production rows required before including a project. Defaults to ME_MIN_T2P_LINKS.",
    )
    return parser


def selected_revision_group_pairs(value: str | list[str] | None) -> list[tuple[str, str]]:
    if value is None:
        return list(DEFAULT_REVISION_GROUP_PAIRS)
    pair_values = value if isinstance(value, list) else [part.strip() for part in str(value).split(";") if part.strip()]
    pairs = []
    known_groups = set(REVISION_GROUP_ORDER)
    for pair_value in pair_values:
        groups = [normalize_revision_group(group) for group in (parse_name_list(pair_value) or [])]
        unknown = [group for group in groups if group not in known_groups]
        if unknown:
            raise ValueError(f"Unknown revision group(s): {', '.join(unknown)}")
        if len(groups) != 2:
            raise ValueError("--revision-group-pairs entries must each include exactly two groups.")
        pairs.append((groups[0], groups[1]))
    if not pairs:
        raise ValueError("--revision-group-pairs must include at least one pair.")
    return pairs


def load_generated_frames(
    experiment_directory,
    tool: str,
    strategy: str,
    smell_detector: str,
    selected_projects: list[str] | None,
    *,
    min_t2p_links: int,
) -> pd.DataFrame:
    input_dir = output_directory(experiment_directory, strategy, tool, smell_detector)
    csv_files = list_csv_files(input_dir, selected_projects, strict=False)
    frames = []
    for csv_file in csv_files:
        frame = pd.read_csv(csv_file, keep_default_na=False, na_filter=False)
        if len(frame) < min_t2p_links:
            warnings.warn(
                f"Skipping project={csv_file.stem}, tool={tool}, strategy={strategy}, "
                f"smell_detector={smell_detector}: "
                f"t2p_links={len(frame)} is below min_t2p_links={min_t2p_links}."
            )
            continue
        frames.append(frame)
    frames = [frame for frame in frames if not frame.empty]
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def method_count_frame(
    frame: pd.DataFrame,
    revision_type: str,
    revision_groups: list[str],
    *,
    loc_groups: pd.DataFrame | None = None,
) -> pd.DataFrame:
    group_column = f"rg_{revision_type}"
    if group_column not in frame.columns:
        return pd.DataFrame(columns=[*frame.columns, "unique_smell_count", "loc_group"])
    output = unique_method_frame(frame, revision_type, revision_groups)
    if output.empty:
        return output
    output = output.copy()
    output["unique_smell_count"] = output["smells"].map(unique_smell_count)
    if loc_groups is not None and not loc_groups.empty:
        output = output.merge(loc_groups[["from_url", "loc_group"]], on="from_url", how="left")
    elif "loc_group" not in output.columns:
        output["loc_group"] = ""
    return output


def _numeric_counts(frame: pd.DataFrame, group_column: str, group: str) -> pd.Series:
    return pd.to_numeric(frame[frame[group_column] == group]["unique_smell_count"], errors="coerce").dropna()


def build_stat_row(
    frame: pd.DataFrame,
    *,
    group1: str,
    group2: str,
    strategy: str,
    tool: str,
    smell_detector: str,
    change: str,
    loc_group: str = ALL_LOC_GROUP,
) -> dict | None:
    group_column = f"rg_{change}"
    if group_column not in frame.columns:
        return None
    pair_df = frame.copy()
    if loc_group != ALL_LOC_GROUP:
        pair_df = pair_df[pair_df["loc_group"] == loc_group].copy()
    g1_values = _numeric_counts(pair_df, group_column, group1)
    g2_values = _numeric_counts(pair_df, group_column, group2)
    if g1_values.empty or g2_values.empty:
        return None

    mww_u1, mww_p = mannwhitneyu(g1_values, g2_values, alternative="two-sided")
    mww_u2 = len(g1_values) * len(g2_values) - mww_u1
    d_value, effect_size = cliffs_delta.cliffs_delta(g1_values, g2_values)
    d_sign = "+" if d_value > 0 else ("-" if d_value < 0 else "=")
    marker_values = {column: "" for column in SIZE_MARKER_COLUMNS.values()}
    marker_column = SIZE_MARKER_COLUMNS.get(effect_size)
    if marker_column is not None:
        marker_values[marker_column] = "x"

    return {
        "comparison": f"{group1},{group2}",
        "strategy": strategy,
        "tool": tool,
        "smell_detector": smell_detector,
        "change": change,
        "loc_group": loc_group,
        "size": len(g1_values) + len(g2_values),
        "g1": group1,
        "g2": group2,
        "g1_size": len(g1_values),
        "g2_size": len(g2_values),
        "g1_median": round(float(g1_values.median()), 2),
        "g2_median": round(float(g2_values.median()), 2),
        "mww_u1": round(float(mww_u1), 2),
        "mww_u2": round(float(mww_u2), 2),
        "mww_p": round(float(mww_p), 2),
        "d_value": round(float(d_value), 2),
        "d_sign": d_sign,
        "effect_size": effect_size,
        **marker_values,
    }


def count_mww_rows(
    frame: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    revision_type: str,
    revision_group_pairs: list[tuple[str, str]],
    loc_groups: pd.DataFrame | None = None,
) -> list[dict]:
    selected_groups = list(dict.fromkeys(group for pair in revision_group_pairs for group in pair))
    method_df = method_count_frame(frame, revision_type, selected_groups, loc_groups=loc_groups)
    if method_df.empty:
        return []

    rows = []
    for group1, group2 in revision_group_pairs:
        for loc_group in [ALL_LOC_GROUP, *SIZE_GROUPS]:
            row = build_stat_row(
                method_df,
                group1=group1,
                group2=group2,
                strategy=strategy,
                tool=tool,
                smell_detector=smell_detector,
                change=revision_type,
                loc_group=loc_group,
            )
            if row is not None:
                rows.append(row)
    return rows


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("t2p_test_smell_count_mww")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    output_file = experiment_directory / "aggregate" / OUTPUT_FILE
    if not should_generate(output_file, replace=args.replace, label=OUTPUT_FILE, stats=stats):
        stats.print_summary()
        return

    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    selected_changes = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_group_pairs = selected_revision_group_pairs(args.revision_group_pairs)

    generated_dir = experiment_directory / OUTPUT_DIRECTORY_NAME
    if not generated_dir.exists():
        warnings.warn(f"Directory not found, skipping: {generated_dir}")
        stats.skipped_missing_input += 1
        stats.print_summary()
        return

    rows = []
    strategies = select_named_items(
        util.sorted_directory_names(generated_dir),
        selected_strategies,
        item_label="strategy",
    )
    for strategy in strategies:
        strategy_dir = generated_dir / strategy
        loc_groups = loc_group_frame(
            load_smell_frames(
                experiment_directory,
                smell_detector,
                strategy,
                selected_projects,
            )
        )
        tools = select_named_items(util.sorted_directory_names(strategy_dir), selected_tools, item_label="tool")
        for tool in tools:
            detector_dir = strategy_dir / tool / smell_detector
            if not detector_dir.exists():
                warnings.warn(f"Directory not found, skipping: {detector_dir}")
                continue
            frame = load_generated_frames(
                experiment_directory,
                tool,
                strategy,
                smell_detector,
                selected_projects,
                min_t2p_links=args.min_t2p_links,
            )
            if frame.empty:
                continue
            for revision_type in selected_changes:
                rows.extend(
                    count_mww_rows(
                        frame,
                        strategy=strategy,
                        tool=tool,
                        smell_detector=smell_detector,
                        revision_type=revision_type,
                        revision_group_pairs=revision_group_pairs,
                        loc_groups=loc_groups,
                    )
                )

    os.makedirs(output_file.parent, exist_ok=True)
    output_df = pd.DataFrame(rows, columns=COUNT_MWW_COLUMNS)
    if not output_df.empty:
        output_df = output_df.sort_values(["strategy", "tool", "smell_detector", "change", "comparison", "loc_group"]).reset_index(drop=True)
    output_df.to_csv(output_file, index=False)
    record_written_csv(output_file, stats, rows=len(output_df))
    print(f"Wrote {output_file}")
    stats.print_summary()


if __name__ == "__main__":
    main()
