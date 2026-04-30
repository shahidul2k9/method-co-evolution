from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from ptc.testlinker.signatures import invocation_name

AUTHOR_RESULT_COLUMNS = [
    "project",
    "id",
    "test_name",
    "recom_by",
    "is_recom_all",
    "invocation",
    "invocation_order",
    "sorted_rank",
    "label",
    "pred_label",
    "recom_signature",
    "labels_json",
    "sorted_invocations_json",
]


def convert_author_result_directory(
        *,
        input_directory: str | Path,
        output_directory: str | Path | None = None,
        project: str | None = None,
) -> list[Path]:
    input_root = Path(input_directory)
    output_root = Path(output_directory) if output_directory else input_root
    json_files = _author_result_files(input_root, project)
    output_root.mkdir(parents=True, exist_ok=True)

    output_files = []
    for json_file in json_files:
        output_file = output_root / f"{_project_name(json_file)}_detail_invocations.csv"
        convert_author_result_file(input_file=json_file, output_file=output_file)
        output_files.append(output_file)
    return output_files


def convert_author_result_file(*, input_file: str | Path, output_file: str | Path) -> Path:
    input_path = Path(input_file)
    output_path = Path(output_file)
    project = _project_name(input_path)
    rows = []

    with input_path.open(encoding="utf-8") as reader:
        for line in reader:
            if not line.strip():
                continue
            item = json.loads(line)
            rows.extend(_rows_for_test(project, item))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", newline="") as writer_handle:
        writer = csv.DictWriter(writer_handle, fieldnames=AUTHOR_RESULT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def _author_result_files(input_root: Path, project: str | None) -> list[Path]:
    if project:
        file_path = input_root / f"{project}_detail.json"
        if not file_path.exists():
            raise FileNotFoundError(f"TestLinker author result JSON not found: {file_path}")
        return [file_path]
    return sorted(input_root.glob("*_detail.json"))


def _rows_for_test(project: str, item: dict[str, object]) -> list[dict[str, object]]:
    labels = list(item.get("labels") or [])
    labels_set = set(labels)
    label_names = {invocation_name(str(label)) for label in labels}
    recom_signatures = [str(signature) for signature in item.get("recom_signatures") or []]
    recom_signatures_by_invocation = _signatures_by_invocation(recom_signatures)
    sorted_invocations = list(item.get("sorted_invocations") or [])
    sorted_rank = {name: rank for rank, name in enumerate(sorted_invocations, start=1)}

    rows = []
    invocations = list(item.get("invocations") or [])
    for order, invocation in enumerate(invocations, start=1):
        recommendations_for_rows = recom_signatures_by_invocation.get(invocation) or [""]
        for recom_signature in recommendations_for_rows:
            rows.append(
                {
                    "project": project,
                    "id": item.get("id", ""),
                    "test_name": item.get("test_name", ""),
                    "recom_by": item.get("recom_by", ""),
                    "is_recom_all": item.get("is_recom_all", ""),
                    "invocation": invocation,
                    "invocation_order": order,
                    "sorted_rank": sorted_rank.get(invocation, ""),
                    "label": int(invocation in label_names),
                    "pred_label": int(bool(recom_signature and recom_signature in labels_set)),
                    "recom_signature": recom_signature,
                    "labels_json": json.dumps(item.get("labels") or [], ensure_ascii=True),
                    "sorted_invocations_json": json.dumps(sorted_invocations, ensure_ascii=True),
                }
            )
    return rows


def _signatures_by_invocation(signatures: list[str]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for signature in signatures:
        grouped.setdefault(invocation_name(signature), []).append(signature)
    return grouped


def _project_name(path: Path) -> str:
    return path.name.removesuffix("_detail.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Convert TestLinker author result JSON into invocation-level CSV.")
    parser.add_argument(
        "--input-directory",
        default="testlinker/code/result/TestLink",
        help="Directory containing author <project>_detail.json result files.",
    )
    parser.add_argument(
        "--output-directory",
        default=None,
        help="Directory for converted CSV files. Defaults to --input-directory.",
    )
    parser.add_argument("--project", default=None, help="Convert a single project.")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_files = convert_author_result_directory(
        input_directory=args.input_directory,
        output_directory=args.output_directory,
        project=args.project,
    )
    for output_file in output_files:
        print(f"Wrote expanded TestLinker author result CSV: {output_file}")
    return 0


if __name__ == "__main__":
    # raise SystemExit(main())
    raise SystemExit(main([
        "--input-directory", f"{Path.cwd()}/testlinker/code/result/TestLink"
    ]))
