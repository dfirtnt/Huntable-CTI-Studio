#!/usr/bin/env python3
"""Convert an observable JSONL export into Workshop span JSONL format."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def convert_to_workshop(input_path: Path, output_path: Path, observable_type: str = "CMD") -> None:
    """
    Rebuild full text + span from observable export JSONL.

    The incoming export contains context_before/after plus the selected value.
    Workshop training expects `{text, spans:[{start,end,label}]}` lines.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    with input_path.open("r", encoding="utf-8") as source:
        for line in source:
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:
                print(f"Skipping invalid JSON line: {exc}")
                continue
            value = data.get("value", "")
            context_before = data.get("context_before", "")
            context_after = data.get("context_after", "")
            full_text = f"{context_before}{value}{context_after}"
            span_start = len(context_before)
            span_end = span_start + len(value)
            record = {
                "text": full_text,
                "spans": [
                    {
                        "start": span_start,
                        "end": span_end,
                        "label": observable_type,
                    }
                ],
            }
            records.append(record)

    with output_path.open("w", encoding="utf-8") as dest:
        for record in records:
            dest.write(json.dumps(record, ensure_ascii=False) + "\n")
    print(f"Converted {len(records)} records to Workshop format at {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Rebuild Workshop span records from observable export JSONL.")
    parser.add_argument(
        "--input",
        "-i",
        required=True,
        help="Path to the observable JSONL export (context_before/after + value).",
    )
    parser.add_argument(
        "--output",
        "-o",
        required=True,
        help="Destination Workshop JSONL file (text + spans).",
    )
    parser.add_argument(
        "--label",
        "-l",
        default="CMD",
        help="Span label to emit (default: CMD).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    if not input_path.exists():
        raise SystemExit(f"Input file not found: {input_path}")
    convert_to_workshop(
        input_path=input_path,
        output_path=output_path,
        observable_type=args.label,
    )


if __name__ == "__main__":
    main()
