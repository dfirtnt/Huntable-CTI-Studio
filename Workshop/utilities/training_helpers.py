"""
Dataset loading and encoding helpers for span-based token classification.
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional

import torch
from torch.utils.data import Dataset
from transformers import DataCollatorForTokenClassification

from Workshop.utilities.preprocessor import preprocess_text, hard_chunk_text
from Workshop.utilities.span_to_token_alignment import (
    CMD_LABEL,
    spans_to_token_labels,
    validate_spans,
)
from Workshop.utilities.tokenizer_utils import DEFAULT_MAX_LENGTH


def set_seed(seed: int = 42):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


def load_jsonl(path: Path) -> List[Dict]:
    examples: List[Dict] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            examples.append(json.loads(line))
    return examples


class SpanTokenDataset(Dataset):
    """Token-level dataset built from span-annotated JSONL."""

    def __init__(
        self,
        examples: List[Dict],
        tokenizer,
        max_length: int = DEFAULT_MAX_LENGTH,
    ):
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.features = self._encode(examples)

    def _encode(self, examples: List[Dict]) -> List[Dict]:
        feats: List[Dict] = []
        for ex in examples:
            raw_text = preprocess_text(ex["text"])
            spans = validate_spans(ex.get("spans", []), len(raw_text))
            chunks = hard_chunk_text(raw_text, self.tokenizer, max_length=self.max_length)
            if not chunks:
                continue

            for chunk in chunks:
                chunk_spans = []
                for span in spans:
                    if span["end"] <= chunk["start"] or span["start"] >= chunk["end"]:
                        continue
                    if not (span["start"] >= chunk["start"] and span["end"] <= chunk["end"]):
                        raise ValueError(
                            f"Span {span} crosses chunk boundary {chunk['start']}:{chunk['end']}. "
                            "Increase max_length or preprocess to avoid splitting spans."
                        )
                    chunk_spans.append(
                        {
                            "start": span["start"] - chunk["start"],
                            "end": span["end"] - chunk["start"],
                            "label": CMD_LABEL,
                        }
                    )

                encoded = self.tokenizer(
                    chunk["text"],
                    max_length=self.max_length,
                    padding="max_length",
                    truncation=True,
                    return_offsets_mapping=True,
                    return_tensors="pt",
                )

                offsets = encoded.pop("offset_mapping")[0].tolist()
                labels = spans_to_token_labels(chunk_spans, offsets)

                feats.append(
                    {
                        "input_ids": encoded["input_ids"].squeeze(0),
                        "attention_mask": encoded["attention_mask"].squeeze(0),
                        "labels": torch.tensor(labels, dtype=torch.long),
                    }
                )
        return feats

    def __len__(self):
        return len(self.features)

    def __getitem__(self, idx):
        return self.features[idx]


def load_datasets(
    train_path: Optional[Path],
    valid_path: Optional[Path],
    tokenizer,
    max_length: int = DEFAULT_MAX_LENGTH,
):
    train_ds = SpanTokenDataset(load_jsonl(train_path), tokenizer, max_length) if train_path else None
    valid_ds = SpanTokenDataset(load_jsonl(valid_path), tokenizer, max_length) if valid_path else None
    return train_ds, valid_ds


def build_data_collator(tokenizer):
    return DataCollatorForTokenClassification(tokenizer=tokenizer, padding="max_length")
