from __future__ import annotations

import argparse
from pathlib import Path
from mhc.config import *
from ptc.llm.models import GenerationConfig
from ptc.llm.persistence import CsvRunStore
from ptc.llm.prompting import JsonPredictionParser, MethodLinkingPromptFactory
from ptc.llm.providers.huggingface import (
    HuggingFaceProviderConfig,
    HuggingFaceTextGenerationProvider,
)
from ptc.llm.runner import DataFrameMethodLinker


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="LLM-based method linking from t2p or p2t dataframes."
    )
    parser.add_argument(
        "command",
        choices=["llm-m2m-link"],
        help="Command to execute.",
    )
    parser.add_argument(
        "--cache-directory",
        dest="cache_directory",
        required=True,
        help="Cache directory root. The input CSV is resolved from <cache_directory>/data plus project and input kind.",
    )
    parser.add_argument(
        "--project",
        required=True,
        help="Project name used to resolve the input CSV from cache_directory.",
    )
    parser.add_argument(
        "--model-name-or-path",
        dest="model_name_or_path",
        required=True,
        help="Hugging Face model id or local path.",
    )
    parser.add_argument(
        "--short-model-name",
        dest="short_model_name",
        default=None,
        help="Short model directory name for persisted outputs, e.g. gpt_oss_20b.",
    )
    parser.add_argument(
        "--input-kind",
        dest="input_kind",
        choices=["t2p", "p2t"],
        default="t2p",
        help="Use `t2p` for test-to-production or `p2t` for production-to-test.",
    )
    parser.add_argument(
        "--batch-size",
        dest="batch_size",
        type=int,
        default=4,
        help="Grouped method cases per inference batch.",
    )
    parser.add_argument(
        "--resume",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Resume from previous persisted predictions when available.",
    )
    parser.add_argument(
        "--device-map",
        dest="device_map",
        default="auto",
        help="transformers device_map value. Use `none` for default single-device loading.",
    )
    parser.add_argument("--dtype", default="auto", help="transformers dtype value.")
    parser.add_argument("--torch_dtype", dest="dtype", help=argparse.SUPPRESS)
    parser.add_argument(
        "--hf-token",
        dest="hf_token",
        default=HF_TOKEN,
        help="Hugging Face token. Defaults to HF_TOKEN or HUGGINGFACE_HUB_TOKEN.",
    )
    parser.add_argument(
        "--trust-remote-code",
        dest="trust_remote_code",
        action="store_true",
        help="Allow loading Hugging Face models with trust_remote_code=True.",
    )
    parser.add_argument(
        "--max-new-tokens",
        dest="max_new_tokens",
        type=int,
        default=256,
        help="Generation cap per grouped case.",
    )
    parser.add_argument("--temperature", type=float, default=0.0, help="Sampling temperature.")
    parser.add_argument("--top-p", dest="top_p", type=float, default=1.0, help="Sampling top_p.")
    parser.add_argument(
        "--do-sample",
        action="store_true",
        help="Enable sampling. Defaults to greedy decoding.",
    )
    return parser


def main() -> None:
    _require_pandas()
    import pandas as pd

    parser = build_parser()
    args = parser.parse_args()

    input_kind = args.input_kind
    input_path = resolve_input_file(args.cache_directory, args.project, input_kind)
    if not input_path.exists():
        parser.error(f"Input file not found: {input_path}")

    output_root = default_output_root(args.cache_directory)
    run_store = CsvRunStore(
        output_root=output_root,
        input_kind=input_kind,
        model_name_or_path=args.model_name_or_path,
        input_file_name=input_path.name,
        short_model_name=args.short_model_name,
    )

    edge_df = pd.read_csv(input_path, keep_default_na=False, na_filter=False)
    provider = HuggingFaceTextGenerationProvider(
        HuggingFaceProviderConfig(
            model_name_or_path=args.model_name_or_path,
            device_map=args.device_map,
            dtype=args.dtype,
            trust_remote_code=args.trust_remote_code,
            batch_size=args.batch_size,
            token=args.hf_token,
        )
    )
    linker = DataFrameMethodLinker(
        provider=provider,
        prompt_factory=MethodLinkingPromptFactory(),
        parser=JsonPredictionParser(),
        run_store=run_store,
        batch_size=args.batch_size,
        resume=args.resume,
    )
    result_df = linker.link_dataframe(
        edge_df=edge_df,
        input_kind=input_kind,
        generation_config=GenerationConfig(
            max_new_tokens=args.max_new_tokens,
            temperature=args.temperature,
            top_p=args.top_p,
            do_sample=args.do_sample,
        ),
    )


def default_output_root(cache_directory: str) -> Path:
    return Path(cache_directory) / "data" / "llm"


def resolve_input_file(cache_directory: str, project: str, input_kind: str) -> Path:
    fan_directory = "t2p-candidate" if input_kind == "t2p" else "fan-in"
    return Path(cache_directory) / "data" / fan_directory / f"{project}.csv"


def _require_pandas() -> None:
    try:
        import pandas  # noqa: F401
    except ImportError as exc:
        raise ImportError("pandas is required for dataframe-based LLM linking.") from exc


if __name__ == "__main__":
    main()
