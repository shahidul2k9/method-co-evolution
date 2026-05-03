from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

import pandas as pd

from ptc.testlinker.paths import (
    class_map_directory,
    input_csv_path,
    projects_all_functions_directory,
    t2p_ground_truth_updated_file,
    testlinker_root,
)
from ptc.testlinker.signatures import compact_signature, invocation_name, split_signature_params


INPUT_COLUMNS = [
    "project",
    "test_id",
    "test_name",
    "test_path",
    "body",
    "invocation",
    "signature",
    "candidate_name",
    "params_json",
    "detail_sigs_json",
    "label",
    "label_json",
    "from_url",
    "candidate_url",
]


def generate_mapping_files(
    cache_directory: str | Path,
    project: str,
    testlinker_directory: str | Path | None = None,
    project_directory: str | Path | None = None,
) -> None:
    """Generate TestLinker mapping files from our class/method scan data."""
    cache_root = Path(cache_directory)
    root = testlinker_root(cache_root, testlinker_directory)

    class_file = cache_root / "data" / "class" / f"{project}.csv"
    method_file = cache_root / "data" / "method" / f"{project}.csv"

    cls_map_dir = class_map_directory(root)
    functions_dir = projects_all_functions_directory(root)
    cls_map_dir.mkdir(parents=True, exist_ok=True)
    functions_dir.mkdir(parents=True, exist_ok=True)

    if project_directory:
        _copy_class_mapping_files(Path(project_directory), cls_map_dir)

    _generate_class_map_files(class_file, cls_map_dir, project)
    _generate_functions_file(method_file, functions_dir, project)


def _copy_class_mapping_files(project_dir: Path, cls_map_dir: Path) -> None:
    source_dir = project_dir / "data" / "testlinker" / "class-mapping"
    if not source_dir.exists():
        return
    for src_file in source_dir.iterdir():
        if src_file.is_file():
            shutil.copy2(src_file, cls_map_dir / src_file.name)


def _generate_class_map_files(class_file: Path, class_map_dir: Path, project: str) -> None:
    class_list: dict[str, list[str]] = {}
    class_list_fqn: dict[str, list[str]] = {}

    if class_file.exists():
        try:
            class_df = pd.read_csv(class_file, keep_default_na=False, na_filter=False)
        except Exception:
            class_df = pd.DataFrame()
        for row in class_df.to_dict(orient="records"):
            name = str(row.get("name", "") or "").strip()
            fqn = str(row.get("fqn", "") or "").strip()
            parent_names = str(row.get("parent_names", "") or "").strip()
            if not name:
                continue
            if parent_names:
                existing = class_list.setdefault(name, [])
                for p in (p.strip() for p in parent_names.split("|") if p.strip()):
                    if p not in existing:
                        existing.append(p)
            if fqn:
                existing_fqns = class_list_fqn.setdefault(name, [])
                if fqn not in existing_fqns:
                    existing_fqns.append(fqn)

    _write_json_single_line(class_map_dir / f"{project}_class_list.json", class_list)
    _write_json_single_line(class_map_dir / f"{project}_class_list_fqn.json", class_list_fqn)


def _generate_functions_file(method_file: Path, functions_dir: Path, project: str) -> None:
    # method_name → class_prefix → set of (method_name, tuple(params)) for dedup
    seen: dict[str, dict[str, set[tuple[str, ...]]]] = {}
    all_functions: dict[str, dict[str, list[dict[str, list[str]]]]] = {}

    if method_file.exists():
        try:
            method_df = pd.read_csv(method_file, keep_default_na=False, na_filter=False)
        except Exception:
            method_df = pd.DataFrame()
        for row in method_df.to_dict(orient="records"):
            sig = _best_method_signature(row)
            if not sig or "(" not in sig:
                continue
            paren_idx = sig.index("(")
            owner_and_name = sig[:paren_idx]
            params_str = sig[paren_idx + 1:].rstrip(")")
            params = [_simple_param(p.strip()) for p in params_str.split(",") if p.strip()] if params_str.strip() else []

            dot_idx = owner_and_name.rfind(".")
            if dot_idx < 0:
                continue
            method_name = owner_and_name[dot_idx + 1:]
            class_prefix = owner_and_name[:dot_idx]
            if not method_name or not class_prefix:
                continue

            key = (method_name, tuple(params))
            if key in seen.setdefault(method_name, {}).setdefault(class_prefix, set()):
                continue
            seen[method_name][class_prefix].add(key)
            all_functions.setdefault(method_name, {}).setdefault(class_prefix, []).append(
                {method_name: params}
            )

    _write_json_single_line(functions_dir / f"{project}_all_functions_full.json", all_functions)


def _best_method_signature(row: dict[str, object]) -> str:
    for col in ("testlinker_fqs", "fqs_alt", "fqs"):
        val = str(row.get(col, "") or "").strip()
        if val and "(" in val:
            return val
    return ""


def _simple_param(type_name: str) -> str:
    type_name = re.sub(r"<.*>", "", type_name).strip()
    if type_name.endswith("..."):
        type_name = type_name[:-3] + "[]"
    return type_name.split(".")[-1]


def _write_json_single_line(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, ensure_ascii=True), encoding="utf-8")


def preprocess_project(
    *,
    cache_directory: str | Path,
    project: str,
    testlinker_directory: str | Path | None = None,
    include_labels: bool = False,
    order_production_method: str = "candidate",
    order_production_directory: str | Path | None = None,
    mapping_mode: str = "testlinker-heuristics",
    replace: bool = False,
    project_directory: str | Path | None = None,
) -> pd.DataFrame:
    cache_root = Path(cache_directory)
    root = testlinker_root(cache_root, testlinker_directory)

    output_file = input_csv_path(root, project)
    if not replace and output_file.exists():
        return pd.read_csv(output_file, keep_default_na=False, na_filter=False)

    generate_mapping_files(cache_directory, project, testlinker_directory, project_directory)
    candidate_file = cache_root / "data" / "t2p-candidate" / f"{project}.csv"
    if not candidate_file.exists():
        raise FileNotFoundError(f"Candidate file not found: {candidate_file}")

    method_code_file = cache_root / "data" / "method-code" / f"{project}.csv"
    method_code_lookup = _load_method_code_lookup(method_code_file)
    label_lookup = _load_label_lookup(t2p_ground_truth_updated_file(project_directory or cache_root, project)) if include_labels else {}
    invocation_order_lookup = _load_invocation_order_lookup(project, order_production_method, order_production_directory)
    candidate_df = pd.read_csv(candidate_file, keep_default_na=False, na_filter=False)
    required_columns = {"project", "from_url", "from_name", "from_file", "to_url", "to_name"}
    missing_columns = required_columns.difference(candidate_df.columns)
    if missing_columns:
        raise ValueError(f"Candidate file {candidate_file} is missing columns: {sorted(missing_columns)}")

    rows = []
    for index, (from_url, group_df) in enumerate(candidate_df.groupby("from_url", sort=False), start=1):
        group_df = group_df.reset_index(drop=True)
        first_row = group_df.iloc[0]
        test_id = f"{index:06d}"
        body = _strip_method_declaration(method_code_lookup.get(from_url, ""))
        label_payload = label_lookup.get(from_url, {"signatures": [], "urls": set()})
        labels = list(label_payload["signatures"])
        label_urls = set(label_payload["urls"])
        seen_rows: set[tuple[str, str]] = set()
        test_rows = []

        for candidate_row in group_df.to_dict(orient="records"):
            signature = _candidate_signature(candidate_row)
            if not signature:
                continue
            signature = compact_signature(signature)
            method_name = invocation_name(signature) or candidate_row.get("to_name", "")
            to_url = candidate_row.get("to_url", "")
            dedupe_key = (signature, to_url)
            if dedupe_key in seen_rows:
                continue
            seen_rows.add(dedupe_key)

            params = split_signature_params(signature)
            test_rows.append(
                {
                    "project": project,
                    "test_id": test_id,
                    "from_url": from_url,
                    "test_name": first_row.get("from_name", ""),
                    "test_path": _test_path(first_row),
                    "body": body,
                    "invocation": method_name,
                    "signature": signature,
                    "candidate_url": to_url,
                    "candidate_name": candidate_row.get("to_name", ""),
                    "params_json": json.dumps(params, ensure_ascii=True),
                    "detail_sigs_json": json.dumps([signature], ensure_ascii=True),
                    "label": 1 if to_url in label_urls else 0,
                    "label_json": json.dumps(labels, ensure_ascii=True),
                }
            )
        rows.extend(_order_rows_by_invocation(test_rows, invocation_order_lookup.get(str(first_row.get("from_name", "")))))

    input_df = pd.DataFrame(rows, columns=INPUT_COLUMNS)
    output_file = input_csv_path(root, project)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    input_df.to_csv(output_file, index=False)
    return input_df


def _load_method_code_lookup(method_code_file: Path) -> dict[str, str]:
    if not method_code_file.exists():
        return {}

    method_code_df = pd.read_csv(method_code_file, keep_default_na=False, na_filter=False)
    if "url" not in method_code_df.columns or "code" not in method_code_df.columns:
        return {}

    return {
        row["url"]: row["code"]
        for row in method_code_df.to_dict(orient="records")
        if row.get("url")
    }


def _load_label_lookup(ground_truth_path: Path) -> dict[str, dict[str, object]]:
    if not ground_truth_path.exists():
        return {}

    ground_truth_df = pd.read_csv(ground_truth_path, keep_default_na=False, na_filter=False)
    required_columns = {"from_url", "to_url"}
    if not required_columns.issubset(ground_truth_df.columns):
        return {}

    label_lookup: dict[str, dict[str, object]] = {}
    for row in ground_truth_df.to_dict(orient="records"):
        from_url = str(row.get("from_url", "") or "")
        to_url = str(row.get("to_url", "") or "")
        label = compact_signature(row.get("to_fqs_alt", ""))
        if not from_url or not to_url:
            continue
        payload = label_lookup.setdefault(from_url, {"signatures": [], "urls": set()})
        payload["urls"].add(to_url)
        if label and label not in payload["signatures"]:
            payload["signatures"].append(label)
    return label_lookup


def _load_invocation_order_lookup(
    project: str,
    order_production_method: str,
    order_production_directory: str | Path | None,
) -> dict[str, list[str]]:
    if order_production_method == "candidate":
        return {}
    if order_production_method != "testlinker":
        raise ValueError("--order-production-method must be one of: candidate, testlinker")

    result_directory = Path(order_production_directory or "testlinker/code/result/TestLink")
    detail_file = result_directory / f"{project}_detail.json"
    if not detail_file.exists():
        return {}

    order_lookup: dict[str, list[str]] = {}
    for line in detail_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        test_name = str(payload.get("test_name", "") or "")
        invocations = payload.get("invocations", [])
        if test_name and isinstance(invocations, list):
            order_lookup[test_name] = [str(invocation) for invocation in invocations]
    return order_lookup


def _order_rows_by_invocation(rows: list[dict[str, object]], invocation_order: list[str] | None) -> list[dict[str, object]]:
    if not invocation_order:
        return rows

    order_index = {invocation: index for index, invocation in enumerate(invocation_order)}
    indexed_rows = list(enumerate(rows))
    return [
        row
        for _, row in sorted(
            indexed_rows,
            key=lambda item: (order_index.get(str(item[1].get("invocation", "")), len(order_index)), item[0]),
        )
    ]


def _strip_method_declaration(code: str) -> str:
    code = str(code or "")
    brace_index = code.find("{")
    if brace_index < 0:
        return code
    return code[brace_index:].strip()


def _candidate_signature(row: dict[str, object]) -> str:
    for column in ("to_fqs_alt", "to_fqs", "to_fqn", "to_name"):
        value = str(row.get(column, "") or "").strip()
        if value:
            return value
    return ""


def _test_path(row: pd.Series) -> str:
    from_fqn = str(row.get("from_fqn", "") or "")
    if "." in from_fqn:
        return from_fqn.rsplit(".", maxsplit=1)[0].replace(".", "/")

    from_file = str(row.get("from_file", "") or "")
    if from_file.endswith(".java"):
        return from_file[:-len(".java")].replace("/", ".")
    return from_file
