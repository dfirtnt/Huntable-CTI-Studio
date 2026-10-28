---
name: huntable-doc-trueup
description: >
  Full weekly documentation audit and fix cycle for Huntable CTI Studio. Scans all *.md and
  /docs files, validates each against the live codebase, applies factual corrections, and
  produces a triage summary. Use this skill whenever the user says "huntable-doc-trueup", "weekly doc
  audit", "true-up the docs", "full doc sync", "docs audit", "check all docs for drift",
  "docs are stale", "run the doc audit", or anything about validating or syncing all
  documentation against current code. This is a FULL REPO sweep — not a single-file fix.
  Trigger it proactively whenever the user has finished a major feature and asks to "clean up"
  or "wrap up" without specifying what.
---

# huntable-doc-trueup

A systematic, sequential documentation audit for Huntable CTI Studio. You verify first, then
rewrite — never the other way around. Your corrections are factual only: wrong paths, stale
names, broken examples, missing required steps. Not style, not polish.

Neighboring skills — pick the right one:
- **doc-overhaul** — deep restructuring, fluff cuts, page deletions, writing missing docs.
  That skill has deletion and rewrite authority; this one is the frequent, safe
  drift-correction pass.
- **mdu** — updates docs to reflect changes made *in the current session*. huntable-doc-trueup audits
  the whole doc set against the *whole codebase*, regardless of what this session touched.
- **mkdocs-helper** — single-file editorial review. huntable-doc-trueup is the full-repo factual sweep.

A note on trust: this skill file itself contains repo facts (paths, names, commands) that go
stale like any doc. Where possible the phases below tell you to enumerate live state instead
of trusting a list. If you find a claim in this skill that contradicts the repo (a missing
file, a renamed agent), the repo wins — and note the skill drift in your final report so the
operator can fix the skill.

---

## Phase 1 — Load Oracles (do this first, before touching any doc)

Before reading or editing docs, run `git status --short` and record every pre-existing
modified or untracked path. Do not edit, stage, or otherwise absorb parallel work; stage only
explicit doc paths if a later commit is requested.

Read these files. They are the ground truth you validate docs against. They change often enough
that stale docs are the default, not the exception.

```
src/database/models.py                   — model names, field names, table names
src/config/workflow_config_schema.py     — config keys, agent names, workflow step IDs
src/web/routes/__init__.py               — all registered API routes and prefixes
src/worker/celery_app.py                 — scheduled task names, beat schedule
tests_runner/config.py                   — valid test suite names (`RunTestType`)
tests_runner/cli.py                      — test CLI flags and argument handling
pyproject.toml                           — package version, dependency versions
```

`run_tests.py` is only a re-exec shim; do not use it as the suite/flag oracle.

Also read:
```
AGENTS.md                                — authoritative naming conventions
docs/CHANGELOG.md                        — version history (helps catch stale version refs)
```

Derive the canonical agent-name set from the schema rather than memorizing it:

```bash
grep -oE '"[A-Z][A-Za-z]*(Extract|Agent)"' src/config/workflow_config_schema.py | sort -u
```

These quoted PascalCase keys (e.g. `CmdlineExtract`, `ServicesExtract`, `SigmaAgent`) are the
only correct spellings. Any doc using a name not in this set — or a plausible-sounding variant
of one — has an accuracy bug. New extractors get added regularly, so an enumerated list in
this file would drift; the grep never does.

Hold a mental map of what's actually in the codebase. Every claim you check in a doc gets
verified against this map, not against another doc.

Also mine removals: skim `CHANGELOG.md` and run `git log --oneline --diff-filter=D -- src/`
for recently removed or deprecated subsystems. Docs describing removed code as current are
the most damaging kind of drift, and you can't spot them by checking claims one at a time —
you have to know what's gone.

Also sweep for debt from prior runs before auditing content:

```bash
grep -RInE '<!-- (AUDIT:|TODO: verify)' docs --include='*.md' || true
```

Resolve every marker you find. If the claim is verified wrong, correct the visible prose and
strip the marker. If it remains genuinely unverifiable, keep a terse marker naming the exact
thing still to check. Do not treat an invisible comment as a warning to readers.

Finally, capture a link-check baseline: run `.venv/bin/python -m mkdocs build --strict` and save
the output. Judge success by the process exit code. Material's MkDocs-2.0 notice may print a
large red-looking banner even on a successful build; do not treat that text alone as failure.
Pre-existing breakage isn't yours to fix (or to be blamed for), but you must not add any.

---

## Phase 2 — Audit Queue

Enumerate the live doc set first — never audit from a remembered file list, because files get
added and deleted between runs:

```bash
find docs -name '*.md' | sort
```

Then process by directory tier, highest drift risk first:

**Tier 1 — Reference & contracts (check every claim)**
- `docs/reference/` — API, schemas, CLI, MCP tools, versioning
- `docs/contracts/` — ⚠️ special rules, see Phase 3

**Tier 2 — Getting started (misleads devs most if wrong)**
- `docs/getting-started/`, `docs/quickstart.md`, root `README.md`

**Tier 3 — Architecture & internals**
- `docs/architecture/`, `docs/internals/`

**Tier 4 — Development, guides, operations**
- `docs/development/`, `docs/guides/`, `docs/deployment/`, `docs/operations/`

**Tier 5 — Concepts, features, everything else**
- `docs/concepts/`, `docs/features/`, `docs/llm/`, `docs/ml-training/`, any remaining live dirs

**Skip — historical and non-doc content:**
- `docs/solutions/`, `docs/reports/`, `docs/superpowers/`, and `docs/audits/` — dated,
  point-in-time working records. Also treat any file with a `-YYYY-MM-DD.md` filename, an
  explicit historical banner, or membership in a `not_in_nav` glob as a working record.
  Verify these for broken paths and misleading current-status labels, but never rewrite their
  historical claims to match today's code.
- `docs/adr/` — architecture decision records are frozen at decision time. If one is badly
  invalidated by later changes, flag it ⚠️; never rewrite it.
- `docs/CHANGELOG.md` — historical release record and oracle only; verify references against it
  but never rewrite its historical entries.
- Root `AGENTS.md` and `CLAUDE.md` — operator contract files. Flag factual drift ⚠️ in the
  report; do not edit them without explicit approval.
- Markdown outside `docs/` and the root: `.remember/`, `logs/`, `backups/`,
  `data/sigma-repo/` (vendored upstream), `tests/allure-results/`, `node_modules/`,
  `.opencode/`, `.context/` — generated, vendored, or session artifacts. Not documentation.

If the user names a focus area, still run Phase 1 in full (oracles are cheap and every fix
depends on them), audit the named tiers deeply, and skip the rest — note the reduced scope in
the report.

---

## Phase 2.5 — Corpus-Wide Mechanical Sweep

Before deep reading, run cheap, repeatable checks across the entire in-scope corpus. This phase
is specifically for contradictions that are invisible when each file is read in isolation.
Record every hit and add flagged files to the Phase 3 deep-read queue.

Run at minimum:

1. **Backticked paths:** extract every backticked path-like token and check that it exists,
   allowing documented runtime/container paths and intentional placeholders to be classified
   rather than blindly rewritten.
2. **Canonical names:** grep for non-canonical agent spellings across all live docs. Compare
   against the schema-derived set and the code's `ALL_AGENT_NAMES`/`AGENT_DISPLAY_NAMES` data.
   `OSDetectionAgent` is a valid display/flat-key name, but it is not an `ALL_AGENT_NAMES` member
   and is invalid as a `Prompts` key; do not "correct" a valid display name toward a prompt key.
3. **Structure:** check every file for one H1, no heading-level skips, balanced fenced blocks,
   and language tags on fenced code blocks.
4. **Runtime vocabulary:** validate environment variables, ports, Docker service names, table
   names, test suite names, and CLI flags against the live scripts/configuration.
5. **Known drift tokens:** search for removed subsystem names, prior-run audit markers, stale
   versions, and known spelling variants from Phase 1 removals.
6. **Corpus consistency:** search names, versions, commands, and claims that appear in multiple
   files and compare the results for contradictions; a canonical sibling is evidence to
   investigate, not an oracle to copy without checking code.

The sweep is a detector, not an auto-fixer. Resolve each hit against the Phase 1 oracles. Its
completion criterion is an explicit disposition for every hit: fixed, intentionally historical,
valid exception, unverifiable, or escalated for review.

---

## Phase 3 — Per-File Validation

For each file in the deep-read queue — Tier 1–2 plus every file flagged by Phase 2.5 — check
these dimensions. Read the doc, then verify each claim against the oracle files loaded in Phase 1.

### ACCURACY — check every concrete claim

Cross-reference these against the codebase:
- **File paths**: does the path exist on disk?
- **CLI commands**: is the command valid against the relevant live CLI implementation? Test
  suite names come from `tests_runner/config.py` (`RunTestType`); flags come from
  `tests_runner/cli.py`, not the `run_tests.py` re-exec shim.
- **Host test commands**: use `python3 run_tests.py ...` for a bare host invocation. Do not
  "correct" `python -m ...` inside a container-command example or a `.venv/bin/python`
  invocation; those are deliberate and valid contexts.
- **API routes**: does the route exist in `src/web/routes/__init__.py`?
- **Config keys**: does the key exist in `workflow_config_schema.py`?
- **Model/field names**: does the name exist in `src/database/models.py`?
- **Agent names**: exactly match the canonical set you derived in Phase 1
- **Docker service names**: check `docker-compose.yml` or `docker-compose.override.yml`
- **Environment variables**: check `setup.sh`, `.env.example`, or startup scripts
- **Version numbers**: does the doc's stated version match `pyproject.toml` or `CHANGELOG.md`?

If you cannot verify a claim from codebase artifacts, mark it as unverifiable — do not assume
it's correct.

### CONTRACTS — docs/contracts/ gets inverted handling

The files in `docs/contracts/` are contract *sources of truth*: code is supposed to conform to
them, not the other way around. A mismatch between a contract doc and the code may mean the
**code** has drifted — "fixing" the doc to match buggy code would erase the spec. So for this
directory only:
- Verify paths, names, and cross-references as usual; fix obvious mechanical staleness
  (a renamed file path, a dead link).
- For any behavioral or schema mismatch with the code, do NOT edit the contract. Flag it ⚠️
  with both sides of the discrepancy and name it a contract-guardian candidate.

### CONSISTENCY — naming and convention alignment

- Agent names must use their canonical PascalCase form from `workflow_config_schema.py`.
  Treat `OSDetectionAgent` as the documented display/flat-key exception described in Phase 2.5;
  it is not a valid `Prompts` key.
- Bare host test invocations should use `python3 run_tests.py`; do not change container
  commands or venv-qualified paths such as `python -m ...` and `.venv/bin/python`.
- No legacy component names (e.g., old worker names, renamed routes, removed extractors)
- No mixed conventions for the same thing (e.g., "step 3" vs "ExtractAgent")

### GAPS — blocking omissions only

Only flag what would actually break someone:
- Missing required env var that the app won't start without
- Missing migration step that would corrupt data
- Example that silently produces wrong output

Ignore: missing explanations, incomplete context, anything stylistic.

### RELEVANCY — removed-subsystem drift

Check the doc against the removals you mined in Phase 1 (CHANGELOG + `git log --diff-filter=D`).
A doc presenting a removed subsystem as current gets its false present-tense claims corrected
minimally (e.g., "removed in v7.4 — see CHANGELOG") — that's a factual fix and in scope. But
whole-page obsolescence is not yours to resolve: flag it ⚠️ in the report and note it as a
doc-overhaul candidate. Deletion and merging belong to that skill, not this one.

### MKDOCS — rendering and navigation

- Single H1 per file
- No heading-level skips (H1 → H3 without H2)
- Fenced code blocks have a language tag (`python`, `bash`, `yaml`, `json`, etc.)
- Relative links: check that the target file exists at the relative path
- No raw HTML unless there's no Markdown equivalent
- Every live doc should be reachable from `mkdocs.yml` nav (the `not_in_nav` globs there are
  deliberate exclusions, not omissions). A new doc missing from nav is worth flagging —
  `--strict` will catch it, but say so in the report rather than letting the build error speak.

---

## Phase 4 — Apply Fixes

Fix confirmed issues directly. Rules:
- Fix only what you've verified is wrong — don't "improve" things that might be correct
- If a claim is unverifiable, flag it in the report but do not rewrite it
- If a fix requires changing a code example, verify the corrected example against actual code
- Keep changes minimal: update the wrong thing, leave the surrounding text alone

After all fixes, run `.venv/bin/python -m mkdocs build --strict` again — the result must be no
worse than the Phase 1 baseline. Judge by exit code; Material's MkDocs-2.0 notice can emit a
red-looking banner on a successful build. A fix that breaks a link or nav entry isn't a fix.

If asked to commit, commit discipline is:
- Small thematic commits (one per directory or tier). Stage explicit paths — never
  `git add -A`; parallel sessions may have uncommitted work you must not sweep up.
- Multi-`-m` commit messages, no heredocs.
- If pre-commit hooks modify files, re-stage and retry up to 3 times; if still failing,
  stop and show the diff and hook errors.
- Do not push unless instructed.

---

## Phase 5 — Triage Report

End with a scalable summary. List every fixed, flagged, or skipped file individually. Collapse
clean files into one or more grouped rows (for example, `docs/reference/*.md` — 18 files — ✅
current) rather than producing an unusable 94-row table. If an evaluation or report contract
requires a status symbol for every audited file, the grouped row must enumerate or otherwise
cover each file; update the contract/eval when it incorrectly requires expanded rows.

```
## huntable-doc-trueup Summary

Audited: N files | Fixed: N files | Flagged: N | Skipped: N

| Files | Status | Issues |
|-------|--------|--------|
| docs/reference/*.md (18 clean files) | ✅ current | — |
| docs/getting-started/installation.md | 🔧 fixed | 2 accuracy, 1 mkdocs |
| docs/reference/schemas.md | ⚠️ needs review | 1 unverifiable claim (see inline) |
```

Status legend:
- ✅ **current** — no issues found
- 🔧 **fixed** — issues found and corrected
- ⚠️ **needs review** — unverifiable claim, contract mismatch, or ambiguous fix

For each fixed or flagged file, add a one-line summary of what changed or what needs attention.
Do not leave an inline marker for a claim you verified as false: correct the visible prose and
remove the marker. Inline `<!-- TODO: verify: ... -->` comments are reserved for claims that
remain genuinely unresolved after the audit, because HTML comments are invisible on the built
site.

If you discovered drift in this skill file itself (Phase 1/2 assumptions that no longer hold),
end the report with a short "Skill drift" note listing what to update in
`~/.hermes/skills/huntable-doc-trueup/SKILL.md`.

---

## Behavioral Rules

**Verify, then write.** Never rewrite a sentence you haven't cross-referenced against an oracle
file. "Looks right" is not verification.

**Factual only.** Don't improve phrasing, add context, reorder sections, or enhance examples
unless the existing content is objectively wrong.

**No invented content.** If something is missing from a doc but you're not sure what the correct
content is, flag the gap — don't fill it with guesses.

**Inline comments are for unknowns, never known-wrong text.** Add
`<!-- TODO: verify: [what to check] -->` only when a claim genuinely remains unresolved after
checking the oracles. If you verified a claim is false, correct the visible prose and strip any
old audit marker; HTML comments do not render on the built site and must not hide known drift.

**Scope awareness.** You're auditing docs, not doing a code review. Don't comment on code quality,
test coverage, or architecture — stay in your lane. The one exception: a contract-vs-code
mismatch gets flagged (never fixed on either side) because the code may be the wrong party.
