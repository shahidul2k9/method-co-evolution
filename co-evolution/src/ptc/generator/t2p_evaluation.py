from dataclasses import dataclass

from sklearn.metrics import precision_score, recall_score, f1_score, matthews_corrcoef
from mhc.config import PROJECT_DIRECTORY
from mhc.util import *
from ptc.experiment_util import (
    build_experiment_parser,
    list_csv_files,
    resolve_experiment_filters,
    resolve_experiment_paths,
)

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only in environments without PyYAML installed.
    yaml = None


DEFAULT_GROUND_TRUTH_CONFIG = Path(PROJECT_DIRECTORY) / "config" / "t2p_ground_truth.yml"
METRIC_COLUMNS = [
    "project",
    "experiment",
    "strategy",
    "gt_links",
    "pred_links",
    "tp",
    "fp",
    "fn",
    "precision",
    "recall",
    "f1",
    "mcc",
]


@dataclass(frozen=True)
class GroundTruthConfig:
    groups: dict[str, list[str]]


@dataclass(frozen=True)
class SelectedGroups:
    names: list[str]
    output_name: str


def build_parser():
    parser = build_experiment_parser(
        "Evaluate generated test-to-production links.",
        include_tools=False,
        include_strategies=False,
        projects_help="Comma-separated project names to process.",
    )
    parser.add_argument(
        "--ground-truth-config",
        dest="ground_truth_config",
        type=Path,
        default=DEFAULT_GROUND_TRUTH_CONFIG,
        help="YAML file defining experiments and experiment groups.",
    )
    parser.add_argument(
        "--experiment-group",
        dest="experiment_group",
        type=str,
        help="Experiment group to evaluate. Defaults to --experiment-name.",
    )
    return parser


def _parse_simple_yaml_config(config_text: str) -> dict[str, dict[str, list[str]]]:
    config: dict[str, dict[str, list[str]]] = {}
    current_section: str | None = None
    current_key: str | None = None

    for raw_line in config_text.splitlines():
        line = raw_line.split("#", 1)[0].rstrip()
        if not line.strip():
            continue

        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped.endswith(":"):
            current_section = stripped[:-1]
            config[current_section] = {}
            current_key = None
        elif indent == 2 and stripped.endswith(":"):
            if current_section is None:
                raise ValueError("Invalid ground-truth config: nested key appears before a section.")
            current_key = stripped[:-1]
            config[current_section][current_key] = []
        elif indent == 4 and stripped.startswith("- "):
            if current_section is None or current_key is None:
                raise ValueError("Invalid ground-truth config: list item appears before a key.")
            config[current_section][current_key].append(stripped[2:].strip())
        else:
            raise ValueError(f"Invalid ground-truth config line: {raw_line!r}")

    return config


def _read_yaml_config(config_file: Path) -> dict:
    config_text = config_file.read_text()
    if yaml is not None:
        return yaml.safe_load(config_text) or {}
    return _parse_simple_yaml_config(config_text)


def _normalize_group_mapping(value: object, section_name: str) -> dict[str, list[str]]:
    if value is None:
        return {}

    if isinstance(value, list):
        return {str(item): [str(item)] for item in value}

    if not isinstance(value, dict):
        raise ValueError(f"Ground-truth config section {section_name!r} must be a mapping or list.")

    normalized: dict[str, list[str]] = {}
    for name, members in value.items():
        if isinstance(members, str):
            normalized[str(name)] = [members]
        elif isinstance(members, list):
            normalized[str(name)] = [str(member) for member in members]
        else:
            raise ValueError(f"Ground-truth config group {name!r} must be a list of experiments.")
    return normalized


def load_ground_truth_config(config_file: str | Path) -> GroundTruthConfig:
    config_path = Path(config_file)
    data = _read_yaml_config(config_path)
    experiments = _normalize_group_mapping(data.get("experiments"), "experiments")
    groups = _normalize_group_mapping(data.get("groups"), "groups")
    return GroundTruthConfig(groups={**experiments, **groups})


def resolve_experiment_group(config: GroundTruthConfig, group_name: str) -> list[str]:
    if group_name not in config.groups:
        available = ", ".join(sorted(config.groups)) if config.groups else "<none>"
        raise ValueError(f"Unknown experiment group {group_name!r}. Available groups: {available}")
    return config.groups[group_name]


def resolve_selected_groups(config: GroundTruthConfig, experiment_group: str) -> SelectedGroups:
    raw_group_names = [name.strip() for name in experiment_group.split(",") if name.strip()]
    if not raw_group_names:
        raise ValueError("Experiment group is required.")

    if raw_group_names == ["all"]:
        return SelectedGroups(names=list(config.groups), output_name="all")

    if "all" in raw_group_names:
        raise ValueError("--experiment-group=all cannot be combined with other group names.")

    group_names: list[str] = []
    for group_name in raw_group_names:
        resolve_experiment_group(config, group_name)
        if group_name not in group_names:
            group_names.append(group_name)

    output_name = group_names[0] if len(group_names) == 1 else "multi-group"
    return SelectedGroups(names=group_names, output_name=output_name)


def load_link_df(csv_file: Path) -> pd.DataFrame:
    df = pd.read_csv(csv_file, na_filter=False, keep_default_na=False)
    return df.drop_duplicates()


def load_ground_truth_df(csv_file: Path) -> pd.DataFrame:
    df = load_link_df(csv_file)
    if "label" in df.columns:
        labels = pd.to_numeric(df["label"], errors="coerce")
        df = df[labels == 1].copy()
    return df


def calculate_score(
    project: str,
    experiment: str,
    strategy_name: str,
    pred_detail_df: pd.DataFrame,
    gt_detail_df: pd.DataFrame,
    mismatch_root_dir: Path,
):
    pred_url_df = pred_detail_df[["from_url", "to_url"]].drop_duplicates()
    pred_url_pairs = set(map(tuple, pred_url_df.to_records(index=False)))

    gt_url_df = gt_detail_df[["from_url", "to_url"]].drop_duplicates()
    gt_url_pairs = set(map(tuple, gt_url_df.to_records(index=False)))

    tp_pairs = gt_url_pairs & pred_url_pairs
    fp_pairs = pred_url_pairs - gt_url_pairs
    fn_pairs = gt_url_pairs - pred_url_pairs

    tp = len(tp_pairs)
    fp = len(fp_pairs)
    fn = len(fn_pairs)

    y_true = [1] * tp + [0] * fp + [1] * fn
    y_pred = [1] * tp + [1] * fp + [0] * fn

    precision = precision_score(y_true, y_pred, zero_division=np.nan)
    recall = recall_score(y_true, y_pred, zero_division=np.nan)
    f1 = f1_score(y_true, y_pred, zero_division=np.nan)

    all_pairs = gt_url_pairs | pred_url_pairs
    from_urls = {from_url for from_url, _ in all_pairs}
    to_urls = {to_url for _, to_url in all_pairs}
    candidate_pairs = {(from_url, to_url) for from_url in from_urls for to_url in to_urls}

    if len(candidate_pairs) == 0:
        mcc = np.nan
    else:
        mcc_y_true = [1 if pair in gt_url_pairs else 0 for pair in candidate_pairs]
        mcc_y_pred = [1 if pair in pred_url_pairs else 0 for pair in candidate_pairs]
        if len(set(mcc_y_true)) < 2 or len(set(mcc_y_pred)) < 2:
            mcc = 0.0
        else:
            mcc = matthews_corrcoef(mcc_y_true, mcc_y_pred)

    score = {
        "project": project,
        "experiment": experiment,
        "strategy": strategy_name,
        "gt_links": len(gt_url_pairs),
        "pred_links": len(pred_url_pairs),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 2) if not np.isnan(precision) else np.nan,
        "recall": round(recall, 2) if not np.isnan(recall) else np.nan,
        "f1": round(f1, 2) if not np.isnan(f1) else np.nan,
        "mcc": round(mcc, 2) if not np.isnan(mcc) else np.nan,
    }

    mismatch_df = pred_detail_df.copy()
    mismatch_df["pair"] = list(zip(mismatch_df["from_url"], mismatch_df["to_url"]))
    mismatch_df["label"] = mismatch_df["pair"].map(
        lambda pair: "TP" if pair in gt_url_pairs else "FP"
    )

    missing_df = gt_detail_df.copy()
    missing_df["pair"] = list(zip(missing_df["from_url"], missing_df["to_url"]))
    missing_df = missing_df[~missing_df["pair"].isin(pred_url_pairs)].copy()
    missing_df["label"] = "FN"

    mismatch_df = pd.concat(
        [mismatch_df.drop(columns=["pair"]), missing_df.drop(columns=["pair"])],
        ignore_index=True,
        sort=False,
    )
    mismatch_df = mismatch_df.drop_duplicates(subset=["from_url", "to_url"])
    mismatch_df = convert_float_int_columns_to_nullable_int(mismatch_df)

    strategy_mismatch_dir = mismatch_root_dir / strategy_name
    strategy_mismatch_dir.mkdir(parents=True, exist_ok=True)
    mismatch_df.to_csv(strategy_mismatch_dir / f"{project}.csv", index=False)
    return score


def calculate_aggregate_score(
    project_label: str,
    experiment_label: str,
    strategy_name: str,
    project_pairs: dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame]],
    mismatch_root_dir: Path,
) -> dict:
    pred_df, gt_df = (
        pd.concat(items, ignore_index=True)
        for items in zip(*project_pairs.values())
    )

    pred_df["project"] = project_label
    gt_df["project"] = project_label
    return calculate_score(project_label, experiment_label, strategy_name, pred_df, gt_df, mismatch_root_dir)


def evaluate_member_experiment(
    *,
    project_directory: Path,
    workspace_directory: Path,
    output_group_name: str,
    experiment_name: str,
    selected_projects: list[str] | None,
) -> tuple[list[dict], dict[str, dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame]]]]:
    ground_truth_dir = project_directory / "data" / experiment_name / "t2p-ground-truth"
    link_root_dir = workspace_directory / "experiment" / experiment_name / "t2p-link"
    mismatch_root_dir = workspace_directory / "experiment" / output_group_name / "t2p-link-metric" / experiment_name

    rows: list[dict] = []
    project_pairs_by_strategy: dict[str, dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame]]] = {}

    if not ground_truth_dir.is_dir():
        print(f"Warning: missing ground-truth directory for experiment {experiment_name}: {ground_truth_dir}")
        return rows, project_pairs_by_strategy

    if not link_root_dir.is_dir():
        print(f"Warning: missing prediction directory for experiment {experiment_name}: {link_root_dir}")
        return rows, project_pairs_by_strategy

    for strategy_dir in sorted(path for path in link_root_dir.iterdir() if path.is_dir()):
        strategy_name = strategy_dir.name
        project_pairs = project_pairs_by_strategy.setdefault(strategy_name, {})
        pred_files = list_csv_files(strategy_dir, selected_projects, strict=False)
        if selected_projects is not None:
            available_projects = {path.stem for path in strategy_dir.rglob("*.csv")}
            for project in selected_projects:
                if project not in available_projects:
                    print(
                        "Info: selected project "
                        f"{project!r} has no prediction CSV for experiment {experiment_name}, "
                        f"strategy {strategy_name}."
                    )

        for pred_file in pred_files:
            pred_detail_df = load_link_df(pred_file)
            project = pred_file.stem
            gt_file = ground_truth_dir / pred_file.name
            if not gt_file.exists() or not str(gt_file.stem):
                print(
                    f"Warning: missing ground-truth CSV for experiment {experiment_name}, "
                    f"strategy {strategy_name}, project {project}: {gt_file}"
                )
                continue

            gt_detail_df = load_ground_truth_df(gt_file)
            gt_detail_df.dropna(subset=["from_url", "to_url"], inplace=True)
            pred_detail_df = pred_detail_df[pred_detail_df["from_url"].isin(gt_detail_df["from_url"])]

            project_pairs[(experiment_name, project)] = (pred_detail_df, gt_detail_df)
            rows.append(
                calculate_score(
                    project,
                    experiment_name,
                    strategy_name,
                    pred_detail_df,
                    gt_detail_df,
                    mismatch_root_dir,
                )
            )

    return rows, project_pairs_by_strategy


def merge_strategy_pairs(
    aggregate_pairs_by_strategy: dict[str, dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame]]],
    member_pairs_by_strategy: dict[str, dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame]]],
) -> None:
    for strategy_name, member_pairs in member_pairs_by_strategy.items():
        aggregate_pairs_by_strategy.setdefault(strategy_name, {}).update(member_pairs)


def select_group_pairs(
    project_pairs: dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame]],
    member_experiments: list[str],
) -> dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame]]:
    member_set = set(member_experiments)
    return {
        key: pair
        for key, pair in project_pairs.items()
        if key[0] in member_set
    }


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    paths = resolve_experiment_paths(
        getattr(args, "workspace_directory", None),
        args.experiment_name or args.experiment_group,
    )
    config = load_ground_truth_config(args.ground_truth_config)
    selected_groups = resolve_selected_groups(config, args.experiment_group or paths.experiment_name)
    output_file = paths.workspace_directory / "t2p_link_overall_metric.csv"
    (paths.workspace_directory / "experiment" / selected_groups.output_name / "t2p-link-metric").mkdir(
        parents=True,
        exist_ok=True,
    )
    _, selected_projects, _ = resolve_experiment_filters(
        use_filters=args.use_filters,
        projects=args.projects,
    )
    rows = []
    aggregate_pairs_by_strategy: dict[
        str,
        dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame]],
    ] = {}

    member_experiments: list[str] = []
    for group_name in selected_groups.names:
        for experiment_name in resolve_experiment_group(config, group_name):
            if experiment_name not in member_experiments:
                member_experiments.append(experiment_name)

    for experiment_name in member_experiments:
        member_rows, member_pairs_by_strategy = evaluate_member_experiment(
            project_directory=Path(PROJECT_DIRECTORY),
            workspace_directory=paths.workspace_directory,
            output_group_name=selected_groups.output_name,
            experiment_name=experiment_name,
            selected_projects=selected_projects,
        )
        rows.extend(member_rows)
        merge_strategy_pairs(aggregate_pairs_by_strategy, member_pairs_by_strategy)

    for group_name in selected_groups.names:
        group_has_rows = False
        group_members = resolve_experiment_group(config, group_name)
        aggregate_mismatch_root_dir = (
            paths.workspace_directory
            / "experiment"
            / selected_groups.output_name
            / "t2p-link-metric"
            / group_name
        )
        for strategy_name, project_pairs in aggregate_pairs_by_strategy.items():
            group_pairs = select_group_pairs(project_pairs, group_members)
            if group_pairs:
                group_has_rows = True
                rows.append(
                    calculate_aggregate_score(
                        f"avg-{group_name}",
                        group_name,
                        strategy_name,
                        group_pairs,
                        aggregate_mismatch_root_dir,
                    )
                )

        if not group_has_rows:
            print(
                f"Info: experiment group {group_name} produced no rows "
                f"from members: {', '.join(group_members)}"
            )

    result_df = pd.DataFrame(rows)
    if result_df.empty:
        print(
            "No results: experiment groups="
            f"{', '.join(selected_groups.names)}, members={', '.join(member_experiments)}"
        )
        return
    result_df = convert_float_int_columns_to_nullable_int(result_df)
    result_df = result_df.reindex(columns=METRIC_COLUMNS)
    result_df = result_df.sort_values(["experiment", "project", "strategy"]).reset_index(drop=True)
    result_df.to_csv(output_file, index=False)


if __name__ == "__main__":
    main()
