"""
Dataset validator for Workshop span JSONL files.
"""

from pathlib import Path
from typing import List

from Workshop.utilities.span_to_token_alignment import validate_spans


def validate_jsonl(path: Path) -> List[str]:
    errors: List[str] = []
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                import json

                record = json.loads(line)
                text = record["text"]
                spans = record.get("spans", [])
                validate_spans(spans, len(text))
            except Exception as exc:
                errors.append(f"Line {idx}: {exc}")
    return errors


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Validate span JSONL files.")
    parser.add_argument("path", help="Path to JSONL file")
    args = parser.parse_args()

    path = Path(args.path)
    errs = validate_jsonl(path)
    if errs:
        print("Validation failed:")
        for err in errs:
            print(f"- {err}")
    else:
        print("Validation passed.")


if __name__ == "__main__":
    main()
