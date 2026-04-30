from __future__ import annotations

import argparse
from pathlib import Path

from ptc.testlinker.execute import execute_project
from ptc.testlinker.postprocess import postprocess_project
from ptc.testlinker.preprocess import preprocess_project


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run TestLinker for a project.")
    parser.add_argument("command", choices=["testlinker"], help="Command to execute.")
    parser.add_argument(
        "--stage",
        choices=["preprocess", "execute", "postprocess", "all"],
        default="all",
        help="Pipeline stage to run.",
    )
    parser.add_argument("--cache-directory", required=True, help="Project cache directory.")
    parser.add_argument("--project", default=None, help="Project name.")
    parser.add_argument(
        "--testlinker-directory",
        default=None,
        help="TestLinker runtime directory. Defaults to <cache-directory>/testlinker.",
    )
    parser.add_argument("--top-k", dest="top_k", type=int, default=1, help="Number of invocations to select.")
    parser.add_argument("--model-name-or-path", default=None, help="CodeT5 base model directory.")
    parser.add_argument("--checkpoint-directory", default=None, help="Directory containing pytorch_model.bin.")
    parser.add_argument("--checkpoint", default="best-acc_and_f1", help="Checkpoint name used by the default layout.")
    parser.add_argument(
        "--model-mode",
        choices=["codet5", "heuristic"],
        default="codet5",
        help="Use codet5 for real inference or heuristic for local dry runs/tests.",
    )
    parser.add_argument("--eval-batch-size", type=int, default=16)
    parser.add_argument("--max-source-length", type=int, default=512)
    parser.add_argument(
        "--tokenizer-mode",
        choices=["original", "auto", "fallback"],
        default="original",
        help="Tokenizer loading mode. Use original for paper-faithful runs; auto/fallback are compatibility modes.",
    )
    parser.add_argument("--only-model", action="store_true", help="Skip TestLinker rule-based shortcut.")
    parser.add_argument(
        "--include-labels",
        action="store_true",
        help="Include labels from <testlinker-directory>/ground-truth/<project>.csv when present.",
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
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if not args.project:
        parser.error("--project is required for the testlinker command")
    if args.top_k <= 0:
        parser.error("--top-k must be a positive integer")

    if args.stage in {"preprocess", "all"}:
        preprocess_df = preprocess_project(
            cache_directory=args.cache_directory,
            project=args.project,
            testlinker_directory=args.testlinker_directory,
            include_labels=args.include_labels,
            order_production_method=args.order_production_method,
            order_production_directory=args.order_production_directory,
        )
        print(f"Wrote TestLinker input rows: {len(preprocess_df)}")

    if args.stage in {"execute", "all"}:
        execute_df = execute_project(
            cache_directory=args.cache_directory,
            project=args.project,
            top_k=args.top_k,
            testlinker_directory=args.testlinker_directory,
            model_name_or_path=args.model_name_or_path,
            checkpoint_directory=args.checkpoint_directory,
            checkpoint=args.checkpoint,
            model_mode=args.model_mode,
            eval_batch_size=args.eval_batch_size,
            max_source_length=args.max_source_length,
            tokenizer_mode=args.tokenizer_mode,
            only_model=args.only_model,
            no_cuda=args.no_cuda,
        )
        print(f"Wrote TestLinker execute rows: {len(execute_df)}")

    if args.stage in {"postprocess", "all"}:
        postprocess_df = postprocess_project(
            cache_directory=args.cache_directory,
            project=args.project,
            testlinker_directory=args.testlinker_directory,
        )
        print(f"Wrote TestLinker final prediction rows: {len(postprocess_df)}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
