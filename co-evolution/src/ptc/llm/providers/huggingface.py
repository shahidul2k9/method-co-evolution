from __future__ import annotations

import copy
import importlib.util
import os
import warnings
from dataclasses import dataclass

from ptc.llm.models import GenerationConfig, PromptInput, ProviderGeneration
from ptc.llm.runner import ModelProvider


@dataclass(slots=True)
class HuggingFaceProviderConfig:
    model_name_or_path: str
    device_map: str = "auto"
    dtype: str = "auto"
    trust_remote_code: bool = False
    batch_size: int = 4
    token: str | None = None


class HuggingFaceTextGenerationProvider(ModelProvider):
    def __init__(self, config: HuggingFaceProviderConfig):
        self.config = config
        self._pipeline = None

    def generate_batch(
        self,
        prompts: list[PromptInput],
        generation_config: GenerationConfig,
    ) -> list[ProviderGeneration]:
        pipeline = self._get_pipeline()
        prompt_texts = [prompt.prompt_text for prompt in prompts]
        hf_generation_config = self._build_generation_config(pipeline, generation_config)
        outputs = pipeline(
            prompt_texts,
            batch_size=self.config.batch_size,
            return_full_text=False,
            generation_config=hf_generation_config,
        )

        generations: list[ProviderGeneration] = []
        for prompt, output in zip(prompts, outputs):
            text = self._extract_generated_text(output)
            generations.append(
                ProviderGeneration(
                    id=prompt.id,
                    output_text=text,
                    metadata={"model_name_or_path": self.config.model_name_or_path},
                )
            )
        return generations

    def _get_pipeline(self):
        if self._pipeline is not None:
            return self._pipeline

        import torch
        from transformers import pipeline

        dtype = self.config.dtype
        if dtype != "auto":
            dtype = getattr(torch, dtype)

        current_accelerator = torch.accelerator.current_accelerator() if hasattr(torch, "accelerator") else None
        if (
            current_accelerator is not None
            and current_accelerator.type == "mps"
            and "gpt-oss" in self.config.model_name_or_path.lower()
        ):
            warnings.warn(
                "The current PyTorch accelerator is MPS. MXFP4 gpt-oss checkpoints do not run natively on MPS, "
                "so Transformers will dequantize them to bf16. This usually increases memory use substantially. "
                "For local testing, prefer a smaller model; for real runs, prefer CUDA/CPU environments such as Canada Alliance.",
                stacklevel=2,
            )

        device_map = self._normalize_device_map(self.config.device_map)
        if device_map is not None and importlib.util.find_spec("accelerate") is None:
            raise ImportError(
                "The configured Hugging Face device_map requires `accelerate`, "
                f"but accelerate is not installed. device_map={self.config.device_map!r}. "
                "Install it with `pip install accelerate`, or rerun with "
                "`--device_map none` to let Transformers use its default single-device loading."
            )

        token = (
            self.config.token
            or os.environ.get("HF_TOKEN")
            or os.environ.get("HUGGINGFACE_HUB_TOKEN")
        )
        if not token:
            warnings.warn(
                "HF_TOKEN is not set. Hugging Face Hub downloads will be unauthenticated and may be slower.",
                stacklevel=2,
            )

        self._pipeline = pipeline(
            task="text-generation",
            model=self.config.model_name_or_path,
            device_map=device_map,
            dtype=dtype,
            trust_remote_code=self.config.trust_remote_code,
            token=token,
        )
        return self._pipeline

    @staticmethod
    def _build_generation_config(pipeline, generation_config: GenerationConfig):
        hf_generation_config = copy.deepcopy(pipeline.model.generation_config)
        hf_generation_config.max_new_tokens = generation_config.max_new_tokens
        hf_generation_config.max_length = None
        hf_generation_config.do_sample = generation_config.do_sample
        if generation_config.do_sample:
            hf_generation_config.temperature = generation_config.temperature
            hf_generation_config.top_p = generation_config.top_p
        else:
            hf_generation_config.temperature = None
            hf_generation_config.top_p = None
            if hasattr(hf_generation_config, "top_k"):
                hf_generation_config.top_k = None
        return hf_generation_config

    @staticmethod
    def _extract_generated_text(output) -> str:
        if isinstance(output, list):
            output = output[0]
        if isinstance(output, dict):
            return str(output.get("generated_text", "")).strip()
        return str(output).strip()

    @staticmethod
    def _normalize_device_map(value: str | None):
        if value is None:
            return None
        if isinstance(value, str) and value.strip().lower() in {"", "none", "null"}:
            return None
        return value
