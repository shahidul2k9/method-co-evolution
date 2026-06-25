from __future__ import annotations

import math
import os
import warnings
from pathlib import Path

import pandas as pd

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    non_negative_int,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_min_t2p_links,
    resolve_revision_types,
    resolve_smell_detector,
    select_named_items,
    select_revision_columns,
)
from ptc.generator.run_stats import GenerationStats, should_generate
from ptc.generator.t2p_test_smell_association import (
    ALPHA,
    DEFAULT_CHANGE,
    OUTPUT_FILE_NAME as ASSOCIATION_OUTPUT_FILE_NAME,
    benjamini_hochberg,
    comparison_unique_method_frame,
    difference_interval,
    pooled_statistics,
    selected_revision_group_pairs,
)
from ptc.generator.t2p_test_smell_loc_group import valid_loc
from ptc.generator.t2p_test_smell_prevalence import (
    PSEUDO_SMELLS,
    load_generated_frames,
    load_smell_frames,
    split_smells,
)
from ptc.generator.t2p_test_smell_revision import (
    CHANGE_COLUMNS,
    OUTPUT_DIRECTORY_NAME,
    REVISION_GROUP_1,
    REVISION_GROUP_2,
    REVISION_GROUP_3,
    normalize_revision_group,
)

OUTPUT_FILE_NAME = "t2p-test-smell-size-control-association.csv"
DEFAULT_REVISION_GROUP_PAIRS = f"{REVISION_GROUP_3},{REVISION_GROUP_1};{REVISION_GROUP_2},{REVISION_GROUP_1}"
COMBINED_TOP_SMELLS = "TOP5"
COMBINED_ROBUST_SMELLS = "ROBUST"
CONTROL_SIZE_GROUPS = ["Small", "Medium", "Large"]
CONTROL_SIZE_LABELS = {
    "Small": "Small (1-29 LOC)",
    "Medium": "Medium (30-60 LOC)",
    "Large": "Large (61+ LOC)",
}
OUTPUT_COLUMNS = [
    "strategy",
    "tool",
    "smell_detector",
    "change",
    "control_group",
    "control_group_label",
    "baseline_group",
    "focal_group",
    "smell",
    "smell_rank",
    "baseline_n",
    "baseline_smell_n",
    "baseline_percent",
    "focal_n",
    "focal_smell_n",
    "focal_percent",
    "difference_pp",
    "difference_ci_low",
    "difference_ci_high",
    "odds_ratio",
    "odds_ratio_ci_low",
    "odds_ratio_ci_high",
    "fisher_p",
    "fisher_p_adjusted",
    "significant",
]


def build_parser():
    parser = build_experiment_parser(
        "Generate LOC-controlled top-smell association rows for RQ4.",
        include_revision_types=True,
        include_smell_detector=True,
        include_replace=True,
        projects_help="Comma-separated project names to include. Defaults to ME_PROJECTS.",
        strategies_help="Comma-separated strategy names to include. Defaults to ME_STRATEGIES.",
        revision_types_help="Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
    )
    parser.add_argument(
        "--revision-group-pairs",
        default=DEFAULT_REVISION_GROUP_PAIRS,
        help=(
            "Semicolon-separated focal,baseline revision-group pairs. "
            f"Defaults to {DEFAULT_REVISION_GROUP_PAIRS}."
        ),
    )
    parser.add_argument("--top-n-smells", type=non_negative_int, default=5)
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum generated linked rows required before including a project.",
    )
    return parser


def fixed_control_group(loc: int) -> str:
    if loc < 30:
        return "Small"
    if loc <= 60:
        return "Medium"
    return "Large"


def fixed_control_group_frame(smell_frames: list[pd.DataFrame]) -> pd.DataFrame:
    loc_by_url: dict[str, int] = {}
    for smell_df in smell_frames:
        if not {"url", "loc"}.issubset(smell_df.columns):
            continue
        for row in smell_df[["url", "loc"]].itertuples(index=False):
            url = str(row.url or "")
            if not url or url in loc_by_url:
                continue
            loc = valid_loc(row.loc)
            if loc is not None:
                loc_by_url[url] = loc
    rows = [
        {
            "from_url": url,
            "loc": loc,
            "control_group": fixed_control_group(loc),
        }
        for url, loc in loc_by_url.items()
    ]
    return pd.DataFrame(rows, columns=["from_url", "loc", "control_group"])


def association_top_smells(
    association_frame: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    revision_type: str,
    focal_group: str,
    baseline_group: str,
    top_n: int,
) -> list[tuple[str, float]]:
    required_columns = {
        "strategy",
        "tool",
        "smell_detector",
        "change",
        "baseline_group",
        "focal_group",
        "smell",
        "difference_pp",
    }
    if not required_columns.issubset(association_frame.columns):
        return []
    subset = association_frame[
        (association_frame["strategy"] == strategy)
        & (association_frame["tool"] == tool)
        & (association_frame["smell_detector"] == smell_detector)
        & (association_frame["change"] == revision_type)
        & (association_frame["focal_group"] == normalize_revision_group(focal_group))
        & (association_frame["baseline_group"] == normalize_revision_group(baseline_group))
        & (~association_frame["smell"].isin([*PSEUDO_SMELLS, COMBINED_TOP_SMELLS, COMBINED_ROBUST_SMELLS]))
    ].copy()
    if "loc_group" in subset.columns:
        subset = subset[subset["loc_group"] == "ALL"].copy()
    if subset.empty:
        return []
    subset["difference_pp"] = pd.to_numeric(subset["difference_pp"], errors="coerce")
    subset = subset.dropna(subset=["difference_pp"]).sort_values(["difference_pp", "smell"], ascending=[False, True])
    return [(str(row.smell), float(row.difference_pp)) for row in subset.head(top_n).itertuples(index=False)]


def top_smells_from_association(
    association_frame: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    revision_type: str,
    top_n: int,
    focal_group: str = REVISION_GROUP_3,
    baseline_group: str = REVISION_GROUP_1,
) -> list[str]:
    return [
        smell
        for smell, _ in association_top_smells(
            association_frame,
            strategy=strategy,
            tool=tool,
            smell_detector=smell_detector,
            revision_type=revision_type,
            focal_group=focal_group,
            baseline_group=baseline_group,
            top_n=top_n,
        )
    ]


def robust_significant_smells_from_association(
    association_frame: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    revision_type: str,
    focal_group: str = REVISION_GROUP_3,
    baseline_group: str = REVISION_GROUP_1,
    alpha: float = ALPHA,
) -> list[str]:
    required_columns = {
        "strategy",
        "tool",
        "smell_detector",
        "change",
        "baseline_group",
        "focal_group",
        "smell",
        "difference_pp",
        "fisher_p_adjusted",
        "mh_p_adjusted",
    }
    if not required_columns.issubset(association_frame.columns):
        return []
    subset = association_frame[
        (association_frame["strategy"] == strategy)
        & (association_frame["tool"] == tool)
        & (association_frame["smell_detector"] == smell_detector)
        & (association_frame["change"] == revision_type)
        & (association_frame["focal_group"] == normalize_revision_group(focal_group))
        & (association_frame["baseline_group"] == normalize_revision_group(baseline_group))
        & (~association_frame["smell"].isin([*PSEUDO_SMELLS, COMBINED_TOP_SMELLS, COMBINED_ROBUST_SMELLS]))
    ].copy()
    if "loc_group" in subset.columns:
        subset = subset[subset["loc_group"] == "ALL"].copy()
    if subset.empty:
        return []
    subset["difference_pp"] = pd.to_numeric(subset["difference_pp"], errors="coerce")
    subset["fisher_p_adjusted"] = pd.to_numeric(subset["fisher_p_adjusted"], errors="coerce")
    subset["mh_p_adjusted"] = pd.to_numeric(subset["mh_p_adjusted"], errors="coerce")
    subset = subset[
        (subset["fisher_p_adjusted"] < alpha)
        & (subset["mh_p_adjusted"] < alpha)
        & subset["difference_pp"].notna()
    ]
    if subset.empty:
        return []
    subset = subset.sort_values(["difference_pp", "smell"], ascending=[False, True])
    return subset["smell"].astype(str).tolist()


def smell_differences(
    group_df: pd.DataFrame,
    *,
    revision_type: str,
    focal_group: str,
    baseline_group: str,
) -> list[tuple[str, float]]:
    group_column = f"rg_{revision_type}"
    focal = group_df[group_df[group_column] == focal_group]
    baseline = group_df[group_df[group_column] == baseline_group]
    if focal.empty or baseline.empty:
        return []

    smell_types = sorted(
        {
            smell
            for value in group_df.get("smells", pd.Series(dtype=str))
            for smell in split_smells(value)
        }
    )
    rows = []
    for smell in smell_types:
        focal_count = int(focal["smells"].map(lambda value: smell in split_smells(value)).sum())
        baseline_count = int(baseline["smells"].map(lambda value: smell in split_smells(value)).sum())
        focal_percent = focal_count / len(focal) * 100
        baseline_percent = baseline_count / len(baseline) * 100
        rows.append((smell, focal_percent - baseline_percent))
    return sorted(rows, key=lambda item: (-item[1], item[0]))


def top_smells_by_primary_difference(
    unique: pd.DataFrame,
    *,
    revision_type: str,
    top_n: int,
    focal_group: str = REVISION_GROUP_3,
    baseline_group: str = REVISION_GROUP_1,
) -> list[str]:
    return [
        smell
        for smell, _ in smell_differences(
            unique,
            revision_type=revision_type,
            focal_group=focal_group,
            baseline_group=baseline_group,
        )[:top_n]
    ]


def top_smell_union_by_control_and_pair(
    unique: pd.DataFrame,
    *,
    revision_type: str,
    revision_group_pairs: list[tuple[str, str]],
    top_n: int,
) -> list[str]:
    first_rank: dict[str, int] = {}
    best_difference: dict[str, float] = {}
    for control_group in CONTROL_SIZE_GROUPS:
        control_df = unique[unique["control_group"] == control_group].copy()
        for focal_group, baseline_group in revision_group_pairs:
            ranked = smell_differences(
                control_df,
                revision_type=revision_type,
                focal_group=focal_group,
                baseline_group=baseline_group,
            )[:top_n]
            for rank, (smell, difference) in enumerate(ranked, start=1):
                first_rank[smell] = min(first_rank.get(smell, rank), rank)
                best_difference[smell] = max(best_difference.get(smell, -math.inf), difference)
    return sorted(first_rank, key=lambda smell: (first_rank[smell], -best_difference[smell], smell))


def controlled_association_rows(
    frame: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    revision_type: str = DEFAULT_CHANGE,
    revision_group_pairs: list[tuple[str, str]] | None = None,
    control_groups: pd.DataFrame | None = None,
    top_smells: list[str] | None = None,
) -> list[dict]:
    revision_group_pairs = revision_group_pairs or selected_revision_group_pairs(DEFAULT_REVISION_GROUP_PAIRS)
    top_smells = list(top_smells or [])
    if not top_smells:
        return []
    if control_groups is None or control_groups.empty:
        return []

    rows = []
    for focal_group, baseline_group in revision_group_pairs:
        unique = comparison_unique_method_frame(
            frame,
            revision_type,
            baseline_group=baseline_group,
            focal_group=focal_group,
        )
        group_column = f"rg_{revision_type}"
        if unique.empty or group_column not in unique.columns:
            continue
        unique = unique.merge(control_groups[["from_url", "control_group"]], on="from_url", how="inner")
        if unique.empty:
            continue
        for control_group in CONTROL_SIZE_GROUPS:
            control_df = unique[unique["control_group"] == control_group].copy()
            rows.extend(
                _controlled_rows_for_pair(
                    control_df,
                    top_smells,
                    strategy=strategy,
                    tool=tool,
                    smell_detector=smell_detector,
                    revision_type=revision_type,
                    control_group=control_group,
                    focal_group=focal_group,
                    baseline_group=baseline_group,
                )
            )
    return rows


def _controlled_rows_for_pair(
    control_df: pd.DataFrame,
    top_smells: list[str],
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    revision_type: str,
    control_group: str,
    focal_group: str,
    baseline_group: str,
) -> list[dict]:
    group_column = f"rg_{revision_type}"
    focal = control_df[control_df[group_column] == focal_group]
    baseline = control_df[control_df[group_column] == baseline_group]
    if focal.empty or baseline.empty:
        return []

    rows = []
    smell_specs = [(smell_rank, smell, [smell]) for smell_rank, smell in enumerate(top_smells, start=1)]
    smell_specs.append((len(top_smells) + 1, COMBINED_ROBUST_SMELLS, top_smells))
    for smell_rank, smell, matched_smells in smell_specs:
        has_smell = lambda value: bool(set(split_smells(value)).intersection(matched_smells))
        focal_smell_n = int(focal["smells"].map(has_smell).sum())
        baseline_smell_n = int(baseline["smells"].map(has_smell).sum())
        focal_percent = focal_smell_n / len(focal) * 100
        baseline_percent = baseline_smell_n / len(baseline) * 100
        ci_low, ci_high = difference_interval(focal_smell_n, len(focal), baseline_smell_n, len(baseline))
        ratio, ratio_low, ratio_high, fisher_p = pooled_statistics(
            focal_smell_n,
            len(focal),
            baseline_smell_n,
            len(baseline),
        )
        rows.append(
            {
                "strategy": strategy,
                "tool": tool,
                "smell_detector": smell_detector,
                "change": revision_type,
                "control_group": control_group,
                "control_group_label": CONTROL_SIZE_LABELS[control_group],
                "baseline_group": normalize_revision_group(baseline_group),
                "focal_group": normalize_revision_group(focal_group),
                "smell": smell,
                "smell_rank": smell_rank,
                "baseline_n": len(baseline),
                "baseline_smell_n": baseline_smell_n,
                "baseline_percent": round(baseline_percent, 2),
                "focal_n": len(focal),
                "focal_smell_n": focal_smell_n,
                "focal_percent": round(focal_percent, 2),
                "difference_pp": round(focal_percent - baseline_percent, 2),
                "difference_ci_low": round(ci_low, 2),
                "difference_ci_high": round(ci_high, 2),
                "odds_ratio": round(ratio, 2),
                "odds_ratio_ci_low": round(ratio_low, 2),
                "odds_ratio_ci_high": round(ratio_high, 2),
                "fisher_p": fisher_p,
                "fisher_p_adjusted": math.nan,
                "significant": "",
            }
        )

    adjusted = benjamini_hochberg([row["fisher_p"] for row in rows])
    for row, adjusted_p in zip(rows, adjusted):
        row["fisher_p_adjusted"] = adjusted_p
        row["significant"] = "x" if adjusted_p < ALPHA else ""
    return rows


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("t2p_test_smell_size_control_association")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    output_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    if not should_generate(output_file, replace=args.replace, label=OUTPUT_FILE_NAME, stats=stats):
        stats.print_summary()
        return

    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_types = select_revision_columns(
        CHANGE_COLUMNS,
        resolve_revision_types(args.revision_types),
        preferred_order=CHANGE_COLUMNS,
        include_extra=False,
    )
    revision_group_pairs = selected_revision_group_pairs(args.revision_group_pairs)
    association_file = experiment_directory / "aggregate" / ASSOCIATION_OUTPUT_FILE_NAME
    if not association_file.exists():
        warnings.warn(
            f"File not found, skipping: {association_file}. "
            "Run ptc.generator.t2p_test_smell_association first."
        )
        stats.skipped_missing_input += 1
        stats.print_summary()
        return
    association_frame = pd.read_csv(association_file, keep_default_na=False)
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
        strict=False,
    )
    for strategy in strategies:
        control_groups = fixed_control_group_frame(
            load_smell_frames(experiment_directory, smell_detector, strategy, selected_projects)
        )
        tools = select_named_items(
            util.sorted_directory_names(generated_dir / strategy),
            selected_tools,
            item_label="tool",
        )
        for tool in tools:
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
            for revision_type in revision_types:
                for focal_group, baseline_group in revision_group_pairs:
                    top_smells = robust_significant_smells_from_association(
                        association_frame,
                        strategy=strategy,
                        tool=tool,
                        smell_detector=smell_detector,
                        revision_type=revision_type,
                        focal_group=focal_group,
                        baseline_group=baseline_group,
                    )
                    if not top_smells:
                        warnings.warn(
                            "No robust-significant association smells found for "
                            f"{strategy}/{tool}/{smell_detector}/{revision_type}/{focal_group}-{baseline_group}, "
                            "skipping."
                        )
                        continue
                    print(
                        "Size-control robust significant smells "
                        f"({strategy}/{tool}/{smell_detector}/{revision_type}/{focal_group}-{baseline_group}): "
                        f"{', '.join(top_smells)}"
                    )
                    rows.extend(
                        controlled_association_rows(
                            frame,
                            strategy=strategy,
                            tool=tool,
                            smell_detector=smell_detector,
                            revision_type=revision_type,
                            revision_group_pairs=[(focal_group, baseline_group)],
                            control_groups=control_groups,
                            top_smells=top_smells,
                        )
                    )

    os.makedirs(output_file.parent, exist_ok=True)
    output_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if not output_df.empty:
        output_df["_control_order"] = output_df["control_group"].map(
            {group: index for index, group in enumerate(CONTROL_SIZE_GROUPS)}
        )
        output_df = (
            output_df.sort_values(
                ["strategy", "tool", "smell_detector", "change", "_control_order", "smell_rank", "focal_group"]
            )
            .drop(columns=["_control_order"])
            .reset_index(drop=True)
        )
    output_df.to_csv(output_file, index=False)
    if output_df.empty:
        stats.record_empty_output()
    stats.record_write(len(output_df))
    print(f"Wrote {output_file}")
    stats.print_summary()


if __name__ == "__main__":
    main()
