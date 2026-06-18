from __future__ import annotations

import os
import warnings
from pathlib import Path

import pandas as pd

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_smell_detector,
    select_named_items,
)
from ptc.generator.run_stats import GenerationStats, should_generate

OUTPUT_FILE_NAME = "t2p-test-smell-loc-size.csv"
LOC_GROUP_COLUMNS = ["strategy", "smell_detector", "loc_group", "loc_min", "loc_max", "methods", "percent"]
SIZE_GROUPS = ["S", "M", "L", "XL"]


def build_parser():
    return build_experiment_parser(
        "Generate test-method LOC size groups from postprocessed test-smell rows.",
        include_smell_detector=True,
        include_replace=True,
        projects_help="Comma-separated project names to include. Defaults to ME_PROJECTS.",
        strategies_help="Comma-separated strategy names to include. Defaults to ME_STRATEGIES.",
    )


def valid_loc(value) -> int | None:
    try:
        loc = int(float(str(value)))
    except (TypeError, ValueError):
        return None
    return loc if loc > 0 else None


def unique_method_locs(frames: list[pd.DataFrame]) -> pd.DataFrame:
    loc_by_url: dict[str, int] = {}
    for frame in frames:
        if not {"url", "loc"}.issubset(frame.columns):
            continue
        for row in frame[["url", "loc"]].itertuples(index=False):
            url = str(row.url or "")
            if not url or url in loc_by_url:
                continue
            loc = valid_loc(row.loc)
            if loc is not None:
                loc_by_url[url] = loc
    return pd.DataFrame(
        [{"url": url, "loc": loc} for url, loc in loc_by_url.items()],
        columns=["url", "loc"],
    )


def percentile_thresholds(loc_values: pd.Series) -> tuple[int, int, int]:
    numeric = pd.to_numeric(loc_values, errors="coerce").dropna()
    if numeric.empty:
        return 0, 0, 0
    return tuple(int(value) for value in numeric.quantile([0.7, 0.8, 0.9], interpolation="nearest"))


def loc_group(loc: int, thresholds: tuple[int, int, int]) -> str:
    p70, p80, p90 = thresholds
    if loc <= p70:
        return "S"
    if loc <= p80:
        return "M"
    if loc <= p90:
        return "L"
    return "XL"


def loc_bounds(values: pd.Series) -> tuple[str, str]:
    if values.empty:
        return "", ""
    minimum = int(values.min())
    maximum = int(values.max())
    return str(minimum), str(maximum)


def loc_group_rows(
    method_locs: pd.DataFrame,
    *,
    strategy: str,
    smell_detector: str,
) -> list[dict]:
    if method_locs.empty or "loc" not in method_locs.columns:
        return []

    frame = method_locs.copy()
    frame["loc"] = pd.to_numeric(frame["loc"], errors="coerce")
    frame = frame.dropna(subset=["loc"])
    frame = frame[frame["loc"] > 0].copy()
    if frame.empty:
        return []

    thresholds = percentile_thresholds(frame["loc"])
    frame["size_group"] = frame["loc"].map(lambda loc: loc_group(int(loc), thresholds))
    total = len(frame)
    rows = []
    for size_group in SIZE_GROUPS:
        group = frame[frame["size_group"] == size_group]
        methods = len(group)
        loc_min, loc_max = loc_bounds(group["loc"])
        rows.append(
            {
                "strategy": strategy,
                "smell_detector": smell_detector,
                "loc_group": size_group,
                "loc_min": loc_min,
                "loc_max": loc_max,
                "methods": methods,
                "percent": round(methods / total * 100, 2) if total else 0.0,
            }
        )
    return rows


def read_strategy_locs(
    experiment_directory: Path,
    *,
    smell_detector: str,
    strategy: str,
    selected_projects: list[str] | None,
) -> pd.DataFrame:
    input_dir = experiment_directory / "test-smell" / smell_detector / strategy
    csv_files = list_csv_files(input_dir, selected_projects, strict=False)
    frames = []
    for csv_file in csv_files:
        frame = pd.read_csv(csv_file, keep_default_na=False, na_filter=False)
        if not {"url", "loc"}.issubset(frame.columns):
            warnings.warn(f"Skipping {csv_file}: missing required column(s): url, loc.")
            continue
        frames.append(frame)
    return unique_method_locs(frames)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("t2p_test_smell_loc_group")
    experiment_directory = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name,
    ).experiment_directory
    output_file = experiment_directory / "aggregate" / OUTPUT_FILE_NAME
    if not should_generate(output_file, replace=args.replace, label=OUTPUT_FILE_NAME, stats=stats):
        stats.print_summary()
        return

    _, selected_projects, selected_strategies = resolve_experiment_filters(
        projects=args.projects,
        strategies=args.strategies,
    )
    smell_detector = resolve_smell_detector(args.smell_detector)
    detector_dir = experiment_directory / "test-smell" / smell_detector
    if not detector_dir.exists():
        warnings.warn(f"Directory not found, skipping: {detector_dir}")
        stats.skipped_missing_input += 1
        stats.print_summary()
        return

    rows = []
    strategies = select_named_items(
        util.sorted_directory_names(detector_dir),
        selected_strategies,
        item_label="strategy",
    )
    for strategy in strategies:
        method_locs = read_strategy_locs(
            experiment_directory,
            smell_detector=smell_detector,
            strategy=strategy,
            selected_projects=selected_projects,
        )
        rows.extend(loc_group_rows(method_locs, strategy=strategy, smell_detector=smell_detector))

    os.makedirs(output_file.parent, exist_ok=True)
    output_df = pd.DataFrame(rows, columns=LOC_GROUP_COLUMNS)
    if not output_df.empty:
        output_df["_size_order"] = output_df["loc_group"].map({group: index for index, group in enumerate(SIZE_GROUPS)})
        output_df = (
            output_df.sort_values(["strategy", "smell_detector", "_size_order"])
            .drop(columns=["_size_order"])
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
