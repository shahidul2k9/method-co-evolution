from pathlib import Path
import operator
import random
import math
from collections.abc import Sequence

import pandas as pd

from mhc.config import DATA_DIRECTORY
from ptc.experiment_util import list_csv_files
from ptc.link_strategy import LinkStrategy, keys_from_mask


def _strategy_key(strategy: str | LinkStrategy) -> str:
    if isinstance(strategy, LinkStrategy):
        return "--".join(keys_from_mask(strategy))
    return "--".join(part.strip().lower() for part in strategy.split("--") if part.strip())


def _apply_filter(
    frame: pd.DataFrame,
    left_column: str | None,
    comparison_operator: str | None,
    right_column: str | None,
) -> pd.DataFrame:
    if left_column is None and comparison_operator is None and right_column is None:
        return frame

    if not left_column or not comparison_operator or not right_column:
        raise ValueError("left_column, comparison_operator, and right_column must be passed together")

    operations = {
        ">": operator.gt,
        ">=": operator.ge,
        "<": operator.lt,
        "<=": operator.le,
        "==": operator.eq,
        "!=": operator.ne,
    }
    if comparison_operator not in operations:
        raise ValueError("comparison_operator must be one of: >, >=, <, <=, ==, !=")

    if left_column not in frame.columns or right_column not in frame.columns:
        raise ValueError(f"Missing column(s): {left_column}, {right_column}")

    left_values = pd.to_numeric(frame[left_column], errors="coerce")
    right_values = pd.to_numeric(frame[right_column], errors="coerce")
    mask = operations[comparison_operator](left_values, right_values).fillna(False)
    return frame.loc[mask].copy()


def _percentage(value: int, total: int) -> float:
    if total == 0:
        return 0.0
    return round(value / total, 2)


def _confidence_sample_size(
    population_size: int,
    confidence_level: float = 0.95,
    margin_of_error: float = 0.05,
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
        raise ValueError("confidence_level must be one of: 0.90, 0.95, 0.99")

    z_score = z_scores[confidence_level]
    numerator = (z_score**2) * proportion * (1 - proportion)
    denominator = margin_of_error**2
    infinite_population_sample = numerator / denominator

    finite_population_sample = infinite_population_sample / (
        1 + ((infinite_population_sample - 1) / population_size)
    )
    return min(population_size, math.ceil(finite_population_sample))


def _extreme_subset(
    frame: pd.DataFrame,
    left_column: str,
    right_column: str,
    filter_out_percent: int,
) -> pd.DataFrame:
    if not 0 <= filter_out_percent < 100:
        raise ValueError("filter_out_percent must be between 0 and 99")

    difference_values = pd.to_numeric(frame[left_column], errors="coerce") - pd.to_numeric(
        frame[right_column], errors="coerce"
    )
    ranked_frame = frame.assign(_difference=difference_values).dropna(subset=["_difference"]).copy()
    if ranked_frame.empty:
        return ranked_frame

    ranked_frame = ranked_frame.sort_values("_difference", ascending=True, kind="stable")
    rows_to_keep = max(1, math.ceil(len(ranked_frame) * (100 - filter_out_percent) / 100))
    return ranked_frame.tail(rows_to_keep).copy()


def main(
    projects: str | Sequence[str] | None,
    tool_name: str,
    method_linking_strategy: str | LinkStrategy,
    filter_out_percent: int,
    seed: int = 42,
    left_column: str | None = None,
    comparison_operator: str | None = None,
    right_column: str | None = None,
    summary_filename_prefix: str | None = None,
) -> Path:
    if not left_column or not right_column or not comparison_operator:
        raise ValueError(
            "left_column, comparison_operator, and right_column are required for filtering and sampling"
        )

    strategy_key = _strategy_key(method_linking_strategy)
    input_directory = Path(DATA_DIRECTORY) / "t2p-change" / tool_name / strategy_key
    aggregate_directory = Path(DATA_DIRECTORY) / "aggregate"
    aggregate_directory.mkdir(parents=True, exist_ok=True)

    project_files = list_csv_files(input_directory, projects, strict=False)
    if not project_files:
        raise FileNotFoundError(f"No csv files found in {input_directory}")

    random_generator = random.Random(seed)
    project_counts = {}
    all_filtered_frames = []
    total_methods_across_projects = 0

    for project_file in project_files:
        project_name = project_file.stem
        project_df = pd.read_csv(project_file, keep_default_na=False, na_filter=False)
        total_methods_across_projects += len(project_df)
        filtered_project_df = _apply_filter(project_df, left_column, comparison_operator, right_column)
        project_counts[project_name] = {
            "methods": len(project_df),
            "gt": len(filtered_project_df),
            "gt_extreme": 0,
        }
        if not filtered_project_df.empty:
            filtered_project_df = filtered_project_df.copy()
            filtered_project_df["project"] = project_name
            filtered_project_df["tool"] = tool_name
            all_filtered_frames.append(filtered_project_df)

    if not all_filtered_frames:
        raise ValueError("No rows left after applying the filter")

    filtered_df = pd.concat(all_filtered_frames, ignore_index=True)
    candidate_df = _extreme_subset(
        filtered_df,
        left_column=left_column,
        right_column=right_column,
        filter_out_percent=filter_out_percent,
    )
    total_candidate_samples = len(candidate_df)
    sample_size = _confidence_sample_size(total_candidate_samples, confidence_level=0.95, margin_of_error=0.05)

    print(f"Total methods linked test and production across all projects: {total_methods_across_projects}")
    print(
        "Total methods where test methods changes more than production across all projects: "
        f"{len(filtered_df)}"
    )
    print(f"Total methods after filtering out %{filter_out_percent} methods: {total_candidate_samples}")
    print(f"Sample size at 95% confidence and 5% error: {sample_size}")

    if sample_size == 0:
        raise ValueError("Sample size is zero after filtering")

    sampled_df = candidate_df.sample(
        n=sample_size,
        random_state=random_generator.randint(0, 10**9),
    ).copy()
    sampled_df["notes"] = ""
    sampled_df["tags"] = ""

    extreme_method_counts = candidate_df["project"].value_counts().to_dict()
    sampled_method_counts = sampled_df["project"].value_counts().to_dict()


    summary_rows = []
    for project_name in sorted(project_counts):
        methods = project_counts[project_name]["methods"]
        filtered_methods = project_counts[project_name]["gt"]
        extreme_methods = extreme_method_counts.get(project_name, 0)
        sampled_methods = sampled_method_counts.get(project_name, 0)
        summary_rows.append(
            {
                "project": project_name,
                "methods": methods,
                "gt": filtered_methods,
                "gt_pct": _percentage(filtered_methods, methods),
                "gt_extreme": extreme_methods,
                "gt_extreme_pct": _percentage(extreme_methods, methods),
                "gt_sample": sampled_methods,
            }
        )
    output_prefix = f"{summary_filename_prefix}-{tool_name}-{strategy_key}"
    sample_output_file = aggregate_directory / f"{output_prefix}.csv"
    summary_output_file = aggregate_directory / f"{output_prefix}--summary.csv"

    sampled_df.drop(columns=["_difference"], errors="ignore").to_csv(sample_output_file, index=False)
    pd.DataFrame(summary_rows).to_csv(summary_output_file, index=False)

    return aggregate_directory


if __name__ == "__main__":
    output_dir = main(
        projects=None,
        tool_name="historyFinder",
        method_linking_strategy="ncc",
        filter_out_percent=80,
        seed=42,
        left_column="from_ch_diff",
        comparison_operator=">",
        right_column="to_ch_diff",
        summary_filename_prefix="t2p-extreme-test",
    )
    print(output_dir)
