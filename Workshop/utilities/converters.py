"""
Converters from common annotation exports to Workshop span JSONL.

Supported formats:
- Doccano JSONL: expects `text` plus `labels` or `entities` as [start, end, label].
- INCEpTION: JSONL with `annotations` (begin/end/label) or TSV with columns text,begin,end,label.
- YEDDA: TSV with columns text,start,end,label (lightweight mapping).
"""

import json
from json import JSONDecoder
from pathlib import Path
from typing import Dict, Iterable, List

from Workshop.utilities.span_to_token_alignment import CMD_LABEL, validate_spans


def _write_jsonl(records: Iterable[Dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load_json_objects(path: Path) -> List[Dict]:
    """
    Robustly load one or more JSON objects from a file.

    Supports:
    - Compact JSONL (one object per line)
    - Pretty-printed objects (jq output) where records span multiple lines
    - Multiple objects concatenated with whitespace
    """
    decoder = JSONDecoder()
    with path.open("r", encoding="utf-8") as f:
        content = f.read()

    objs = []
    idx = 0
    length = len(content)
    while idx < length:
        # Skip whitespace
        while idx < length and content[idx].isspace():
            idx += 1
        if idx >= length:
            break
        obj, end = decoder.raw_decode(content, idx)
        objs.append(obj)
        idx = end
    return objs


def _to_cmd_span(start: int, end: int, label: str) -> Dict:
    if label != CMD_LABEL:
        raise ValueError(f"Only '{CMD_LABEL}' label allowed (got {label})")
    return {"start": int(start), "end": int(end), "label": CMD_LABEL}


def doccano_to_span_jsonl(input_path: Path, output_path: Path) -> None:
    records: List[Dict] = []
    objs = _load_json_objects(input_path)
    for data in objs:
        text = data["text"]
        raw_spans = data.get("labels") or data.get("label") or data.get("entities") or []
        spans = [_to_cmd_span(s[0], s[1], s[2]) for s in raw_spans]
        validate_spans(spans, len(text))
        records.append({"text": text, "spans": spans})
    _write_jsonl(records, output_path)


def inception_to_span_jsonl(input_path: Path, output_path: Path) -> None:
    records: List[Dict] = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            if line.lstrip().startswith("{"):
                data = json.loads(line)
                text = data["text"]
                raw_spans = data.get("annotations", [])
                spans = [_to_cmd_span(s["begin"], s["end"], s["label"]) for s in raw_spans]
            else:
                # TSV: text<TAB>begin<TAB>end<TAB>label
                parts = line.rstrip("\n").split("\t")
                if len(parts) < 4:
                    raise ValueError("TSV line must contain text, begin, end, label")
                text, begin, end, label = parts[0], parts[1], parts[2], parts[3]
                spans = [_to_cmd_span(int(begin), int(end), label)]
            validate_spans(spans, len(text))
            records.append({"text": text, "spans": spans})
    _write_jsonl(records, output_path)


def yedda_to_span_jsonl(input_path: Path, output_path: Path) -> None:
    """
    Lightweight YEDDA mapper.

    Expects TSV rows: text<TAB>start<TAB>end<TAB>label
    """
    records: List[Dict] = []
    with input_path.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 4:
                raise ValueError("YEDDA TSV must have text, start, end, label columns")
            text, start, end, label = parts[0], parts[1], parts[2], parts[3]
            spans = [_to_cmd_span(int(start), int(end), label)]
            validate_spans(spans, len(text))
            records.append({"text": text, "spans": spans})
    _write_jsonl(records, output_path)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Convert annotation exports to Workshop span JSONL.")
    parser.add_argument("--format", required=True, choices=["doccano", "inception", "yedda"])
    parser.add_argument("--input", required=True, help="Path to source file")
    parser.add_argument("--output", required=True, help="Path to JSONL output")
    args = parser.parse_args()

    fmt = args.format.lower()
    input_path = Path(args.input)
    output_path = Path(args.output)

    if fmt == "doccano":
        doccano_to_span_jsonl(input_path, output_path)
    elif fmt == "inception":
        inception_to_span_jsonl(input_path, output_path)
    else:
        yedda_to_span_jsonl(input_path, output_path)

    print(f"Converted {fmt} annotations to {output_path}")


if __name__ == "__main__":
    main()
