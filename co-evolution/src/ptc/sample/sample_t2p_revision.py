import warnings
import sys
import math
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    list_csv_files,
    non_negative_int,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_min_t2p_links,
    resolve_revision_types,
    select_named_items,
)


REVIEW_COLUMNS = [
    "project",
    "tool",
    "from_name",
    "to_name",
    "from_url",
    "to_url",
    "sampled",
    "label",
    "tags",
    "notes",
]
DUPLICATE_KEY_COLUMNS = ["from_url", "to_url"]
DEFAULT_MIN_T2P_REVISION = 5
DEFAULT_SAMPLE_CONFIDENCE = 0.95
DEFAULT_SAMPLE_MARGIN_ERROR = 0.05


@dataclass(frozen=True)
class ProjectReviewInput:
    project: str
    source_count: int
    review_df: pd.DataFrame


def normalize_argv(argv: list[str] | None) -> list[str] | None:
    if argv is None:
        return None

    normalized_args: list[str] = []
    for arg in argv:
        if arg.startswith("-") or "=" not in arg:
            normalized_args.append(arg)
            continue

        for part in arg.split(","):
            if not part:
                continue
            if "=" not in part:
                normalized_args.append(part)
                continue
            key, value = part.split("=", 1)
            normalized_args.extend([f"--{key.strip()}", value.strip()])
    return normalized_args


def build_parser():
    parser = build_experiment_parser(
        "Sample linked test-production rows for revision review.",
        include_revision_types=True,
        projects_help="Comma-separated project names to process. Defaults to ME_PROJECTS.",
        revision_types_help="Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
    )
    parser.add_argument(
        "--min-t2p-links",
        dest="min_t2p_links",
        type=non_negative_int,
        default=resolve_min_t2p_links(),
        help="Minimum linked test-production pairs required before review CSVs are generated. Defaults to ME_MIN_T2P_LINKS.",
    )
    parser.add_argument(
        "--min-t2p-revision",
        dest="min_t2p_revision",
        type=non_negative_int,
        default=DEFAULT_MIN_T2P_REVISION,
        help=f"Minimum from/to revision delta required for review rows. Defaults to {DEFAULT_MIN_T2P_REVISION}.",
    )
    parser.add_argument(
        "--seed",
        dest="seed",
        type=int,
        default=42,
        help="Random seed used when selecting new sampled rows. Defaults to 42.",
    )
    parser.add_argument(
        "--sample-confidence",
        dest="sample_confidence",
        type=float,
        default=DEFAULT_SAMPLE_CONFIDENCE,
        help=f"Confidence level for finite-population sample size. Defaults to {DEFAULT_SAMPLE_CONFIDENCE}.",
    )
    parser.add_argument(
        "--sample-margin-error",
        dest="sample_margin_error",
        type=float,
        default=DEFAULT_SAMPLE_MARGIN_ERROR,
        help=f"Margin of error for finite-population sample size. Defaults to {DEFAULT_SAMPLE_MARGIN_ERROR}.",
    )
    return parser


def _format_percent(count: int, total: int) -> str:
    if total == 0:
        return "0.0%"
    return f"{(count / total) * 100:.1f}%"


def confidence_sample_size(
    population_size: int,
    confidence_level: float = DEFAULT_SAMPLE_CONFIDENCE,
    margin_of_error: float = DEFAULT_SAMPLE_MARGIN_ERROR,
    proportion: float = 0.5,
) -> int:
    if population_size <= 0:
        return 0

    z_scores = {
        0.90: 1.645,
        0.95: 1.96,
        0.99: 2.576,
    }
    if confidence_level not in z_scores:
        raise ValueError("sample confidence must be one of: 0.90, 0.95, 0.99")
    if margin_of_error <= 0:
        raise ValueError("sample margin error must be greater than zero")

    z_score = z_scores[confidence_level]
    numerator = (z_score**2) * proportion * (1 - proportion)
    denominator = margin_of_error**2
    infinite_population_sample = numerator / denominator
    finite_population_sample = infinite_population_sample / (
        1 + ((infinite_population_sample - 1) / population_size)
    )
    return min(population_size, math.ceil(finite_population_sample))


def allocate_proportional_samples(populations: dict[str, int], target: int) -> dict[str, int]:
    allocations = {project: 0 for project in populations}
    eligible = {project: size for project, size in populations.items() if size > 0}
    if target <= 0 or not eligible:
        return allocations

    target = min(target, sum(eligible.values()))
    total = sum(eligible.values())
    quotas = {project: target * size / total for project, size in eligible.items()}
    min_allowed = {project: 1 if target >= len(eligible) else 0 for project in eligible}

    for project, quota in quotas.items():
        allocations[project] = min(eligible[project], max(min_allowed[project], math.floor(quota)))

    def remainder(project: str) -> float:
        return quotas[project] - math.floor(quotas[project])

    remaining = target - sum(allocations.values())
    while remaining > 0:
        candidates = [
            project for project in eligible
            if allocations[project] < eligible[project]
        ]
        if not candidates:
            break
        for selected in sorted(
            candidates,
            key=lambda project: (remainder(project), eligible[project], project),
            reverse=True,
        ):
            if remaining == 0:
                break
            allocations[selected] += 1
            remaining -= 1

    excess = sum(allocations.values()) - target
    while excess > 0:
        candidates = [
            project for project in eligible
            if allocations[project] > min_allowed[project]
        ]
        if not candidates:
            break
        for selected in sorted(candidates, key=lambda project: (remainder(project), eligible[project], project)):
            if excess == 0:
                break
            allocations[selected] -= 1
            excess -= 1

    return allocations


def _review_frame(frame: pd.DataFrame, project: str, tool: str = "") -> pd.DataFrame:
    review_df = frame.copy()
    if "project" not in review_df:
        review_df["project"] = project
    if "tool" not in review_df:
        review_df["tool"] = tool
    for column in REVIEW_COLUMNS:
        if column not in review_df:
            review_df[column] = ""
    review_df["sampled"] = "0"
    review_df["label"] = ""
    review_df["tags"] = ""
    review_df["notes"] = ""
    return review_df[REVIEW_COLUMNS].drop_duplicates(subset=DUPLICATE_KEY_COLUMNS, keep="first").copy()


def _read_existing_review(output_file: Path) -> pd.DataFrame:
    if not output_file.exists():
        return pd.DataFrame(columns=REVIEW_COLUMNS)

    existing_df = pd.read_csv(output_file, keep_default_na=False, na_filter=False)
    if any(column not in existing_df for column in DUPLICATE_KEY_COLUMNS):
        warnings.warn(f"Existing review CSV is missing duplicate key columns, treating as empty: {output_file}")
        return pd.DataFrame(columns=REVIEW_COLUMNS)

    for column in REVIEW_COLUMNS:
        if column not in existing_df:
            existing_df[column] = ""
    return existing_df[REVIEW_COLUMNS].drop_duplicates(subset=DUPLICATE_KEY_COLUMNS, keep="first").copy()


def _row_key(row) -> tuple[str, str]:
    return str(row["from_url"]), str(row["to_url"])


def _sampled_keys(existing_df: pd.DataFrame) -> set[tuple[str, str]]:
    if existing_df.empty:
        return set()
    sampled = existing_df["sampled"].astype(str).str.strip().isin({"1", "true", "True"})
    return {_row_key(row) for _, row in existing_df.loc[sampled].iterrows()}


def _merge_review_rows(current_df: pd.DataFrame, existing_df: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    existing_by_key = {_row_key(row): row for _, row in existing_df.iterrows()}
    merged_rows = []
    skipped_duplicates = 0
    added_rows = 0

    for _, current_row in current_df.iterrows():
        key = _row_key(current_row)
        if key in existing_by_key:
            existing_row = existing_by_key[key].copy()
            for column in ["project", "tool", "from_name", "to_name", "from_url", "to_url"]:
                existing_row[column] = current_row[column]
            merged_rows.append(existing_row)
            skipped_duplicates += 1
        else:
            merged_rows.append(current_row.copy())
            added_rows += 1

    if not merged_rows:
        return pd.DataFrame(columns=REVIEW_COLUMNS), added_rows, skipped_duplicates

    merged_df = pd.DataFrame(merged_rows)
    for column in REVIEW_COLUMNS:
        if column not in merged_df:
            merged_df[column] = ""
    return merged_df[REVIEW_COLUMNS].copy(), added_rows, skipped_duplicates


def _write_review_rows(output_file: Path, output_df: pd.DataFrame) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_df[REVIEW_COLUMNS].to_csv(output_file, index=False)


def qualifying_rows(
    project_df: pd.DataFrame,
    revision_types: list[str],
    *,
    min_t2p_revision: int,
    project: str,
    tool: str,
    strategy: str,
) -> pd.DataFrame:
    masks = []
    for revision_type in revision_types:
        from_column = f"from_{revision_type}"
        to_column = f"to_{revision_type}"
        if from_column not in project_df.columns or to_column not in project_df.columns:
            warnings.warn(
                "Skipping "
                f"project={project}, tool={tool}, strategy={strategy}, revision_type={revision_type}: "
                f"missing required columns {from_column!r} and/or {to_column!r}."
            )
            continue

        pair_df = project_df[[from_column, to_column]].apply(pd.to_numeric, errors="coerce")
        valid_mask = pair_df[from_column].notna() & pair_df[to_column].notna()
        if not valid_mask.any():
            warnings.warn(
                "Skipping "
                f"project={project}, tool={tool}, strategy={strategy}, revision_type={revision_type}: "
                "no valid numeric revision pairs."
            )
            continue

        masks.append(valid_mask & ((pair_df[from_column] - pair_df[to_column]) >= min_t2p_revision))

    if not masks:
        return project_df.iloc[0:0].copy()

    combined_mask = masks[0].copy()
    for mask in masks[1:]:
        combined_mask = combined_mask | mask
    return project_df.loc[combined_mask].copy()


def load_project_review_input(
    project_file: Path,
    *,
    revision_types: list[str],
    min_t2p_links: int,
    min_t2p_revision: int,
    tool: str,
    strategy: str,
) -> ProjectReviewInput | None:
    project = project_file.stem
    project_df = pd.read_csv(project_file, keep_default_na=False, na_filter=False)
    source_count = len(project_df)
    if source_count < min_t2p_links:
        warnings.warn(
            "Skipping "
            f"project={project}, tool={tool}, strategy={strategy}: "
            f"t2p_links={source_count} is below min_t2p_links={min_t2p_links}."
        )
        return None

    matched_df = qualifying_rows(
        project_df,
        revision_types,
        min_t2p_revision=min_t2p_revision,
        project=project,
        tool=tool,
        strategy=strategy,
    )
    qualifying_count = len(matched_df)
    if qualifying_count == 0:
        return None

    review_df = _review_frame(matched_df, project, tool=tool)
    return ProjectReviewInput(
        project=project,
        source_count=source_count,
        review_df=review_df,
    )


def _select_new_sample_keys(
    merged_df: pd.DataFrame,
    *,
    existing_sampled_keys: set[tuple[str, str]],
    target: int,
    seed: int,
) -> set[tuple[str, str]]:
    if target <= len(existing_sampled_keys):
        return set()

    available_mask = ~merged_df[DUPLICATE_KEY_COLUMNS].apply(
        lambda row: (str(row["from_url"]), str(row["to_url"])) in existing_sampled_keys,
        axis=1,
    )
    available_df = merged_df.loc[available_mask]
    if available_df.empty:
        return set()

    sample_size = min(target - len(existing_sampled_keys), len(available_df))
    sampled_df = available_df.sample(n=sample_size, random_state=seed)
    return {_row_key(row) for _, row in sampled_df.iterrows()}


def _apply_sampled_flags(
    merged_df: pd.DataFrame,
    sampled_keys: set[tuple[str, str]],
) -> pd.DataFrame:
    output_df = merged_df.copy()
    output_df["sampled"] = output_df[DUPLICATE_KEY_COLUMNS].apply(
        lambda row: "1" if (str(row["from_url"]), str(row["to_url"])) in sampled_keys else "0",
        axis=1,
    )
    return output_df[REVIEW_COLUMNS].copy()


def _allocate_topup_targets(
    project_targets: dict[str, int],
    existing_sampled_counts: dict[str, int],
    capacities: dict[str, int],
    global_target: int,
) -> dict[str, int]:
    existing_total = sum(existing_sampled_counts.values())
    remaining_global = max(0, global_target - existing_total)
    deficits = {
        project: min(
            capacities.get(project, 0),
            max(0, project_targets.get(project, 0) - existing_sampled_counts.get(project, 0)),
        )
        for project in project_targets
    }
    deficit_total = sum(deficits.values())
    if remaining_global == 0 or deficit_total == 0:
        return {project: 0 for project in project_targets}
    if deficit_total <= remaining_global:
        return deficits
    return allocate_proportional_samples(deficits, remaining_global)


def process_strategy(
    project_files: list[Path],
    *,
    output_directory: Path,
    revision_types: list[str],
    min_t2p_links: int,
    min_t2p_revision: int,
    sample_confidence: float,
    sample_margin_error: float,
    seed: int,
    tool: str,
    strategy: str,
) -> None:
    project_inputs = []
    for project_file in project_files:
        project_input = load_project_review_input(
            project_file,
            revision_types=revision_types,
            min_t2p_links=min_t2p_links,
            min_t2p_revision=min_t2p_revision,
            tool=tool,
            strategy=strategy,
        )
        if project_input is not None:
            project_inputs.append(project_input)

    if not project_inputs:
        return

    populations = {project_input.project: len(project_input.review_df) for project_input in project_inputs}
    total_population = sum(populations.values())
    global_target = confidence_sample_size(
        total_population,
        confidence_level=sample_confidence,
        margin_of_error=sample_margin_error,
    )
    project_targets = allocate_proportional_samples(populations, global_target)

    project_stats = []
    for project_input in project_inputs:
        project = project_input.project
        output_file = output_directory / f"{project}.csv"
        existing_df = _read_existing_review(output_file)
        existing_sampled_keys = _sampled_keys(existing_df)
        merged_df, added_rows, skipped_duplicates = _merge_review_rows(project_input.review_df, existing_df)
        current_keys = {_row_key(row) for _, row in merged_df.iterrows()}
        existing_sampled_keys = existing_sampled_keys.intersection(current_keys)
        existing_sampled_count = len(existing_sampled_keys)

        project_stats.append(
            {
                "project": project,
                "source_count": project_input.source_count,
                "qualifying_count": len(merged_df),
                "target": project_targets.get(project, 0),
                "existing_sampled_keys": existing_sampled_keys,
                "existing_sampled_count": existing_sampled_count,
                "capacity": len(merged_df) - existing_sampled_count,
                "added_rows": added_rows,
                "skipped_duplicates": skipped_duplicates,
                "merged_df": merged_df,
                "output_file": output_file,
            }
        )

    topup_targets = _allocate_topup_targets(
        project_targets,
        {stat["project"]: stat["existing_sampled_count"] for stat in project_stats},
        {stat["project"]: stat["capacity"] for stat in project_stats},
        global_target,
    )

    total_existing_sampled = 0
    total_newly_sampled = 0
    total_added = 0
    total_skipped_duplicates = 0

    for index, stat in enumerate(project_stats):
        project = stat["project"]
        new_sampled_keys = _select_new_sample_keys(
            stat["merged_df"],
            existing_sampled_keys=stat["existing_sampled_keys"],
            target=stat["existing_sampled_count"] + topup_targets.get(project, 0),
            seed=seed + index,
        )
        sampled_keys = set(stat["existing_sampled_keys"]) | new_sampled_keys
        output_df = _apply_sampled_flags(stat["merged_df"], sampled_keys)
        _write_review_rows(stat["output_file"], output_df)

        newly_sampled_count = len(new_sampled_keys)
        final_sampled_count = int((output_df["sampled"].astype(str) == "1").sum())
        total_existing_sampled += stat["existing_sampled_count"]
        total_newly_sampled += newly_sampled_count
        total_added += stat["added_rows"]
        total_skipped_duplicates += stat["skipped_duplicates"]

        print(
            f"project={project}, tool={tool}, strategy={strategy}: "
            f"source={stat['source_count']}, "
            f"qualifying={stat['qualifying_count']} ({_format_percent(stat['qualifying_count'], stat['source_count'])}), "
            f"target_sample={stat['target']}, "
            f"existing_sampled={stat['existing_sampled_count']}, "
            f"newly_sampled={newly_sampled_count}, "
            f"final_sampled={final_sampled_count} ({_format_percent(final_sampled_count, stat['qualifying_count'])}), "
            f"added={stat['added_rows']}, "
            f"skipped_duplicates={stat['skipped_duplicates']}"
        )

    final_sampled_total = total_existing_sampled + total_newly_sampled
    print(
        f"tool={tool}, strategy={strategy}: "
        f"population={total_population}, "
        f"target_sample={global_target}, "
        f"existing_sampled={total_existing_sampled}, "
        f"newly_sampled={total_newly_sampled}, "
        f"final_sampled={final_sampled_total} ({_format_percent(final_sampled_total, total_population)}), "
        f"added={total_added}, "
        f"skipped_duplicates={total_skipped_duplicates}"
    )


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(normalize_argv(sys.argv[1:] if argv is None else argv))
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    selected_tools, selected_projects, selected_strategies = resolve_experiment_filters(
        tools=args.tools,
        projects=args.projects,
        strategies=args.strategies,
    )
    revision_types = resolve_revision_types(args.revision_types) or []
    if not revision_types:
        warnings.warn("No revision types selected; nothing to sample.")
        return

    t2p_change_dir = experiment_directory / "t2p-change"
    if not t2p_change_dir.exists():
        warnings.warn(f"Directory not found, skipping: {t2p_change_dir}")
        return

    tools = select_named_items(util.sorted_directory_names(t2p_change_dir), selected_tools, item_label="tool")
    for tool in tools:
        tool_dir = t2p_change_dir / tool
        if not tool_dir.exists():
            warnings.warn(f"Tool directory not found, skipping: {tool_dir}")
            continue

        strategies = select_named_items(
            util.sorted_directory_names(tool_dir),
            selected_strategies,
            item_label="strategy",
        )
        for strategy in strategies:
            input_directory = t2p_change_dir / tool / strategy
            output_directory = experiment_directory / "t2p-revision-review" / tool / strategy
            project_files = list_csv_files(input_directory, selected_projects, strict=False)
            if not project_files:
                warnings.warn(f"No csv files found, skipping: {input_directory}")
                continue

            process_strategy(
                project_files,
                output_directory=output_directory,
                revision_types=revision_types,
                min_t2p_links=args.min_t2p_links,
                min_t2p_revision=args.min_t2p_revision,
                sample_confidence=args.sample_confidence,
                sample_margin_error=args.sample_margin_error,
                seed=args.seed,
                tool=tool,
                strategy=strategy,
            )


if __name__ == "__main__":
    main()
