from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from ptc.llm.models import GenerationConfig
from ptc.llm.persistence import CsvRunStore
from ptc.llm.prompting import JsonPredictionParser, MethodLinkingPromptFactory
from ptc.llm.providers.huggingface import (
    HuggingFaceProviderConfig,
    HuggingFaceTextGenerationProvider,
)
from ptc.llm.providers.openai_responses import (
    OpenAIResponsesProvider,
    OpenAIResponsesProviderConfig,
)
from ptc.llm.t2p_link_projection import project_t2p_links
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
        "--stage",
        dest="stage",
        choices=["execute", "parse"],
        default="execute",
        help="Use `execute` to run model inference or `parse` to project stored LLM outputs into t2p-link rows.",
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
        help="Model id or local path.",
    )
    parser.add_argument(
        "--api-type",
        dest="api_type",
        choices=["auto", "huggingface", "openai-responses"],
        default="auto",
        help="Provider transport to use. `auto` routes GPT-family models to OpenAI Responses API and others to Hugging Face.",
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
        "--prompt-format",
        dest="prompt_format",
        choices=["auto", "json", "text"],
        default="auto",
        help="Prompt/output contract. `auto` uses the provider default.",
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
        dest="resume",
        choices=["none", "all", "error"],
        default="none",
        help="Resume mode: `none` reruns all rows, `all` skips completed rows, `error` reruns only rows with existing non-empty errors.",
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
        default=os.environ.get("HF_TOKEN"),
        help="Hugging Face token. Defaults to HF_TOKEN or HUGGINGFACE_HUB_TOKEN.",
    )
    parser.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="Provider API key. Used by native API providers such as openai-responses.",
    )
    parser.add_argument(
        "--base-url",
        dest="base_url",
        default=None,
        help="Optional base URL for native API providers.",
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


def main() -> int:
    _require_pandas()
    import pandas as pd

    parser = build_parser()
    args = parser.parse_args()
    exit_code = 0

    if args.stage == "parse":
        projected_df = run_llm_t2p_link(args)
        print(projected_df.head().to_string(index=False))
    else:
        input_kind = args.input_kind
        input_path = resolve_input_file(args.cache_directory, args.project, input_kind)
        if not input_path.exists():
            parser.error(f"Input file not found: {input_path}")
        method_code_path = resolve_method_code_file(args.cache_directory, args.project)
        if not method_code_path.exists():
            parser.error(f"Method code file not found: {method_code_path}")

        output_root = default_output_root(args.cache_directory)
        run_store = CsvRunStore(
            output_root=output_root,
            input_kind=input_kind,
            model_name_or_path=args.model_name_or_path,
            input_file_name=input_path.name,
            short_model_name=args.short_model_name,
        )

        edge_df = pd.read_csv(input_path, keep_default_na=False, na_filter=False)
        method_code_lookup = load_method_code_lookup(method_code_path)
        provider = build_provider(args)
        linker = DataFrameMethodLinker(
            provider=provider,
            prompt_factory=MethodLinkingPromptFactory(method_code_lookup=method_code_lookup),
            parser=JsonPredictionParser(),
            run_store=run_store,
            batch_size=args.batch_size,
            resume_mode=args.resume,
            prompt_format=args.prompt_format,
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
        print(result_df.head().to_string(index=False))
    return exit_code


def run_llm_t2p_link(args):
    candidate_file = resolve_input_file(args.cache_directory, args.project, "t2p")
    if not candidate_file.exists():
        raise FileNotFoundError(f"Input file not found: {candidate_file}")

    run_store = CsvRunStore(
        output_root=default_output_root(args.cache_directory),
        input_kind="t2p",
        model_name_or_path=args.model_name_or_path,
        input_file_name=candidate_file.name,
        short_model_name=args.short_model_name,
    )
    output_file = Path(args.cache_directory) / "data" / "llm" / "t2p-link" / run_store.model_directory_name / candidate_file.name
    return project_t2p_links(
        candidate_file=candidate_file,
        llm_run_file=run_store.runs_file,
        output_file=output_file,
    )


def default_output_root(cache_directory: str) -> Path:
    return Path(cache_directory) / "data" / "llm"


def resolve_input_file(cache_directory: str, project: str, input_kind: str) -> Path:
    fan_directory = "t2p-candidate" if input_kind == "t2p" else "fanin"
    return Path(cache_directory) / "data" / fan_directory / f"{project}.csv"


def resolve_method_code_file(cache_directory: str, project: str) -> Path:
    return Path(cache_directory) / "data" / "method-code" / f"{project}.csv"


def load_method_code_lookup(method_code_path: Path) -> dict[str, dict[str, str]]:
    import pandas as pd

    method_code_df = pd.read_csv(method_code_path, keep_default_na=False, na_filter=False)
    lookup: dict[str, dict[str, str]] = {}
    for row in method_code_df.itertuples(index=False):
        url = getattr(row, "url", "")
        if url:
            lookup[url] = {
                "name": getattr(row, "name", ""),
                "code": getattr(row, "code", ""),
            }
    return lookup


def _require_pandas() -> None:
    try:
        import pandas  # noqa: F401
    except ImportError as exc:
        raise ImportError("pandas is required for dataframe-based LLM linking.") from exc


def build_provider(args):
    api_type = resolve_api_type(args.api_type, args.model_name_or_path)
    if api_type == "openai-responses":
        return OpenAIResponsesProvider(
            OpenAIResponsesProviderConfig(
                model_name_or_path=args.model_name_or_path,
                api_key=args.api_key,
                base_url=args.base_url,
            )
        )

    return HuggingFaceTextGenerationProvider(
        HuggingFaceProviderConfig(
            model_name_or_path=args.model_name_or_path,
            device_map=args.device_map,
            dtype=args.dtype,
            trust_remote_code=args.trust_remote_code,
            batch_size=args.batch_size,
            token=args.hf_token,
        )
    )


def resolve_api_type(api_type: str, model_name_or_path: str) -> str:
    if api_type != "auto":
        return api_type

    normalized = model_name_or_path.strip().lower()
    if normalized.startswith("gpt-") or normalized.startswith("openai/gpt-oss"):
        return "openai-responses"
    return "huggingface"


if __name__ == "__main__":
    sys.exit(main())
