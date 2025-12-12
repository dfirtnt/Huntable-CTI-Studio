"""
Character span validation and alignment to token-level labels.
"""

from typing import List, Dict, Tuple


CMD_LABEL = "CMD"
LABEL_TO_ID = {"O": 0, CMD_LABEL: 1}


def validate_spans(spans: List[Dict], text_length: int) -> List[Dict]:
    """Ensure spans are sorted, non-overlapping, within bounds, and CMD-only."""
    normalized = []
    for span in spans or []:
        if span.get("label") != CMD_LABEL:
            raise ValueError(f"Only '{CMD_LABEL}' label is allowed (got {span.get('label')})")
        start = int(span["start"])
        end = int(span["end"])
        if start < 0 or end < 0 or start >= end:
            raise ValueError(f"Invalid span bounds: {span}")
        if end > text_length:
            raise ValueError(f"Span end {end} exceeds text length {text_length}")
        normalized.append({"start": start, "end": end, "label": CMD_LABEL})

    normalized.sort(key=lambda s: (s["start"], s["end"]))
    for prev, curr in zip(normalized, normalized[1:]):
        if curr["start"] < prev["end"]:
            raise ValueError(f"Overlapping spans detected: {prev} vs {curr}")

    return normalized


def spans_to_token_labels(
    spans: List[Dict],
    offsets: List[Tuple[int, int]],
) -> List[int]:
    """
    Convert character spans to token labels (binary CMD vs O).

    Any token whose offset overlaps a span is labeled CMD.
    """
    labels = [LABEL_TO_ID["O"]] * len(offsets)
    if not spans:
        return labels

    for span in spans:
        span_start, span_end = span["start"], span["end"]
        for idx, (tok_start, tok_end) in enumerate(offsets):
            if tok_end <= span_start:
                continue
            if tok_start >= span_end:
                break
            labels[idx] = LABEL_TO_ID[CMD_LABEL]

    return labels
