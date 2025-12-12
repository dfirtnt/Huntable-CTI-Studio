# Workshop (Span Extraction Lab)

- Use a Python venv for all commands: `python3 -m venv .venv && source .venv/bin/activate`.
- Install deps locally: `pip install -r Workshop/requirements.txt`.
- All work stays under `Workshop/` (no production code or DB writes).
- Dataset format: JSONL `{ "text": "...", "spans": [{"start": int, "end": int, "label": "CMD"}] }`.
- Model versions are created only after training; defaults save to `models/<model>/v0.1/` when training scripts finish.
- Regression uses fixed `regression/test_set/test.jsonl` and writes results only.