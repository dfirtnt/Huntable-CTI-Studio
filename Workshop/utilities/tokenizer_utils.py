"""
Shared tokenizer helpers for Workshop models.
"""

import os
from functools import lru_cache
from typing import Optional

from transformers import AutoTokenizer

DEFAULT_MAX_LENGTH = 512

# Allow overriding SecBERT path via env to avoid hardcoding an unavailable repo.
MODEL_PRESETS = {
    "bert_base": "bert-base-uncased",
    "roberta_base": "roberta-base",
    "secbert": os.getenv("SECBERT_MODEL_NAME", "bert-base-uncased"),
}


def resolve_model_name(name_or_key: str) -> str:
    """Map short keys to pretrained identifiers; passthrough unknown values."""
    return MODEL_PRESETS.get(name_or_key, name_or_key)


@lru_cache(maxsize=8)
def get_tokenizer(name_or_key: str, max_length: int = DEFAULT_MAX_LENGTH):
    """Load and configure a tokenizer."""
    resolved = resolve_model_name(name_or_key)
    tokenizer = AutoTokenizer.from_pretrained(resolved, use_fast=True)
    tokenizer.model_max_length = max_length
    return tokenizer
