from __future__ import annotations

import json
import warnings
from pathlib import Path

import pandas as pd

from ptc.testlinker.mapping import apply_signature_mapping
from ptc.testlinker.paths import (
    class_map_directory,
    model_name_from_name_or_path,
    model_output_csv_path,
    postprocess_output_path,
    projects_all_functions_directory,
    testlinker_root,
)


METHOD_RESOLVERS = ["testlinker", "testlinkerv2", "all"]


def postprocess_project(
    *,
    experiment_directory: str | Path,
    project: str,
    top_k: int = 1,
    method_resolver: str | None = None,
    model_name_or_path: str | Path | None = None,
    replace: bool = False,
) -> dict[str, pd.DataFrame]:
    if method_resolver is None or method_resolver == "all":
        method_resolvers = ["testlinker", "testlinkerv2"]
    else:
        method_resolvers = [method_resolver]

    root = testlinker_root(experiment_directory)
    model_name = model_name_from_name_or_path(model_name_or_path)

    if not replace:
        results = {}
        pending_resolvers = []
        for resolver in method_resolvers:
            output_file = postprocess_output_path(root, project, resolver, model_name=model_name)
            if output_file.exists():
                results[resolver] = pd.read_csv(output_file, keep_default_na=False, na_filter=False)
            else:
                pending_resolvers.append(resolver)
        if not pending_resolvers:
            return results
        method_resolvers = pending_resolvers
    else:
        results = {}

    model_csv = model_output_csv_path(root, project, model_name)
    if not model_csv.exists():
        raise FileNotFoundError(f"Model output CSV not found: {model_csv}. Run the execute stage first.")
    model_df = pd.read_csv(model_csv, keep_default_na=False, na_filter=False)

    for resolver in method_resolvers:
        if resolver == "testlinkerv2":
            output_df = _predict_with_rank(model_df, top_k)
        elif resolver == "testlinker":
            _warn_if_mapping_files_missing(root=root, project=project)
            output_df = _predict_with_mapping(model_df, root=root, project=project, top_k=top_k)
        else:
            raise NotImplementedError(f"Not implemented resolver: {resolver}")

        output_file = postprocess_output_path(root, project, resolver, model_name=model_name)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_df.to_csv(output_file, index=False)
        results[resolver] = output_df

    return results


def _predict_with_rank(model_df: pd.DataFrame, top_k: int) -> pd.DataFrame:
    output_df = model_df.copy()
    selected = pd.to_numeric(output_df["rank"], errors="coerce") <= top_k
    output_df["recommender"] = selected.map({True: "model", False: ""})
    output_df["label_pred"] = selected.astype(int)
    return output_df


def _predict_with_mapping(model_df: pd.DataFrame, *, root: Path, project: str, top_k: int) -> pd.DataFrame:
    output_df = model_df.copy()
    output_df["recommender"] = ""
    output_df["label_pred"] = 0

    for _, group_df in model_df.groupby("from_url", sort=False):
        mapped_example = apply_signature_mapping(
            [_csv_rows_to_mapping_example(group_df)],
            class_map_dir=class_map_directory(root),
            projects_all_functions_dir=projects_all_functions_directory(root),
            project=project,
        )[0]
        signature_to_urls = _expanded_signature_to_urls(group_df, mapped_example)
        top_rows = group_df.loc[pd.to_numeric(group_df["rank"], errors="coerce") <= top_k]
        recommended_signatures = _recommended_signatures(top_rows, mapped_example)
        predicted_urls = {
            to_url
            for signature in recommended_signatures
            for to_url in signature_to_urls.get(signature, [])
        }
        selected = group_df["to_url"].isin(predicted_urls)
        output_df.loc[group_df.index, "label_pred"] = selected.astype(int)
        output_df.loc[group_df.index[selected], "recommender"] = "model"

    return output_df


def _csv_rows_to_mapping_example(group_df: pd.DataFrame) -> dict[str, object]:
    signatures: dict[str, dict[str, object]] = {}
    for row in group_df.to_dict(orient="records"):
        signature = str(row.get("to_testlinker_fqs", "") or "")
        if not signature:
            continue
        params = _load_params(row.get("to_testlinker_p"))
        signatures[signature] = {
            "params_len": len(params),
            "params": params,
            "detail_sigs": [signature],
        }
    return {"signature": signatures}


def _load_params(value: object) -> list[str]:
    if value is None or value == "":
        return []
    try:
        params = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    return [str(param) for param in params] if isinstance(params, list) else []


def _expanded_signature_to_urls(
    group_df: pd.DataFrame,
    mapped_example: dict[str, object],
) -> dict[str, list[str]]:
    signature_to_urls: dict[str, list[str]] = {}
    mapped_signatures = dict(mapped_example.get("signature", {}))
    for row in group_df.to_dict(orient="records"):
        original_signature = str(row.get("to_testlinker_fqs", "") or "")
        to_url = str(row.get("to_url", "") or "")
        if not original_signature or not to_url:
            continue
        signature_to_urls.setdefault(original_signature, [])
        if to_url not in signature_to_urls[original_signature]:
            signature_to_urls[original_signature].append(to_url)
        payload = mapped_signatures.get(original_signature, {})
        detail_sigs = list(payload.get("detail_sigs", [])) if isinstance(payload, dict) else []
        for detail_sig in detail_sigs:
            signature_to_urls.setdefault(detail_sig, [])
            if to_url not in signature_to_urls[detail_sig]:
                signature_to_urls[detail_sig].append(to_url)
    return signature_to_urls


def _recommended_signatures(top_rows: pd.DataFrame, mapped_example: dict[str, object]) -> list[str]:
    mapped_signatures = dict(mapped_example.get("signature", {}))
    recommended = []
    for signature in top_rows["to_testlinker_fqs"].dropna().astype(str).tolist():
        payload = mapped_signatures.get(signature, {})
        detail_sigs = list(payload.get("detail_sigs", [])) if isinstance(payload, dict) else []
        recommended.extend(detail_sigs or [signature])
    return recommended


def _warn_if_mapping_files_missing(*, root: Path, project: str) -> None:
    required_files = [
        class_map_directory(root) / "java_class_list.json",
        class_map_directory(root) / f"{project}_class_list.json",
        class_map_directory(root) / f"{project}_class_list_fqn.json",
        projects_all_functions_directory(root) / f"{project}_all_functions_full.json",
    ]
    missing_files = [path for path in required_files if not path.exists()]
    if not missing_files:
        return
    warnings.warn(
        f"TestLinker mapping files are missing for {project}; "
        "signature mapping will fall back to unmapped candidate signatures. "
        f"Missing: {', '.join(str(p) for p in missing_files)}",
        RuntimeWarning,
        stacklevel=2,
    )
