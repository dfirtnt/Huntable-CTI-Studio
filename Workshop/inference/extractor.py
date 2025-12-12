"""
Unified inference wrapper for span extraction models.
"""

from pathlib import Path
from typing import Dict, List

import torch
from transformers import AutoModelForTokenClassification

from Workshop.utilities.preprocessor import preprocess_text, hard_chunk_text
from Workshop.utilities.span_to_token_alignment import CMD_LABEL, LABEL_TO_ID
from Workshop.utilities.tokenizer_utils import get_tokenizer


def _detect_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


class CmdExtractor:
    def __init__(self, model_path: str, max_length: int = 512):
        self.model_path = Path(model_path)
        self.tokenizer = get_tokenizer(model_path, max_length=max_length)
        self.model = AutoModelForTokenClassification.from_pretrained(model_path)
        self.device = _detect_device()
        if self.device != "cpu":
            self.model.to(self.device)
        self.model.eval()
        self.max_length = max_length

    @torch.inference_mode()
    def extract(self, text: str) -> Dict[str, List[Dict]]:
        cleaned = preprocess_text(text)
        spans: List[Dict] = []

        chunks = hard_chunk_text(cleaned, self.tokenizer, max_length=self.max_length)
        if not chunks:
            return {"spans": []}

        for chunk in chunks:
            inputs = self.tokenizer(
                chunk["text"],
                return_offsets_mapping=True,
                truncation=True,
                padding="max_length",
                max_length=self.max_length,
                return_tensors="pt",
            )
            offsets = inputs.pop("offset_mapping")[0].tolist()
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            logits = self.model(**inputs).logits[0]
            preds = torch.argmax(logits, dim=-1).tolist()

            chunk_spans = []
            current = None
            for idx, label_id in enumerate(preds):
                start, end = offsets[idx]
                if start == end == 0:
                    continue  # special or padding tokens
                if label_id == LABEL_TO_ID[CMD_LABEL]:
                    if current and start <= current["end"]:
                        current["end"] = end
                    else:
                        if current:
                            chunk_spans.append(current)
                        current = {"start": start, "end": end}
                else:
                    if current:
                        chunk_spans.append(current)
                        current = None
            if current:
                chunk_spans.append(current)

            for span in chunk_spans:
                abs_start = span["start"] + chunk["start"]
                abs_end = span["end"] + chunk["start"]
                spans.append(
                    {
                        "start": abs_start,
                        "end": abs_end,
                        "text": cleaned[abs_start:abs_end],
                        "label": CMD_LABEL,
                    }
                )

        spans.sort(key=lambda s: (s["start"], s["end"]))
        return {"spans": spans}
