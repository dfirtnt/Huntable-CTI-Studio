---
name: lgl
description: Lite commit and push to current branch (git add ., commit, push)
disable-model-invocation: true
---

Run from the project root **with the project .venv active** so pre-commit (and vulture) hooks succeed:

1. `git add .`
2. Commit with a clear message: use the project venv for the commit step (e.g. `source .venv/bin/activate && git commit -m "..."` or ensure `.venv/bin` is on PATH when running `git commit`). Do not use `--no-verify` unless the user explicitly asks.
3. Push the **current branch** only: `git push origin HEAD` (or `git push`). Do not push to `origin main` unless the user explicitly requests it.

If the repo has no .venv or pre-commit is not installed, proceed with a normal `git commit` and push.
