from __future__ import annotations

import math
import os
import warnings

import pandas as pd
from scipy.stats import kendalltau, pearsonr, spearmanr

import mhc.util as util
from mhc.command_util import (
    build_experiment_parser,
    list_csv_files,
    non_negative_int,
    resolve_experiment_filters,
    resolve_experiment_paths,
    resolve_revision_types,
    resolve_smell_detector,
    select_named_items,
    select_revision_columns,
)
from ptc.generator.run_stats import GenerationStats, should_generate
from ptc.generator.t2p_test_smell_association import DEFAULT_CHANGE, OUTPUT_FILE_NAME as ASSOCIATION_OUTPUT_FILE_NAME
from ptc.generator.t2p_test_smell_loc_group import valid_loc
from ptc.generator.t2p_test_smell_prevalence import split_smells
from ptc.generator.t2p_test_smell import OUTPUT_DIRECTORY_NAME as T2P_TEST_SMELL_DIRECTORY_NAME
from ptc.generator.t2p_test_smell_revision import CHANGE_COLUMNS
from ptc.generator.t2p_test_smell_size_control_association import top_smells_from_association

OUTPUT_FILE_NAME = "t2p-test-smell-top-loc-correlation.csv"
OUTPUT_COLUMNS = [
    "strategy",
    "tool",
    "smell_detector",
    "change",
    "top_n",
    "top_smells",
    "methods",
    "loc_min",
    "loc_median",
    "loc_max",
    "top_smell_count_min",
    "top_smell_count_median",
    "top_smell_count_max",
    "correlation_algorithm",
    "correlation",
    "p_value",
    "effect_size",
]


def build_parser():
    parser = build_experiment_parser(
        "Correlate method LOC with selected top test-smell count.",
        include_revision_types=True,
        include_smell_detector=True,
        include_replace=True,
        projects_help="Comma-separated project names to include. Defaults to ME_PROJECTS.",
        strategies_help="Comma-separated strategy names to include. Defaults to ME_STRATEGIES.",
        revision_types_help="Comma-separated revision types to include. Defaults to ME_REVISION_TYPES.",
    )
    parser.add_argument("--top-n-smells", type=non_negative_int, default=5)
    return parser


def effect_size_label(value: float) -> str:
    if pd.isna(value):
        return ""
    magnitude = abs(float(value))
    if magnitude < 0.10:
        return "negligible"
    if magnitude < 0.30:
        return "small"
    if magnitude < 0.50:
        return "medium"
    return "large"


def unique_test_method_locs(smell_frames: list[pd.DataFrame]) -> pd.DataFrame:
    rows_by_url: dict[str, dict] = {}
    for smell_df in smell_frames:
        if not {"url", "loc"}.issubset(smell_df.columns):
            continue
        for row in smell_df[["url", "loc"]].itertuples(index=False):
            url = str(row[0] or "")
            if not url:
                continue
            loc = valid_loc(row[1])
            if loc is None:
                continue
            rows_by_url.setdefault(url, {"from_url": url, "loc": loc})
    return pd.DataFrame(rows_by_url.values(), columns=["from_url", "loc"])


def unique_linked_method_locs(link_frames: list[pd.DataFrame]) -> pd.DataFrame:
    rows_by_url: dict[str, dict] = {}
    for link_df in link_frames:
        if not {"from_url", "from_start", "from_end"}.issubset(link_df.columns):
            continue
        starts = pd.to_numeric(link_df["from_start"], errors="coerce")
        ends = pd.to_numeric(link_df["from_end"], errors="coerce")
        for url, start, end in zip(link_df["from_url"].astype(str), starts, ends):
            if not url or pd.isna(start) or pd.isna(end):
                continue
            loc = int(end) - int(start) + 1
            if loc <= 0:
                continue
            rows_by_url.setdefault(url, {"from_url": url, "loc": loc})
    return pd.DataFrame(rows_by_url.values(), columns=["from_url", "loc"])


def unique_test_method_loc_smells(smell_frames: list[pd.DataFrame]) -> pd.DataFrame:
    rows_by_url: dict[str, dict] = {}
    for smell_df in smell_frames:
        if not {"url", "loc"}.issubset(smell_df.columns):
            continue
        smell_column = "smell" if "smell" in smell_df.columns else "smells" if "smells" in smell_df.columns else None
        if smell_column is None:
            continue
        for row in smell_df[["url", "loc", smell_column]].itertuples(index=False):
            url = str(row[0] or "")
            if not url:
                continue
            loc = valid_loc(row[1])
            if loc is None:
                continue
            entry = rows_by_url.setdefault(url, {"from_url": url, "loc": loc, "smells": set()})
            for smell in split_smells(row[2]):
                entry["smells"].add(smell)
    rows = [
        {"from_url": row["from_url"], "loc": row["loc"], "smells": " ".join(sorted(row["smells"]))}
        for row in rows_by_url.values()
    ]
    return pd.DataFrame(rows, columns=["from_url", "loc", "smells"])


def unique_linked_test_method_smells(link_frames: list[pd.DataFrame]) -> pd.DataFrame:
    rows_by_url: dict[str, set[str]] = {}
    for link_df in link_frames:
        if not {"from_url", "smells"}.issubset(link_df.columns):
            continue
        for row in link_df[["from_url", "smells"]].itertuples(index=False):
            url = str(row[0] or "")
            if not url:
                continue
            rows_by_url.setdefault(url, set()).update(split_smells(row[1]))
    rows = [
        {"from_url": url, "smells": " ".join(sorted(smells))}
        for url, smells in rows_by_url.items()
    ]
    return pd.DataFrame(rows, columns=["from_url", "smells"])


def method_frame_from_t2p_test_smell(
    link_frames: list[pd.DataFrame],
    loc_frames: list[pd.DataFrame],
) -> pd.DataFrame:
    linked_methods = unique_linked_test_method_smells(link_frames)
    if linked_methods.empty:
        return pd.DataFrame(columns=["from_url", "loc", "smells"])
    locs = unique_linked_method_locs(loc_frames)
    if locs.empty:
        return pd.DataFrame(columns=["from_url", "loc", "smells"])
    return linked_methods.merge(locs, on="from_url", how="inner")[["from_url", "loc", "smells"]]


def top_smell_count_frame(methods: pd.DataFrame, top_smells: list[str]) -> pd.DataFrame:
    if methods.empty:
        return pd.DataFrame(columns=[*methods.columns, "top_smell_count"])
    selected = set(top_smells)
    frame = methods.copy()
    frame["top_smell_count"] = frame["smells"].map(lambda value: len(set(split_smells(value)).intersection(selected)))
    return frame


def correlation_rows(
    methods: pd.DataFrame,
    *,
    strategy: str,
    tool: str,
    smell_detector: str,
    revision_type: str = DEFAULT_CHANGE,
    top_smells: list[str],
) -> list[dict]:
    frame = top_smell_count_frame(methods, top_smells)
    if frame.empty:
        return []

    loc = pd.to_numeric(frame["loc"], errors="coerce")
    counts = pd.to_numeric(frame["top_smell_count"], errors="coerce")
    valid = pd.DataFrame({"loc": loc, "top_smell_count": counts}).dropna()
    if valid.empty:
        return []

    if len(valid) < 2 or valid["loc"].nunique() < 2 or valid["top_smell_count"].nunique() < 2:
        statistics = [
            ("spearman", math.nan, math.nan),
            ("kendall", math.nan, math.nan),
            ("pearson", math.nan, math.nan),
        ]
    else:
        spearman = spearmanr(valid["loc"], valid["top_smell_count"])
        kendall = kendalltau(valid["loc"], valid["top_smell_count"])
        pearson = pearsonr(valid["loc"], valid["top_smell_count"])
        statistics = [
            ("spearman", float(spearman.statistic), float(spearman.pvalue)),
            ("kendall", float(kendall.statistic), float(kendall.pvalue)),
            ("pearson", float(pearson.statistic), float(pearson.pvalue)),
        ]

    common = {
        "strategy": strategy,
        "tool": tool,
        "smell_detector": smell_detector,
        "change": revision_type,
        "top_n": len(top_smells),
        "top_smells": " ".join(top_smells),
        "methods": len(valid),
        "loc_min": int(valid["loc"].min()),
        "loc_median": round(float(valid["loc"].median()), 2),
        "loc_max": int(valid["loc"].max()),
        "top_smell_count_min": int(valid["top_smell_count"].min()),
        "top_smell_count_median": round(float(valid["top_smell_count"].median()), 2),
        "top_smell_count_max": int(valid["top_smell_count"].max()),
    }
    rows = []
    for algorithm, estimate, p_value in statistics:
        rows.append(
            {
                **common,
                "correlation_algorithm": algorithm,
                "correlation": round(estimate, 4) if pd.notna(estimate) else math.nan,
                "p_value": p_value,
                "effect_size": effect_size_label(estimate),
            }
        )
    return rows


def t2p_test_smell_input_directory(
    experiment_directory,
    strategy: str,
    tool: str,
    smell_detector: str,
):
    strategy_dir = experiment_directory / T2P_TEST_SMELL_DIRECTORY_NAME / strategy
    nested_dir = strategy_dir / tool / smell_detector if tool else None
    if nested_dir is not None and nested_dir.exists():
        return nested_dir
    return strategy_dir / smell_detector


def load_t2p_test_smell_frames(
    experiment_directory,
    strategy: str,
    tool: str,
    smell_detector: str,
    selected_projects: list[str] | None,
) -> list[pd.DataFrame]:
    input_dir = t2p_test_smell_input_directory(experiment_directory, strategy, tool, smell_detector)
    csv_files = list_csv_files(input_dir, selected_projects, strict=False)
    frames = []
    for csv_file in csv_files:
        frame = pd.read_csv(csv_file, keep_default_na=False, na_filter=False)
        frames.append(frame)
    return frames


def t2p_link_input_directory(experiment_directory, strategy: str, tool: str):
    strategy_dir = experiment_directory / "t2p-link" / strategy
    nested_dir = strategy_dir / tool if tool else None
    if nested_dir is not None and nested_dir.exists():
        return nested_dir
    return strategy_dir


def load_t2p_link_frames(
    experiment_directory,
    strategy: str,
    tool: str,
    selected_projects: list[str] | None,
) -> list[pd.DataFrame]:
    input_dir = t2p_link_input_directory(experiment_directory, strategy, tool)
    csv_files = list_csv_files(input_dir, selected_projects, strict=False)
    return [pd.read_csv(csv_file, keep_default_na=False, na_filter=False) for csv_file in csv_files]


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    stats = GenerationStats("t2p_test_smell_top_loc_correlation")
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

    generated_dir = experiment_directory / T2P_TEST_SMELL_DIRECTORY_NAME
    if not generated_dir.exists():
        warnings.warn(
            f"Directory not found, skipping: {generated_dir}. "
            "Run ptc.generator.t2p_test_smell first."
        )
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
        strategy_dir = generated_dir / strategy
        strategy_children = util.sorted_directory_names(strategy_dir)
        if smell_detector in strategy_children:
            tools = [""]
        else:
            tools = select_named_items(strategy_children, selected_tools, item_label="tool")
        for tool in tools:
            link_frames = load_t2p_test_smell_frames(
                experiment_directory,
                strategy,
                tool,
                smell_detector,
                selected_projects,
            )
            methods = method_frame_from_t2p_test_smell(
                link_frames,
                load_t2p_link_frames(experiment_directory, strategy, tool, selected_projects),
            )
            for revision_type in revision_types:
                top_smells = top_smells_from_association(
                    association_frame,
                    strategy=strategy,
                    tool=tool or "historyFinder",
                    smell_detector=smell_detector,
                    revision_type=revision_type,
                    top_n=args.top_n_smells,
                )
                if not top_smells:
                    warnings.warn(
                        "No association-selected top smells found for "
                        f"{strategy}/{tool or 'historyFinder'}/{smell_detector}/{revision_type}, skipping."
                    )
                    continue
                print(
                    "Top LOC-correlation smells "
                    f"({strategy}/{tool or 'historyFinder'}/{smell_detector}/{revision_type}): {', '.join(top_smells)}"
                )
                rows.extend(
                    correlation_rows(
                        methods,
                        strategy=strategy,
                        tool=tool or "historyFinder",
                        smell_detector=smell_detector,
                        revision_type=revision_type,
                        top_smells=top_smells,
                    )
                )

    os.makedirs(output_file.parent, exist_ok=True)
    output_df = pd.DataFrame(rows, columns=OUTPUT_COLUMNS)
    if not output_df.empty:
        output_df = output_df.sort_values(
            ["strategy", "tool", "smell_detector", "change", "correlation_algorithm"]
        ).reset_index(drop=True)
    output_df.to_csv(output_file, index=False)
    if output_df.empty:
        stats.record_empty_output()
    stats.record_write(len(output_df))
    print(f"Wrote {output_file}")
    stats.print_summary()


if __name__ == "__main__":
    main()
