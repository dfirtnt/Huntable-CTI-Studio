---
name: mdu
description: Update all Markdown documentation (changelog, README, docs/) to reflect code and session changes; verify MkDocs build. Use when the user says "mdu" or asks to update all Markdown docs.
---

# MDU — Update All Markdown Docs

When the user says **mdu**, update all Markdown documentation. Do not commit or push; this is docs-only.

## Scope

1. **Changelog** — Add this session’s changes to `docs/CHANGELOG.md` (Keep a Changelog format; root `CHANGELOG.md` only points to `docs/CHANGELOG.md`).
2. **README** — Ensure `README.md` reflects current quick start, stack, and links (e.g. `docs/`, `./start.sh`, ports).
3. **Docs** — Ensure `docs/` (and any touched feature/concept/how-to pages) match current behavior, APIs, and config. Update `mkdocs.yml` nav if new docs were added.
4. **Verify** — Run `mkdocs build` (or `mkdocs serve` briefly) so the docs site builds without errors.

## Order

- Changelog first, then README, then affected docs under `docs/`, then MkDocs build.

## Out of scope

- No `git add` / commit / push (use **lg** for that).
- No dependency or security checks (those are part of **lg** hygiene).
