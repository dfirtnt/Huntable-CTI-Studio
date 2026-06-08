# Sigma Similarity Rendering — Unification Refactor Plan

**Date:** 2026-06-05
**Branch context:** europa-7.2.1
**Status:** Planned, not started. Intended home is Todoist (project "Huntable CTI Studio", id `6cm4mfcPqvJxXW23`) as a parent + 6 subtasks (Phases 0–5). This file is the durable backup written because the Todoist connector was down at authoring time.

> **Line-number caveat:** Every line number below came from subagent exploration. It is **directionally correct but approximate** — re-confirm exact lines before editing. File names, function names, and route paths are reliable.

---

## 1. Why this exists (the problem)

Sigma rule **similarity analysis** is shown in **5 live UI surfaces**. All five compute through **one** backend engine, but:

- **Layer 2 (endpoint shaping)** is forked — each route hand-builds its own response dict (different nesting, rounding, field pruning).
- **Layer 3 (frontend render)** is forked into **3 code paths** — one shared component plus two hand-rolled renderers.

Result: **a fix in one place does not propagate.** Concrete symptom that triggered this plan — on 2026-06-05 a containment-metric relabel (showing `overlap_ratio_a` as "Containment", relabeling the old hardcoded 0.65 metric as "Logic Shape") could only land in the **queue** renderer, because the queue is the *only* surface that reads `overlap_ratio_a` at all.

---

## 2. The 5 live surfaces

| # | Surface | URL | Template | Route / endpoint |
|---|---------|-----|----------|------------------|
| 1 | Sigma Similarity Test | `/sigma-similarity-test` | `src/web/templates/sigma_similarity_test.html` | `src/web/routes/sigma_similarity_test.py` — `POST /api/sigma-similarity-test/search` |
| 2 | Sigma A/B Test | `/sigma-ab-test` | `src/web/templates/sigma_ab_test.html` | `src/web/routes/sigma_ab_test.py` — `/compare` and `/compare-to-repository` |
| 3 | Sigma Queue review | `/sigma-queue` | `src/web/templates/sigma_queue.html` | `src/web/routes/sigma_queue.py` — similarity cached in `SigmaRuleQueueTable.similarity_scores` |
| 4 | Workflow Config | `/workflow` | `src/web/templates/workflow.html` | threshold slider + queue similarity column |
| 5 | Workflow Executions | `/workflow-executions` | `src/web/templates/workflow_executions.html` | similarity results summary per execution |

### Vestigial 6th surface (do NOT count as live)
The **Article Detail `#sigma` modal** in `src/web/templates/article_detail.html` (backend `GET /api/articles/{id}/sigma-matches` in `src/web/routes/ai.py` ~line 2416) is a leftover from the **deprecated AI/ML Assistant modal** (deprecated in commit `a2a245f2`, ~v5.2.0, 2026-01-21). There is **no button entrypoint** anymore — the "Generate Sigma Rules" trigger and the regenerate buttons were gutted to deprecation notices. The container modal only auto-opens via the `/articles/{id}#sigma` URL fragment, for articles that already have `sigma_rules` stored in metadata, and the `🔍 Similarity Search` button inside is further gated on the article having an embedding. The backend endpoint is **still live** and still re-implements novelty thresholds (see Phase 2). **Decision deferred to Phase 5:** delete it outright vs. fold it in.

---

## 3. The architecture (3 layers)

- **LAYER 1 — ENGINE: healthy / unified.** All surfaces compute via `SigmaNoveltyService` (wrapped by `SigmaMatchingService.assess_rule_novelty()`). Formula: `0.70·atom_jaccard + 0.30·logic_shape − service_penalty − filter_penalty`. Numbers are consistent. Files: `src/services/sigma_novelty_service.py`, `src/services/sigma_matching_service.py`. There is also an optional deterministic engine (the `sigma_similarity` package / `sigma_semantic_scorer.py`) producing `jaccard`, `containment_factor`, surface scores, and `similarity_engine: "deterministic"` vs `"legacy"`; it is transparent to endpoint consumers.

- **LAYER 2 — ENDPOINT SHAPING: forked.** Each route hand-builds its response dict:
  - `sigma_similarity_test.py` — nests metrics under `similarity_breakdown{}`, rounds to 4 places.
  - `sigma_ab_test.py /compare` — flat keys, rounds.
  - `sigma_ab_test.py /compare-to-repository` — returns **only 3 fields** (rule_id, title, similarity, atom_jaccard, logic_shape_similarity); strips novelty, atoms, penalties.
  - `sigma_queue.py` — passes the **full raw record** through, no rounding; cached in DB column.
  - `ai.py /sigma-matches` — **re-implements** novelty thresholds locally and derives `coverage_status`.

- **LAYER 3 — FRONTEND RENDER: forked into 4 paths** (originally audited as 3 — the workflow path was missed; see (d)).
  - (a) Shared component `src/web/static/js/components/similarity-display.js` — exposes `renderSimilarityDisplay()`, `updateSimilarityDisplay()`, `normalizeSimilarityData()`, `calculateNoveltyLabel()`, `getNoveltyLabelClasses()`. Modes: `full` / `compact` / `minimal`. Used by the A/B test page (`updateSimilarityDisplay`).
  - (b) **Queue** hand-rolls `buildSimilarityDetailHtml()` + adapters `mapSimilarityResponse()` / `mapSimilarityResponseFromCache()` in `sigma_queue.html` (~lines 616–752). **This is the code path the containment bug lived in.** Reads `m.containment` from `semantic_details.overlap_ratio_a`, `m.logic_shape` from `semantic_details.containment_factor`, `m.jaccard` from `semantic_details.jaccard ?? atom_jaccard`.
  - (c) **Test page** hand-rolls `displayResults()` in `sigma_similarity_test.html` (~lines 257–299) with its own hardcoded `0.90 / 0.75` color thresholds.
  - (d) **Workflow / Workflow-Executions** hand-roll `showSimilarRuleDetails()` — **duplicated verbatim** in `workflow_executions.html` (~line 1444) AND `workflow.html` (~line 16740). This is the MOST impoverished renderer: it shows only Title / Description / Rule ID / Status / Similarity% / File Path / Tags / Log Source / Detection — **no atom-Jaccard, Logic-Shape, Containment, or shared-atoms breakdown at all.** IMPORTANT: this is a pure RENDERER gap, not a data gap — the workflow stores full engine matches (`similar_rules = match_result["matches"]`, `agentic_workflow.py:2256/2275`), so `ruleData` already carries `atom_jaccard` / `logic_shape_similarity` / `shared_atoms` / `semantic_details`; the template just never renders them. Phase 1 does not and cannot fix this (it reads persisted execution data, not the serialized live endpoints), so it is squarely a Phase 4 frontend fix needing no backend/data change.

---

## 4. IMPORTANT CORRECTION (folded in — do not re-litigate)

The `sigma-similarity-test` page is **NOT embedding-based at compute time.** Its route calls the **behavioral** engine `assess_rule_novelty()` just like the others:
- `sigma_similarity_test.py` ~line 90: `matching_service.assess_rule_novelty(...)`.
- ~line 137: it self-labels `embedding_model or "behavioral-novelty-engine"` — the `embedding_model` request param is a vestige.
- The backend builds `similarity_breakdown` with **only** `atom_jaccard` + `logic_shape_similarity` (~lines 100–119).

But the frontend block at `sigma_similarity_test.html` ~lines 274–294 reads `breakdown.title`, `.description`, `.tags`, `.signature` and renders each as `(value * 100).toFixed(1)%`. The backend **never returns those sub-fields**, so they evaluate to `undefined` → **the page renders literal `NaN%`** for all four. This is **dead code from the old embedding era.**

**Consequences:**
1. There is **no embedding-aware exception** — all 5 surfaces are the same behavioral metric, so all 5 are legitimately unifiable onto `renderSimilarityDisplay()`.
2. Deleting the dead `title/description/tags/signature` block (Phase 4) is also a **free bug fix** (removes the `NaN%`).

**Embeddings are out of scope.** The embedding/cosine machinery (`src/services/embedding_service.py`, `src/services/rag_service.py`) is a **separate retrieval concern** serving semantic search + the MCP tools (`search_articles`, `search_sigma_rules`, `search_unified`) and the web search routes (`search.py`, `articles.py`, `embeddings.py`). Two different meanings of "similar" — **behavioral** (atom/logic, the 5 widgets) vs **semantic/vector** (retrieval) — are conflated by naming. **Do not merge them.**

---

## 5. Canonical contract (decided in Phase 0, used everywhere after)

**Canonical match fields:** `similarity`, `atom_jaccard`, `logic_shape_similarity`, `containment` (← canonical name for the metric currently called `overlap_ratio_a`), `shared_atoms`, `added_atoms`, `removed_atoms`, `filter_differences`, `novelty_label`, `novelty_score`, `similarity_engine`, `semantic_details{}`.

**Kill the naming ambiguity:** `overlap_ratio_a` vs `containment` vs `containment_factor` must resolve to one canonical name each; all else becomes an adapter alias.

**One threshold table** (referenced by BOTH backend and frontend; no more hardcoded `0.90/0.75`):
- Legacy engine: DUPLICATE = `atom_jaccard > 0.95 AND logic_shape > 0.95`; SIMILAR = `atom_jaccard > 0.80`; else NOVEL.
- Deterministic engine: DUPLICATE = `similarity >= 0.75`; SIMILAR = `similarity >= 0.50`; else NOVEL.

---

## 6. Sequenced phases (do in order)

### Phase 0 — Lock the contract (no behavior change)
**Goal:** write down the canonical match schema + the single threshold table before touching code.
**Deliverable:** short contract note (this doc's §5, or a dedicated file). Decide canonical names for the containment/logic-shape fields.
**Risk:** none. **Depends on:** nothing.

### Phase 1 — Backend: single serializer (highest leverage, lowest risk)
**Goal:** all 5 endpoints emit the Phase-0 shape via one function.
**Do:**
- Add `serialize_similarity_match(match) -> dict` (in `src/services/sigma_matching_service.py` or a new `similarity_serialization.py`).
- Replace the per-route hand-built dicts in `sigma_similarity_test.py`, `sigma_ab_test.py` (`/compare` AND `/compare-to-repository` — restore the stripped fields), `sigma_queue.py`, and `ai.py /sigma-matches`.
- Standardize rounding **inside** the serializer (one policy).
- Ship behind **additive aliases**: emit BOTH canonical and legacy keys so frontends keep working until Phase 3/4. Aliases removed in Phase 5.
**Risk:** medium (response shapes change) — mitigated by additive aliases.
**Verify:** extend `tests/api/test_sigma_ab_test_api.py`, `tests/api/test_sigma_similar_rules_api.py`. Run via `run_tests.py`.
**Depends on:** Phase 0.

### Phase 2 — Backend: dedup the novelty classifier ✅ DONE (2026-06-05)
**Goal:** one classifier.
**Plan-vs-reality correction:** the original plan said "delete ai.py's loop and trust the engine's `novelty_label`." On inspection that would have **regressed** behavior: `SigmaNoveltyService.classify_novelty` returns a *single* verdict from `matches[0]`, and `assess_rule_novelty` broadcasts that one label to *every* match (sigma_matching_service.py ~line 587/607). ai.py classifies **per match** — which is what the article coverage view (covered/extend/new per existing rule) needs. So the faithful "one classifier" fix was **extraction, not deletion**.
**What was done:**
- Added `classify_match_novelty(match) -> NoveltyLabel` to `sigma_novelty_service.py` — single source of truth for the legacy atom/logic thresholds + exact-hash override + None-logic handling.
- Refactored `SigmaNoveltyService.classify_novelty` to delegate its label to it (kept its score semantics: exact→0.0, else 1.0−weighted_sim).
- Replaced ai.py's inline ~25-line classifier with `classify_match_novelty(match)`, preserving per-match semantics and the article-specific `novelty_label → coverage_status` mapping.
**Tests:** `tests/services/test_classify_match_novelty.py` (7, incl. a per-match regression guard). Existing novelty (55) + matching (20) suites green — proves `classify_novelty` behavior unchanged.
**Risk:** low. **Depends on:** Phase 1.

### Phase 3 — Frontend: single ingress through `normalizeSimilarityData()`
**Goal:** no surface reads raw response fields directly.
**Do:**
- Extend `normalizeSimilarityData()` in `similarity-display.js` to absorb `containment` / `semantic_details.*` / surface scores plus the legacy aliases from Phase 1.
- Pull novelty thresholds + metric labels into one exported constants object (the Phase-0 table); every surface imports it. Removes the hardcoded `0.90/0.75` on the test page and the duplicate cutoffs.
**Risk:** low (additive adapter).
**Verify:** unit-level — feed each endpoint's sample payload to `normalizeSimilarityData`, assert identical normalized output.
**Depends on:** Phase 1.

### Phase 4 — Frontend: retire the FOUR hand-rolled renderers (structural payoff)
**Goal:** one widget.
**Do:**
- **Queue:** replace `buildSimilarityDetailHtml()` + `mapSimilarityResponse()` / `mapSimilarityResponseFromCache()` in `sigma_queue.html` with `renderSimilarityDisplay(match, { mode: 'compact' })`. Queue's chip + expandable-detail needs are expressible via `mode: 'compact'` + `includeExplainability`. **Retires the exact path the containment bug lived in.**
- **Test page:** delete the dead `if (match.similarity_breakdown){ title/description/tags/signature }` block (`sigma_similarity_test.html` ~lines 274–294) — **fixes the `NaN%`** — and swap `displayResults()`'s metric section for the shared component rendering the real `atom_jaccard` / `logic_shape` / `containment` it already receives.
- **Workflow + Workflow-Executions:** replace `showSimilarRuleDetails()` — **duplicated verbatim** in `workflow_executions.html` (~line 1444) AND `workflow.html` (~line 16740) — with `renderSimilarityDisplay(ruleData, { mode: 'compact' })`. This is the surface that currently shows NO breakdown (only title/desc/id/status/similarity/path/tags/logsource). The data is already present in `ruleData` (full engine match stored by the workflow), so this needs no backend/data change — and it collapses TWO duplicated copies into the shared component. (Found 2026-06-05 by operator inspecting `/workflow#executions` → "Similar Rule Details" modal.)
- **A/B test:** already uses `updateSimilarityDisplay()` — confirm it's on canonical fields.
**Risk:** medium (visible UI).
**Verify:** pytest **template-contract tests** (NOT the live :8001 browser — :8001 is Docker-served from the MAIN tree, not a worktree). Browser/screenshot verify only AFTER merge to the served tree.
**Depends on:** Phase 3.

### Phase 5 — Cleanup vestiges
**Do:**
- Drop the legacy aliases emitted in Phase 1.
- Remove the `embedding_model` request param + `"behavioral-novelty-engine"` label from `sigma_similarity_test.py` and the unused form field in the template.
- Confirm `similarity-display.js` is the ONLY similarity renderer left; remove orphaned helpers.
- **Decide the vestigial Article Detail `#sigma` modal:** delete the orphaned modal + its 3 deprecated-notice buttons + the (otherwise unreachable) `GET /api/articles/{id}/sigma-matches` endpoint, OR re-home it onto the shared component if there's a real use case.
**Risk:** low.
**Verify:** full `run_tests.py`; grep that no template reads raw similarity fields directly.
**Depends on:** Phases 1–4 merged and stable.

---

## 7. Scope guard & verification discipline

- **Out of scope:** embedding/vector retrieval (search + MCP). This refactor unifies only the **behavioral** similarity widget.
- **Canonical test entrypoint:** `run_tests.py`. Do **not** pipe test output through `| tail` or similar buffering filters.
- **Template edits** verified via pytest template-contract tests, not the live `:8001` browser (Docker-served from main tree). Browser-verify only after merge.
- **Contract sources of truth:** `src/config/workflow_config_schema.py`, `src/database/models.py`.
- **Smallest safe first commit:** Phase 1 serializer behind additive aliases — high leverage, reversible, no UI change.
