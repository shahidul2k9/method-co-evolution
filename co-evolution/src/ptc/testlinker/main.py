from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
from mhc.util import parse_project_index

from ptc.experiment_util import build_experiment_parser, resolve_experiment_paths
from ptc.testlinker.execute import execute_project
from ptc.testlinker.postprocess import METHOD_RESOLVERS, postprocess_project
from ptc.testlinker.preprocess import preprocess_project


def build_parser() -> argparse.ArgumentParser:
    parser = build_experiment_parser(
        "Run TestLinker for a project.",
        include_tools=False,
        include_projects=False,
        include_strategies=False,
        include_filter_toggle=False,
        experiment_help="Experiment name. Defaults to ME_EXPERIMENT_NAME.",
    )
    parser.add_argument("command", choices=["testlinker"], help="Command to execute.")
    parser.add_argument(
        "--stage",
        choices=["preprocess", "execute", "postprocess", "all"],
        default="all",
        help="Pipeline stage to run.",
    )
    parser.add_argument(
        "--project-directory",
        dest="project_directory",
        default=None,
        help=(
            "Project root directory (ME_PROJECT_DIRECTORY). Used to locate "
            "data/ground-truth/ and data/testlinker/class-mapping/."
        ),
    )
    parser.add_argument("--project", default=None, help="Project name.")
    parser.add_argument("--projects", default=None, help="Comma-separated project names.")
    parser.add_argument(
        "--project-index",
        default=None,
        help="Python-style project index or slice from <workspace-directory>/experiment/<experiment>/project.csv. "
        "Examples: '10', '-1', '10:20', ':10', '10:', ':'.",
    )
    parser.add_argument("--top-k", dest="top_k", type=int, default=1, help="Number of invocations to select.")
    parser.add_argument("--model-name-or-path", default=None, help="CodeT5 base model directory.")
    parser.add_argument("--checkpoint-directory", default=None, help="Directory containing pytorch_model.bin.")
    parser.add_argument("--checkpoint", default="best-acc_and_f1", help="Checkpoint name used by the default layout.")
    parser.add_argument(
        "--method-resolver",
        choices=METHOD_RESOLVERS,
        default="testlinker",
        help=(
            "Method resolving modes to run (default: testlinker). "
            "testlinker applies the TestLinker signature mapping algorithm. "
            "testlinkerv2 uses direct URL matching from the symbol solver. "
            "all computes output for both."
        ),
    )
    parser.add_argument("--eval-batch-size", type=int, default=16)
    parser.add_argument("--max-source-length", type=int, default=512)
    parser.add_argument(
        "--tokenizer-mode",
        choices=["original", "auto", "fallback"],
        default="original",
        help="Tokenizer loading mode. Use original for paper-faithful runs; auto/fallback are compatibility modes.",
    )
    parser.add_argument(
        "--include-labels",
        action="store_true",
        help="Include labels from ground-truth/<project>.csv when present.",
    )
    parser.add_argument(
        "--order-production-method",
        choices=["candidate", "testlinker"],
        default="candidate",
        help="Order input invocations by candidate CSV order or TestLinker author detail JSON order.",
    )
    parser.add_argument(
        "--order-production-directory",
        default=None,
        help="Directory containing <project>_detail.json files for --order-production-method testlinker. "
        "Defaults to testlinker/code/result/TestLink.",
    )
    parser.add_argument("--no-cuda", action="store_true", help="Force CPU inference.")
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Re-run stages even when output files already exist.",
    )

    return parser


def _parse_projects_csv(projects: str | None) -> list[str]:
    if not projects:
        return []
    return [project.strip() for project in projects.split(",") if project.strip()]


def _load_repository_projects(workspace_directory: str | Path) -> list[str]:
    repository_file = Path(workspace_directory) / "project.csv"
    if not repository_file.exists():
        raise ValueError(f"repository index does not exist: {repository_file}")

    repository_df = pd.read_csv(repository_file)
    if "project" not in repository_df.columns:
        raise ValueError(f"repository index is missing project column: {repository_file}")
    return repository_df["project"].dropna().astype(str).tolist()


def _resolve_projects(args: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    provided_selection_count = sum(
        value is not None for value in (args.project, args.projects, args.project_index)
    )
    if provided_selection_count != 1:
        parser.error("exactly one of --project, --projects, or --project-index is required")

    if args.project is not None:
        return [args.project]
    if args.projects is not None:
        projects = _parse_projects_csv(args.projects)
        if not projects:
            parser.error("--projects must include at least one project")
        return projects

    try:
        return parse_project_index(args.project_index, _load_repository_projects(args.experiment_directory))
    except ValueError as exc:
        parser.error(str(exc))


def _run_project(args: argparse.Namespace, project: str) -> None:
    print(f"Running TestLinker for project: {project}")

    if args.stage in {"preprocess", "all"}:
        preprocess_df = preprocess_project(
            experiment_directory=args.experiment_directory,
            project=project,
            include_labels=args.include_labels,
            order_production_method=args.order_production_method,
            order_production_directory=args.order_production_directory,
            replace=args.replace,
            project_directory=args.project_directory,
        )
        print(f"Wrote TestLinker input rows: {len(preprocess_df)}")

    if args.stage in {"execute", "all"}:
        execute_df = execute_project(experiment_directory=args.experiment_directory, project=project,
                                     model_name_or_path=args.model_name_or_path,
                                     checkpoint_directory=args.checkpoint_directory,
                                     checkpoint_workspace_directory=args.checkpoint_workspace_directory,
                                     checkpoint=args.checkpoint, eval_batch_size=args.eval_batch_size,
                                     max_source_length=args.max_source_length, tokenizer_mode=args.tokenizer_mode,
                                     no_cuda=args.no_cuda, replace=args.replace)
        print(f"Wrote model output rows: {len(execute_df)}")

    if args.stage in {"postprocess", "all"}:
        postprocess_results = postprocess_project(experiment_directory=args.experiment_directory, project=project,
                                                  top_k=args.top_k,
                                                  method_resolver=args.method_resolver,
                                                  model_name_or_path=args.model_name_or_path, replace=args.replace)
        for mode, mode_df in postprocess_results.items():
            print(f"Wrote TestLinker [{mode}] prediction rows: {len(mode_df)}")


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    paths = resolve_experiment_paths(args.workspace_directory, args.experiment_name)
    args.experiment_directory = str(paths.experiment_directory)
    args.workspace_directory = str(paths.workspace_directory)
    args.checkpoint_workspace_directory = str(paths.workspace_directory)
    if args.top_k <= 0:
        parser.error("--top-k must be a positive integer")

    for project in _resolve_projects(args, parser):
        _run_project(args, project)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
