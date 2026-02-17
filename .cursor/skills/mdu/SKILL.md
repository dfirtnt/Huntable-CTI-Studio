---
name: mdu
description: Update all Markdown documentation (changelog, README, docs/) to reflect code and session changes; verify MkDocs build. Use when the user says "mdu" or asks to update all Markdown docs. Supports a full weekly true-up mode (sequential reasoning, code–docs cross-check).
---

# MDU — Update All Markdown Docs

When the user says **mdu**, update all Markdown documentation. Do not commit or push; this is docs-only.

## Scope (standard run)

1. **Changelog** — Add this session’s changes to `docs/CHANGELOG.md` (Keep a Changelog format; root `CHANGELOG.md` only points to `docs/CHANGELOG.md`).
2. **README** — Ensure `README.md` reflects current quick start, stack, and links (e.g. `docs/`, `./start.sh`, ports).
3. **Docs** — Ensure `docs/` (and any touched feature/concept/how-to pages) match current behavior, APIs, and config. Update `mkdocs.yml` nav if new docs were added.
4. **Verify** — Run `mkdocs build` (or `mkdocs serve` briefly) so the docs site builds without errors.

## Order

- Changelog first, then README, then affected docs under `docs/`, then MkDocs build.

---

## Full weekly true-up (sequential reasoning)

When the user requests a **full weekly true-up** or **Deepthink / sequential** doc review, perform a complete codebase–documentation alignment. Think step by step; **verify before rewriting**. Focus on **factual accuracy and internal consistency**, not stylistic polish.

### Objective

Ensure that **all** Markdown files (`*.md`), READMEs, help pages, and inline code documentation accurately reflect the current implementation. Compare code, configuration files, Dockerfiles, and scripts with every corresponding doc.

### Steps (execute in order)

1. **Factual consistency**
   - Verify every `*.md` and file under `docs/` against the latest code.
   - Update any mismatched **examples**, **CLI flags**, or **configuration references** in docs to match actual behavior.

2. **Dependency and version drift**
   - Check code vs Docker vs documentation for dependency names and versions (e.g. `requirements*.txt`, `Dockerfile`, `docker-compose`, `pyproject.toml`).
   - Align docs with the versions and commands that the repo actually uses.

3. **Broken, outdated, or redundant docs**
   - Identify docs that reference removed features, deprecated APIs, or duplicate/conflicting content.
   - For each: propose a concise correction and explain why (e.g. “remove section X because script Y was deleted”).

4. **Help messages, docstrings, README**
   - Confirm that help text, docstrings, and README examples align with **actual CLI behavior** and **API structure** (e.g. run CLI with `--help` or inspect API and compare to docs).

5. **Cross-reference layers**
   - Cross-reference **environment variables**, **file paths**, and **build/run commands** across:
     - Application code and config
     - Docker / docker-compose
     - Docs and README

6. **Per-issue output**
   - For each inaccuracy: state the **issue**, **proposed correction**, and **rationale** (why the doc is wrong and what source of truth was used).

7. **Final summary**
   - **Current** — List files that are already accurate and up to date.
   - **Needs update** — List files that were changed or that still need changes (with brief reason).
   - **Inaccuracies found** — Where each inaccuracy was (file + section/topic) and what was fixed or proposed.

### Constraints

- **Sequential:** Complete each step before moving to the next; use code/config as source of truth.
- **Verify before rewrite:** Read the implementation (or run the CLI/script) before editing the doc.
- **No stylistic polish:** Only fix factual and consistency errors unless the user asks for more.

---

## Out of scope

- No `git add` / commit / push (use **lg** for that).
- No dependency or security checks (those are part of **lg** hygiene).
