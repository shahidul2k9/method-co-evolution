from __future__ import annotations

import math
import os
import warnings

import pandas as pd
from scipy.stats import chi2, fisher_exact
from scipy.stats.contingency import odds_ratio

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    non_negative_int,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_min_t2p_links,
    resolve_smell_detector,
    select_named_items,
)
from ptc.generator.t2p_test_smell_prevalence import (
    ALL_LOC_GROUP,
    ALL_SMELLS,
    load_generated_frames,
    load_smell_frames,
    loc_group_frame,
    smell_type_order,
    split_smells,
    unique_method_frame,
)
from ptc.generator.t2p_test_smell_loc_group import SIZE_GROUPS
from ptc.generator.t2p_test_smell_revision import (
    OUTPUT_DIRECTORY_NAME,
    REVISION_GROUP_1,
    REVISION_GROUP_2,
    REVISION_GROUP_3,
    normalize_revision_group,
)

OUTPUT_FILE_NAME = "t2p-test-smell-association.csv"
DEFAULT_CHANGE = "ch_diff"
ALPHA = 0.05
OUTPUT_COLUMNS = [
    "strategy",
    "tool",
    "smell_detector",
    "change",
    "loc_group",
    "baseline_group",
    "focal_group",
    "smell",
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
    "mh_odds_ratio",
    "mh_p",
    "mh_p_adjusted",
    "mh_significant",
    "sensitivity_agrees",
]


def output_revision_group(group: str) -> str:
    return normalize_revision_group(group)


def build_parser():
    parser = build_experiment_parser(
        "Analyze test-smell associations with recurrent revision-proneness.",
        include_revision_types=False,
        include_smell_detector=True,
        include_replace=True,
        projects_help="Comma-separated project names to include. Defaults to ME_PROJECTS.",
        strategies_help="Comma-separated strategy names to include. Defaults to ME_STRATEGIES.",
    )
    parser.add_argument("--change", default=DEFAULT_CHANGE, help=f"Revision change column. Defaults to {DEFAULT_CHANGE}.")
    parser.add_argument(
        "--revision-group-pairs",
        dest="revision_group_pairs",
        default=None,
        help=(
            "Semicolon-separated focal,baseline revision-group pairs. "
            "Example: HTR,NTR;MTR,NTR. Defaults to HTR,NTR."
        ),
    )
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum generated linked rows required before including a project.",
    )
    return parser


def selected_revision_group_pairs(value: str | None) -> list[tuple[str, str]]:
    if value is None or not str(value).strip():
        return [(REVISION_GROUP_3, REVISION_GROUP_1)]

    pairs = []
    for raw_pair in str(value).split(";"):
        names = [normalize_revision_group(part.strip()) for part in raw_pair.split(",") if part.strip()]
        if len(names) != 2:
            raise ValueError(
                "--revision-group-pairs entries must use focal,baseline format, "
                f"for example HTR,NTR;MTR,NTR: {raw_pair}"
            )
        unknown = [name for name in names if name not in {REVISION_GROUP_1, REVISION_GROUP_2, REVISION_GROUP_3}]
        if unknown:
            raise ValueError(f"Unknown revision group(s): {', '.join(unknown)}")
        pairs.append((names[0], names[1]))
    return pairs


def benjamini_hochberg(values: list[float]) -> list[float]:
    if not values:
        return []
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    adjusted = [1.0] * len(values)
    running = 1.0
    for reverse_rank, (index, value) in enumerate(reversed(ordered), start=1):
        rank = len(values) - reverse_rank + 1
        running = min(running, value * len(values) / rank)
        adjusted[index] = min(1.0, running)
    return adjusted


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total == 0:
        return math.nan, math.nan
    proportion = successes / total
    denominator = 1 + z * z / total
    center = (proportion + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(proportion * (1 - proportion) / total + z * z / (4 * total * total)) / denominator
    return center - margin, center + margin


def difference_interval(
    focal_successes: int,
    focal_total: int,
    baseline_successes: int,
    baseline_total: int,
) -> tuple[float, float]:
    focal_low, focal_high = wilson_interval(focal_successes, focal_total)
    baseline_low, baseline_high = wilson_interval(baseline_successes, baseline_total)
    return (focal_low - baseline_high) * 100, (focal_high - baseline_low) * 100


def pooled_statistics(
    focal_successes: int,
    focal_total: int,
    baseline_successes: int,
    baseline_total: int,
) -> tuple[float, float, float, float]:
    table = [
        [focal_successes, focal_total - focal_successes],
        [baseline_successes, baseline_total - baseline_successes],
    ]
    _, fisher_p = fisher_exact(table, alternative="two-sided")
    try:
        result = odds_ratio(table, kind="conditional")
        confidence = result.confidence_interval(confidence_level=0.95)
        return float(result.statistic), float(confidence.low), float(confidence.high), float(fisher_p)
    except ValueError:
        return math.nan, math.nan, math.nan, float(fisher_p)


def mantel_haenszel_statistics(
    frame: pd.DataFrame,
    smell: str,
    *,
    baseline_group: str,
    focal_group: str,
    group_column: str,
) -> tuple[float, float]:
    numerator = 0.0
    denominator = 0.0
    observed_minus_expected = 0.0
    variance = 0.0
    for _, project_df in frame.groupby("project", sort=False):
        focal = project_df[project_df[group_column] == focal_group]
        baseline = project_df[project_df[group_column] == baseline_group]
        if focal.empty or baseline.empty:
            continue
        has_smell = lambda value: bool(split_smells(value)) if smell == ALL_SMELLS else smell in split_smells(value)
        focal_has = int(focal["smells"].map(has_smell).sum())
        baseline_has = int(baseline["smells"].map(has_smell).sum())
        a = focal_has
        b = len(focal) - focal_has
        c = baseline_has
        d = len(baseline) - baseline_has
        total = a + b + c + d
        numerator += a * d / total
        denominator += b * c / total
        expected = (a + b) * (a + c) / total
        observed_minus_expected += a - expected
        if total > 1:
            variance += (a + b) * (c + d) * (a + c) * (b + d) / (total * total * (total - 1))

    mh_odds_ratio = numerator / denominator if denominator else math.inf if numerator else math.nan
    mh_p = float(chi2.sf(observed_minus_expected * observed_minus_expected / variance, 1)) if variance else 1.0
    return mh_odds_ratio, mh_p


def association_rows(
    frame: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    change: str = DEFAULT_CHANGE,
    baseline_group: str = REVISION_GROUP_1,
    focal_group: str = REVISION_GROUP_3,
    loc_groups: pd.DataFrame | None = None,
) -> list[dict]:
    group_column = f"rg_{change}"
    unique = unique_method_frame(frame, change, [baseline_group, focal_group])
    if unique.empty or group_column not in unique.columns:
        return []
    if loc_groups is not None and not loc_groups.empty:
        unique = unique.merge(loc_groups[["from_url", "loc_group"]], on="from_url", how="left")
    elif "loc_group" not in unique.columns:
        unique["loc_group"] = ""

    rows = _association_rows_for_frame(
        unique,
        strategy=strategy,
        tool=tool,
        smell_detector=smell_detector,
        change=change,
        loc_group=ALL_LOC_GROUP,
        baseline_group=baseline_group,
        focal_group=focal_group,
    )
    for loc_group_value in SIZE_GROUPS:
        loc_df = unique[unique["loc_group"] == loc_group_value].copy()
        rows.extend(
            _association_rows_for_frame(
                loc_df,
                strategy=strategy,
                tool=tool,
                smell_detector=smell_detector,
                change=change,
                loc_group=loc_group_value,
                baseline_group=baseline_group,
                focal_group=focal_group,
            )
        )
    return rows


def _association_rows_for_frame(
    unique: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    change: str,
    loc_group: str,
    baseline_group: str,
    focal_group: str,
) -> list[dict]:
    group_column = f"rg_{change}"
    if unique.empty or group_column not in unique.columns:
        return []
    baseline = unique[unique[group_column] == baseline_group]
    focal = unique[unique[group_column] == focal_group]
    if baseline.empty or focal.empty:
        return []

    rows = []
    for smell in [ALL_SMELLS, *smell_type_order(unique)]:
        has_smell = lambda value: bool(split_smells(value)) if smell == ALL_SMELLS else smell in split_smells(value)
        baseline_smell_n = int(baseline["smells"].map(has_smell).sum())
        focal_smell_n = int(focal["smells"].map(has_smell).sum())
        baseline_percent = baseline_smell_n / len(baseline) * 100
        focal_percent = focal_smell_n / len(focal) * 100
        ci_low, ci_high = difference_interval(focal_smell_n, len(focal), baseline_smell_n, len(baseline))
        ratio, ratio_low, ratio_high, fisher_p = pooled_statistics(
            focal_smell_n,
            len(focal),
            baseline_smell_n,
            len(baseline),
        )
        mh_ratio, mh_p = mantel_haenszel_statistics(
            unique,
            smell,
            baseline_group=baseline_group,
            focal_group=focal_group,
            group_column=group_column,
        )
        rows.append(
            {
                "strategy": strategy,
                "tool": tool,
                "smell_detector": smell_detector,
                "change": change,
                "loc_group": loc_group,
                "baseline_group": output_revision_group(baseline_group),
                "focal_group": output_revision_group(focal_group),
                "smell": smell,
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
                "mh_odds_ratio": round(mh_ratio, 2),
                "mh_p": mh_p,
            }
        )

    individual_indices = [index for index, row in enumerate(rows) if row["smell"] != ALL_SMELLS]
    fisher_adjusted = benjamini_hochberg([rows[index]["fisher_p"] for index in individual_indices])
    mh_adjusted = benjamini_hochberg([rows[index]["mh_p"] for index in individual_indices])
    for row in rows:
        row.update(
            {
                "fisher_p_adjusted": math.nan,
                "significant": "",
                "mh_p_adjusted": math.nan,
                "mh_significant": "",
                "sensitivity_agrees": "",
            }
        )
    for index, fisher_p_adjusted, mh_p_adjusted in zip(individual_indices, fisher_adjusted, mh_adjusted):
        row = rows[index]
        row["fisher_p_adjusted"] = fisher_p_adjusted
        row["significant"] = "x" if fisher_p_adjusted < ALPHA else ""
        row["mh_p_adjusted"] = mh_p_adjusted
        row["mh_significant"] = "x" if mh_p_adjusted < ALPHA else ""
        same_direction = (row["difference_pp"] > 0 and row["mh_odds_ratio"] > 1) or (
            row["difference_pp"] < 0 and row["mh_odds_ratio"] < 1
        )
        row["sensitivity_agrees"] = "x" if same_direction and row["mh_significant"] == row["significant"] else ""
    return rows


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    revision_group_pairs = selected_revision_group_pairs(args.revision_group_pairs)
    generated_dir = experiment_directory / OUTPUT_DIRECTORY_NAME
    if not generated_dir.exists():
        warnings.warn(f"Directory not found, skipping: {generated_dir}")
        return

    rows = []
    strategies = select_named_items(util.sorted_directory_names(generated_dir), selected_strategies, item_label="strategy")
    for strategy in strategies:
        tools = select_named_items(
            util.sorted_directory_names(generated_dir / strategy),
            selected_tools,
            item_label="tool",
        )
        for tool in tools:
            loc_groups = loc_group_frame(
                load_smell_frames(experiment_directory, smell_detector, strategy, selected_projects)
            )
            frame = load_generated_frames(
                experiment_directory,
                tool,
                strategy,
                smell_detector,
                selected_projects,
                min_t2p_links=args.min_t2p_links,
            )
            if not frame.empty:
                for focal_group, baseline_group in revision_group_pairs:
                    rows.extend(
                        association_rows(
                            frame,
                            strategy=strategy,
                            tool=tool,
                            smell_detector=smell_detector,
                            change=args.change,
                            baseline_group=baseline_group,
                            focal_group=focal_group,
                            loc_groups=loc_groups,
                        )
                    )

    output_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    os.makedirs(output_file.parent, exist_ok=True)
    output_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if not output_df.empty:
        output_df = output_df.sort_values(
            ["strategy", "tool", "smell_detector", "change", "loc_group", "difference_pp"],
            ascending=[True, True, True, True, True, False],
        )
    output_df.to_csv(output_file, index=False)
    print(f"Wrote {output_file}")


if __name__ == "__main__":
    main()
