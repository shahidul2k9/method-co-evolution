import re
import warnings
from pathlib import Path

import pandas as pd

from mhc.artifacts import is_main_code, is_test_case_method
from ptc.constants import MethodChangeType

REVISION_METHOD_KINDS = ["test-case-method", "main-code"]
TEST_REVISION_METHOD_KIND = "test-case-method"
PRODUCTION_REVISION_METHOD_KIND = "main-code"


def filter_concrete_methods(df: pd.DataFrame) -> pd.DataFrame:
    abstract = (
        pd.to_numeric(df["abstract"], errors="coerce")
        if "abstract" in df.columns
        else pd.Series(float("nan"), index=df.index)
    )
    invalid = abstract.isna() | ~abstract.isin([0, 1])
    if invalid.any():
        if "project" in df.columns:
            for project, project_df in df.groupby("project", dropna=False, sort=False):
                project_invalid_count = int(invalid.loc[project_df.index].sum())
                if project_invalid_count:
                    warnings.warn(
                        f"project={project}: {project_invalid_count} invalid abstract values "
                        f"out of {len(project_df)} methods."
                    )
        else:
            warnings.warn(
                f"project=<unknown>: {int(invalid.sum())} invalid abstract values "
                f"out of {len(df)} methods."
            )

    return df[~invalid & (abstract == 0)].copy()


def classify_revision_method_kind(artifact: str | None) -> str | None:
    if is_test_case_method(artifact):
        return TEST_REVISION_METHOD_KIND
    if is_main_code(artifact):
        return PRODUCTION_REVISION_METHOD_KIND
    return None


def filter_revision_method_population(
    df: pd.DataFrame,
    *,
    filter_trivial_production: bool = True,
) -> pd.DataFrame:
    filtered_df = filter_revision_method_base_population(df)
    if filter_trivial_production and "code" in filtered_df.columns:
        filtered_df, _ = filter_trivial_production_methods(filtered_df)
    return filtered_df


def filter_revision_method_population_with_code(
    df: pd.DataFrame,
    experiment_directory: Path,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    if "project" not in df.columns:
        raise ValueError("method-history data must include a project column for RQ3 filtering.")

    filtered_project_dfs = []
    for project, project_df in df.groupby("project", dropna=False, sort=False):
        if pd.isna(project) or str(project) == "":
            raise ValueError("method-history data contains rows without a project value.")
        project_name = str(project)
        base_df = filter_revision_method_base_population(project_df)
        joined_df, _ = join_method_code_for_project(
            base_df,
            Path(experiment_directory),
            project_name,
        )
        final_df, _ = filter_trivial_production_methods(joined_df)
        filtered_project_dfs.append(final_df)

    if not filtered_project_dfs:
        return pd.DataFrame(columns=df.columns)
    return pd.concat(filtered_project_dfs, ignore_index=True)


def filter_revision_method_base_population(df: pd.DataFrame) -> pd.DataFrame:
    filtered_df = filter_concrete_methods(df)
    filtered_df["method_kind"] = filtered_df["artifact"].map(classify_revision_method_kind)
    return filtered_df[filtered_df["method_kind"].isin(REVISION_METHOD_KINDS)].copy()


def load_filtered_artifact_df(experiment_directory: Path, project: str) -> pd.DataFrame:
    artifact_file = Path(experiment_directory) / "method-artifact-filtered" / f"{project}.csv"
    if not artifact_file.exists():
        raise FileNotFoundError(
            f"Missing filtered artifact CSV for project={project}: {artifact_file}. "
            "Run ptc.generator.filter_artifact before RQ3 revision plots/statistics."
        )
    return pd.read_csv(
        artifact_file,
        keep_default_na=False,
        na_filter=False,
        low_memory=False,
    )


def join_filtered_artifacts(df: pd.DataFrame, experiment_directory: Path) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    if "project" not in df.columns or "url" not in df.columns:
        raise ValueError("method-history data must include project and url columns to join filtered artifacts.")

    joined_project_dfs = []
    for project, project_df in df.groupby("project", dropna=False, sort=False):
        if pd.isna(project) or str(project) == "":
            raise ValueError("method-history data contains rows without a project value.")
        artifact_df = load_filtered_artifact_df(Path(experiment_directory), str(project))
        artifact_columns = [
            column
            for column in ["url", "method_kind"]
            if column in artifact_df.columns
        ]
        if "url" not in artifact_columns or "method_kind" not in artifact_columns:
            raise ValueError(f"Filtered artifact CSV for project={project} must include url and method_kind columns.")
        joined_df = pd.merge(
            project_df,
            artifact_df[artifact_columns].drop_duplicates(subset=["url"]),
            on="url",
            how="inner",
        )
        joined_project_dfs.append(joined_df)
    if not joined_project_dfs:
        return pd.DataFrame(columns=df.columns)
    return pd.concat(joined_project_dfs, ignore_index=True)


def load_method_code_df(experiment_directory: Path, project: str) -> pd.DataFrame:
    code_file = experiment_directory / "method-code" / f"{project}.csv"
    if not code_file.exists():
        raise FileNotFoundError(
            f"Missing method-code CSV for project={project}: {code_file}. "
            "RQ3 revision filtering requires method-code for getter/setter and empty-method removal."
        )
    return pd.read_csv(
        code_file,
        usecols=["url", "code"],
        keep_default_na=False,
        na_filter=False,
        low_memory=False,
    ).drop_duplicates(subset=["url"])


def join_method_code(df: pd.DataFrame, experiment_directory: Path) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    if "project" not in df.columns or "url" not in df.columns:
        raise ValueError("method-history data must include project and url columns to join method-code.")

    joined_project_dfs = []
    for project, project_df in df.groupby("project", dropna=False, sort=False):
        if pd.isna(project) or str(project) == "":
            raise ValueError("method-history data contains rows without a project value.")
        joined_df, _ = join_method_code_for_project(project_df, Path(experiment_directory), str(project))
        joined_project_dfs.append(joined_df)
    return pd.concat(joined_project_dfs, ignore_index=True)


def join_method_code_for_project(
    project_df: pd.DataFrame,
    experiment_directory: Path,
    project: str,
) -> tuple[pd.DataFrame, int]:
    method_code_df = load_method_code_df(Path(experiment_directory), project)
    joined_df = pd.merge(
        project_df,
        method_code_df,
        on="url",
        how="left",
    )
    missing_code_count = int((joined_df["code"].isna() | joined_df["code"].eq("")).sum())
    if missing_code_count:
        warnings.warn(
            f"Dropping {missing_code_count} method-history rows with missing method code "
            f"in project={project}."
        )
        joined_df = joined_df[~(joined_df["code"].isna() | joined_df["code"].eq(""))].copy()
    return joined_df, missing_code_count


def filter_trivial_production_methods(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if df.empty or "code" not in df.columns:
        return df.copy(), 0
    trivial_production = (
        df["method_kind"].eq(PRODUCTION_REVISION_METHOD_KIND)
        & df.apply(is_trivial_production_method, axis=1)
    )
    return df[~trivial_production].copy(), int(trivial_production.sum())


def is_trivial_production_method(row: pd.Series | dict) -> bool:
    code = str(row.get("code", "") or "")
    if is_empty_method_code(code):
        return True
    return is_short_accessor_method(row)


def is_empty_method_code(code: str | None) -> bool:
    stripped = str(code or "").strip()
    if not stripped:
        return True
    if stripped.endswith(";") and "{" not in stripped:
        return True
    return not ("{" in stripped and "}" in stripped)


def is_short_accessor_method(row: pd.Series | dict) -> bool:
    name = str(row.get("name", "") or "")
    if not (name.startswith("get") or name.startswith("set")):
        return False
    if method_line_count(row) >= 5:
        return False

    code = str(row.get("code", "") or "")
    parameter_count = method_parameter_count(code, name)
    return_type = method_return_type(code, name)
    if name.startswith("get"):
        return parameter_count == 0 and return_type is not None and return_type != "void"
    return parameter_count == 1 and return_type == "void"


def method_line_count(row: pd.Series | dict) -> int:
    start_line = pd.to_numeric(row.get("start_line"), errors="coerce")
    end_line = pd.to_numeric(row.get("end_line"), errors="coerce")
    if pd.notna(start_line) and pd.notna(end_line):
        return max(int(end_line) - int(start_line) + 1, 0)
    return len(str(row.get("code", "") or "").splitlines())


def method_parameter_count(code: str, method_name: str) -> int | None:
    match = re.search(rf"\b{re.escape(method_name)}\s*\((?P<parameters>[^)]*)\)", code, flags=re.S)
    if match is None:
        return None
    parameters = match.group("parameters").strip()
    if not parameters:
        return 0
    return len([parameter for parameter in parameters.split(",") if parameter.strip()])


def method_return_type(code: str, method_name: str) -> str | None:
    match = re.search(rf"(?P<prefix>.*?)\b{re.escape(method_name)}\s*\(", code, flags=re.S)
    if match is None:
        return None
    prefix = re.sub(r"@\w+(?:\([^)]*\))?", " ", match.group("prefix"))
    tokens = re.findall(r"[A-Za-z_$][\w$]*(?:\[\])*|[A-Za-z_$][\w$]*<[^>]+>", prefix)
    if not tokens:
        return None
    while tokens and tokens[-1] in {"public", "protected", "private", "static", "final", "abstract", "synchronized", "native", "strictfp", "default"}:
        tokens.pop()
    return tokens[-1] if tokens else None


def extract_change_count(history_json) -> dict[str, int]:
    change_commits = history_json["changeHistoryDetails"]
    change_history = {f"ch_{ct.name.lower()}": 0 for ct in MethodChangeType}
    diff_commit_count = 0
    for commit_hash, commit_detail in change_commits.items():
        changes = {p.strip() for p in re.split(r'[(),]', commit_detail['type']) if
                   p.strip()}
        for change_type in changes:
            change_history[f"ch_{MethodChangeType(change_type).name.lower()}"] += 1
        if "diff" in commit_detail and commit_detail['diff']:
            diff_commit_count += 1
        elif "subchanges" in commit_detail:
            for subchange in commit_detail['subchanges']:
                if "diff" in subchange and subchange['diff']:
                    diff_commit_count += 1
                    break

    change_history["ch_all"] = len(change_commits)
    change_history["ch_diff"] = diff_commit_count
    return change_history
