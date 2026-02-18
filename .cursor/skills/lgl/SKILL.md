---
name: lgl
description: Lite commit and push to current branch (git add ., commit, push)
disable-model-invocation: true
---

Run: `git add .`, commit, then push the **current branch** only. Use `git push origin HEAD` (or `git push`) so the remote is always the branch you are on. Do not push to `origin main` unless the user explicitly requests it.
