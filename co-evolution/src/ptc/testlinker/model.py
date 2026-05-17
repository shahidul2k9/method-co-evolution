from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelConfig:
    model_name_or_path: str
    checkpoint_file: str
    max_source_length: int = 512
    eval_batch_size: int = 16
    no_cuda: bool = False
    tokenizer_mode: str = "original"


class CodeT5InvocationRanker:
    def __init__(self, config: ModelConfig):
        self.config = config
        self._model = None
        self._tokenizer = None
        self._device = None

    def score_invocations(self, *, body: str, test_name: str, invocations: list[str]) -> dict[str, float]:
        if not invocations:
            return {}
        self._ensure_loaded()

        import numpy as np
        import torch
        from torch.utils.data import DataLoader, SequentialSampler, TensorDataset

        source_ids = []
        for invocation in invocations:
            source = f"{invocation}{body}".replace("</s>", "<unk>")
            encoded = self._tokenizer.encode(
                source,
                max_length=self.config.max_source_length,
                padding="max_length",
                truncation=True,
            )
            source_ids.append(encoded)

        inputs = torch.tensor(source_ids, dtype=torch.long)
        labels = torch.tensor([0 for _ in source_ids], dtype=torch.long)
        dataset = TensorDataset(inputs, labels)
        dataloader = DataLoader(
            dataset,
            sampler=SequentialSampler(dataset),
            batch_size=self.config.eval_batch_size,
            num_workers=0,
        )

        logits = []
        self._model.eval()
        for batch in dataloader:
            batch_inputs = batch[0].to(self._device)
            batch_labels = batch[1].to(self._device)
            with torch.no_grad():
                _, probabilities = self._model(batch_inputs, batch_labels)
                logits.append(probabilities.cpu().numpy())

        predictions = np.concatenate(logits, 0)
        return {
            invocation: float(predictions[index][1])
            for index, invocation in enumerate(invocations)
        }

    def rank_invocations(self, *, body: str, test_name: str, invocations: list[str]) -> list[str]:
        scores = self.score_invocations(body=body, test_name=test_name, invocations=invocations)
        return [
            invocation
            for invocation, _ in sorted(scores.items(), key=lambda item: item[1], reverse=True)
        ]

    def _ensure_loaded(self) -> None:
        if self._model is not None:
            return

        import torch
        import torch.nn as nn
        from transformers import RobertaTokenizer, T5Config, T5ForConditionalGeneration

        _validate_pretrained_model_path(self.config.model_name_or_path)
        config = T5Config.from_pretrained(self.config.model_name_or_path)
        encoder = T5ForConditionalGeneration.from_pretrained(self.config.model_name_or_path)
        tokenizer = _load_roberta_tokenizer(self.config.model_name_or_path, self.config.tokenizer_mode)
        args = _ModelArgs(max_source_length=self.config.max_source_length, model_type="codet5")
        model = _DefectModel(encoder, config, tokenizer, args)
        state_dict = torch.load(self.config.checkpoint_file, map_location="cpu")
        model.load_state_dict(state_dict)
        device = torch.device("cuda" if torch.cuda.is_available() and not self.config.no_cuda else "cpu")
        model.to(device)
        if torch.cuda.device_count() > 1 and not self.config.no_cuda:
            model = nn.DataParallel(model.unwrap())

        self._model = model
        self._tokenizer = tokenizer
        self._device = device


@dataclass
class _ModelArgs:
    max_source_length: int
    model_type: str


class _DefectModel:
    def __init__(self, encoder, config, tokenizer, args):
        import torch.nn as nn

        class DefectModule(nn.Module):
            def __init__(self, encoder, config, tokenizer, args):
                super().__init__()
                self.encoder = encoder
                self.config = config
                self.tokenizer = tokenizer
                self.classifier = nn.Linear(config.hidden_size, 2)
                self.args = args

            def get_t5_vec(self, source_ids):
                import torch

                attention_mask = source_ids.ne(self.tokenizer.pad_token_id)
                outputs = self.encoder(
                    input_ids=source_ids,
                    attention_mask=attention_mask,
                    labels=source_ids,
                    decoder_attention_mask=attention_mask,
                    output_hidden_states=True,
                )
                hidden_states = outputs["decoder_hidden_states"][-1]
                eos_mask = source_ids.eq(self.config.eos_token_id)
                if len(torch.unique(eos_mask.sum(1))) > 1:
                    raise ValueError("All examples must have the same number of <eos> tokens.")
                return hidden_states[eos_mask, :].view(hidden_states.size(0), -1, hidden_states.size(-1))[:, -1, :]

            def forward(self, source_ids=None, labels=None):
                import torch.nn as nn

                source_ids = source_ids.view(-1, self.args.max_source_length)
                vec = self.get_t5_vec(source_ids)
                logits = self.classifier(vec)
                probabilities = nn.functional.softmax(logits, dim=-1)
                if labels is not None:
                    loss = nn.CrossEntropyLoss()(logits, labels)
                    return loss, probabilities
                return probabilities

        self._module = DefectModule(encoder, config, tokenizer, args)

    def __getattr__(self, item):
        return getattr(self._module, item)

    def __call__(self, *args, **kwargs):
        return self._module(*args, **kwargs)

    def unwrap(self):
        return self._module


def _validate_pretrained_model_path(model_name_or_path: str) -> None:
    model_path = Path(model_name_or_path)
    if not model_path.exists():
        return

    has_config = (model_path / "config.json").exists()
    has_weights = any(
        (model_path / filename).exists()
        for filename in ("pytorch_model.bin", "model.safetensors", "tf_model.h5", "flax_model.msgpack")
    )
    has_tokenizer = any(
        (model_path / filename).exists()
        for filename in ("tokenizer.json", "vocab.json", "merges.txt", "sentencepiece.bpe.model")
    )
    if has_config and has_weights and has_tokenizer:
        return

    raise FileNotFoundError(
        "CodeT5 base model files are missing from "
        f"{model_path}. This directory must contain the pretrained CodeT5 config, tokenizer, and base weights. "
        "Keep fine-tuned TestLinker checkpoints separately under "
        "<workspace-directory>/testlinker-finetuned-checkpoints/codet5-base/checkpoint-*/pytorch_model.bin, "
        "or pass --model-name-or-path to a valid pretrained CodeT5 directory/model id."
    )


def _load_roberta_tokenizer(model_name_or_path: str, tokenizer_mode: str = "original"):
    from transformers import RobertaTokenizer

    if tokenizer_mode == "fallback":
        vocab_file, merges_file = _resolve_roberta_tokenizer_files(model_name_or_path)
        return _build_roberta_tokenizer_from_files(vocab_file, merges_file)
    if tokenizer_mode not in {"original", "auto"}:
        raise ValueError(f"Unsupported tokenizer mode: {tokenizer_mode}")

    try:
        return RobertaTokenizer.from_pretrained(model_name_or_path)
    except (TypeError, ValueError) as exc:
        if tokenizer_mode == "original":
            raise
        try:
            vocab_file, merges_file = _resolve_roberta_tokenizer_files(model_name_or_path)
        except Exception:
            raise exc
        return _build_roberta_tokenizer_from_files(vocab_file, merges_file)


def _resolve_roberta_tokenizer_files(model_name_or_path: str) -> tuple[str, str]:
    model_path = Path(model_name_or_path)
    if model_path.exists():
        vocab_file = model_path / "vocab.json"
        merges_file = model_path / "merges.txt"
        if vocab_file.exists() and merges_file.exists():
            return str(vocab_file), str(merges_file)
        raise FileNotFoundError(f"Missing vocab.json or merges.txt in {model_path}")

    from transformers.utils.hub import cached_file

    vocab_file = cached_file(model_name_or_path, "vocab.json")
    merges_file = cached_file(model_name_or_path, "merges.txt")
    if vocab_file is None or merges_file is None:
        raise FileNotFoundError(f"Could not resolve vocab.json and merges.txt for {model_name_or_path}")
    return vocab_file, merges_file


def _build_roberta_tokenizer_from_files(vocab_file: str, merges_file: str):
    import inspect

    from transformers import RobertaTokenizer

    tokenizer_kwargs = {
        "unk_token": "<unk>",
        "bos_token": "<s>",
        "eos_token": "</s>",
        "sep_token": "</s>",
        "cls_token": "<s>",
        "pad_token": "<pad>",
        "mask_token": "<mask>",
    }
    constructor_parameters = inspect.signature(RobertaTokenizer.__init__).parameters
    if "vocab" in constructor_parameters:
        tokenizer_kwargs.update({"vocab": str(vocab_file), "merges": str(merges_file)})
    else:
        tokenizer_kwargs.update({"vocab_file": str(vocab_file), "merges_file": str(merges_file)})
    return RobertaTokenizer(**tokenizer_kwargs)
