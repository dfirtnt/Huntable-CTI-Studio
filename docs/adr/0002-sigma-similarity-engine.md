# ADR-0002: SigmaSimilarity Engine — Atom-Based Jaccard × Containment Deduplication

- **Status:** Accepted
- **Date:** 2026-06-11
- **Author:** dfirtnt + Huntable engineering session series, 2026-06-01 → 2026-06-11
- **First ADR in `docs/adr/`.** No prior ADR formally established the embedding-cosine path that this one retires; the prior state is reconstructed below from code and git history.

## Context

Huntable CTI Studio ingests open-source threat-intelligence articles and runs a LangGraph workflow whose terminal stage drafts Sigma detection rules. Once drafted, every candidate rule must be compared against the existing corpus — the SigmaHQ rule base plus prior customer-approved rules — to decide whether it is **NOVEL** (worth queueing for human review), **SIMILAR** (worth surfacing as a neighbour but not enqueuing again), or a **DUPLICATE** (suppress). The same scoring is reused interactively from `/sigma-queue`, `/sigma-ab-test`, the workflow-execution detail pages, and the article-coverage panel, so any divergence between paths shows up as conflicting verdicts on the same rule.

Rule similarity is hard for three reasons.

First, two YAML files can look very different but mean the same thing. `Image|endswith: '\rundll32.exe'` and `Image: '*\rundll32.exe'` are byte-distinct but behaviorally identical; so are `CommandLine` vs `process.command_line`, `windows.process_creation` vs `service: sysmon` + `EventID: 1`, and a `1 of selection_*` shorthand vs the disjunction it expands to. Surface diffs and YAML hashes treat these as different rules. They are not.

Second, two rules that share an atom (say, `Image|endswith: '\powershell.exe'`) can be detecting wildly different tradecraft if their *other* atoms diverge. An embedding-cosine score over title+description+detection text gives high similarity for both pairs above without any way to interrogate *why*. The analyst cannot see what overlapped.

Third, the Sigma corpus is structured. Detections decompose into atoms (`field|modifier_chain|value`), atoms compose via `and`/`or`/`not` into a DNF, and rules belong to a small set of telemetry classes (`windows.process_creation`, `windows.registry_event`, `windows.network_connection`, …). An embedding throws that structure away. A deterministic algorithm that respects it can produce explanations the analyst can act on — shared atoms, missing atoms, asymmetric containment, filter (NOT-clause) drift.

Before this work, the codebase carried two incompatible mechanisms. A `SigmaSemanticScorer` (deleted in `119a687d`) computed cosine over OpenAI/local embeddings of a serialized rule. A separate in-app pairwise scorer inside `SigmaNoveltyService` computed a homegrown Jaccard over `(field, op, value)` keys. Their results disagreed; both were called from UI; neither could explain *why* two rules were close. `sigma_rules` carried three write-only embedding columns nobody read (dropped in `2d0ce5a9`). The two-extractor split was the root cause of the polarity bug filed as `6gqhWHxjgpWGHGP3` — the live extractor and the precomputed extractor disagreed on which atoms were positive vs negative for the same rule.

This ADR records the deterministic atom-set engine that replaced both paths, the canonicalization spec that lets it match behaviorally identical syntactic variants, the read-only pair-mining tool that surfaces its blind spots, the unified UI that renders its output, and the engineering work it took to retire embeddings from the dedup path.

## The Core Design Decision

The engine compares two Sigma rules by reducing each to a sorted set of canonical positive atoms and a sorted set of negative atoms, then scoring the pair with:

```
similarity = clamp(0, 1, Jaccard(A1, A2) × Containment(A1, A2) − FilterPenalty(F1, F2))
```

All three terms are implemented in the standalone `sigma_atom_similarity` package (formerly `sigma_semantic_similarity`, renamed in `76be4c24`). The package has no I/O, no global state, and no dependence on the Huntable app — it takes two rule dicts and returns a `SimilarityResult` dataclass.

### Positive atoms

An atom is the smallest behavioral predicate in a Sigma detection: one field, one operator (possibly with modifiers), one value. Its identity string lives in the column `sigma_rules.positive_atoms` (JSONB array) and takes the **3-slot form**:

```
field | modifier_chain | normalized_value
```

The operator is *not* stored separately. It is recoverable as `modifier_chain.split("|")[0]`, with an empty chain denoting the default `eq`. The 3-slot format landed in `f7ad0813`; the corpus was rewritten to it in `3626e795`. The prior 4-slot form had stored the operator twice (once explicitly, once as the first modifier token), producing identities like `Image|endswith|endswith|\rundll32.exe` that displayed redundantly in the UI and broke containment math for `|all` chains.

Atom identities are produced by `sigma_atom_similarity/sigma_similarity/atom_extractor.py::atom_identity`. Field names are resolved through `FIELD_ALIAS_MAP` (PascalCase → canonical, plus a lowercase / snake_case fallback for LLM-generated rules so `process_path` and `Image` and `ProcessPath` all fold to `process.image`). Values are normalized: backslashes deterministically, case folded for Sigma's case-insensitive operators (`contains`, `endswith`, `startswith`, `eq` unless `|cased` is present), regex preserved verbatim. Edge wildcards on `eq` are folded into the equivalent modifier (`*foo*`-as-eq becomes `foo`-as-contains, `*foo`-as-eq becomes `foo`-as-endswith). The `|cased` modifier defeats case-folding so two rules hunting different literal casings of the same token are not collapsed into one (`4b94e175`).

Atoms are extracted from the *normalized detection block*, not the raw YAML and not the title or description. The pipeline is: `normalize_detection` (parse condition with a hand-written recursive-descent parser, resolve `selection_*` references, reject unsupported features) → `build_ast` (AND/OR/NOT/atom tree) → `ast_to_dnf` (disjunctive normal form, with an expansion limit that raises `DeterministicExpansionLimitError` for pathological cases) → `extract_positive_atoms` / `extract_negative_atoms`. Negative atoms are only extracted under `AND NOT` (a branch with at least one positive literal); naked `NOT` under `OR` is dropped because the engine cannot meaningfully reason about it.

### Canonical telemetry class

The engine compares two rules only if both resolve to the same canonical telemetry class. `sigma_atom_similarity/sigma_similarity/canonical_logsource.py::CANONICAL_CLASS_REGISTRY` maps `(product, category, service, event_id)` tuples to class names — `windows.process_creation`, `windows.registry_event`, `windows.file_event`, `windows.image_load`, `windows.network_connection`, `windows.dns_query`, `windows.process_access`, `windows.pipe_created`, `windows.create_remote_thread`, `windows.driver_load`, `windows.create_stream_hash`, `windows.ps_script`, `windows.ps_module`, `windows.ps_classic_start`, `windows.service`, `windows.scheduled_task`, `network.dns`, `web.webserver`, `web.proxy`, `linux.process_creation`, `macos.process_creation`. The registry consolidates fragmented SigmaHQ vocabulary: `registry_event` / `registry_set` / `registry_add` / `registry_delete` are one class because they share Sysmon EID and `TargetObject`; `file_event` / `file_delete` / `file_access` / `file_rename` / `file_change` are likewise one class. PowerShell remains three distinct classes (Script Block, Module, Classic Start) because each emits a different EID and a different field — folding them would force a field-alias decision with false-merge risk. EventCode is recognized as EventID at the resolver to handle Splunk-backend rules (`8a9adb19`, Finding A).

If a rule fails to map, the engine raises `UnknownTelemetryClassError`. The caller (here, `SigmaNoveltyService.assess_novelty`) catches it, marks the rule unassessable, and routes it to `needs_review` rather than silently calling it NOVEL (`75d2eca5`). Class mismatch — both rules resolve, but to different classes — is *not* an error: the engine returns `similarity=0.0` with `reason_flags=["canonical_class_mismatch"]`.

### Jaccard

Once both rules resolve to the same class and the atom sets are extracted, the engine computes Jaccard over positive atoms:

```
J = |A1 ∩ A2| / |A1 ∪ A2|
```

If the intersection is empty, the engine short-circuits to `similarity=0.0` with `reason_flags=["no_shared_atoms"]` — there is no behavioral overlap to score. Otherwise `J ∈ (0, 1]`.

### Containment

Jaccard alone is symmetric and penalizes subset relationships. If rule A has 3 atoms `{x, y, z}` and rule B has 4 atoms `{x, y, z, w}`, A is fully contained in B but Jaccard is only `3/4 = 0.75`. For dedup we *want* that pair flagged: A and B detect the same behavior plus one extra constraint. Containment captures it.

`compute_containment(intersection_size, |A1|, |A2|, surface_a, surface_b)` returns a directional factor `B` and the two overlap ratios `overlap_a = |A1∩A2|/|A1|`, `overlap_b = |A1∩A2|/|A2|`. The factor bucket (`sigma_atom_similarity/sigma_similarity/containment_estimator.py`):

- **Equivalent** (`B = 1.0`) — both overlaps ≥ 0.9 and surface size differs by ≤ 10%.
- **Subset** (`B = 0.85`) — `overlap_a ≥ 0.9` and `surface_a < surface_b` (A's atoms are nearly all in B, A is the smaller rule).
- **Superset** (`B = 0.75`) — `overlap_b ≥ 0.9` and `surface_a > surface_b`.
- **Else** (`B = 0.65`) — partial overlap, no containment relationship.

"Surface" here is the DNF branch count (`surface_estimator.py`). It captures *logical breadth* — a rule with one selection has surface 1; a rule with `selection_a or selection_b or selection_c` has surface 3 once the selections are AND-of-atoms each. Surface is also persisted on `sigma_rules.surface_score`.

### Filter penalty

Negative atoms (NOT clauses) never increase similarity. They only subtract. `filter_penalty(F1, F2, |A1|, |A2|)` computes:

```
F = min(0.5, |F1 △ F2| / max(|A1|, |A2|))
```

where `△` is symmetric difference. The capped 0.5 ceiling exists because two rules with very different filter sets should not be driven negative — they may still describe the same positive behavior with different exclusions. Filters never enter the positive Jaccard; their entire effect is the subtraction.

### Why both Jaccard and Containment

Either alone is wrong. Jaccard alone marks every subset relationship as "not very similar" — the very case dedup most wants to catch (a rule that is a stricter version of one already in the corpus). Containment alone marks every rule whose atoms are a subset of any other rule as fully similar — which makes a 1-atom generic catchall (e.g. `Image|endswith: '\powershell.exe'`) look identical to every PowerShell-targeting rule. The product `J × B` rewards atom-set overlap *and* makes the score directional in the containment bucket. The downstream classifier (see *Implementation* below) reads `J`, `B`, and the final `similarity` independently so the analyst can disambiguate.

### The decision not to use embeddings here

Embeddings are still used elsewhere in Huntable. `SigmaRuleTable` retains two Vector(768) columns — `embedding` (whole-rule text) and `logsource_embedding` (a "signature" vector built from logsource + detection structure + detection fields). `SigmaMatchingService.match_article_to_rules` (`src/services/sigma_matching_service.py`) compares an article's embedding against each Sigma rule's `logsource_embedding` via pgvector cosine (`<=>`) to drive article-to-rule lookup. Articles and chunks carry their own embeddings for semantic article search. Embeddings are the right tool for "find me articles that look like this article" because articles are free-form natural language. They are the wrong tool for "is this proposed Sigma rule a dedup of one we already have." A rule has structure that maps cleanly to a set; embeddings throw the structure away in exchange for fuzziness the rule corpus does not need.

Concretely: an embedding similarity of 0.93 tells the analyst nothing about *why*. An atom-set similarity of 0.93 comes with shared/added/removed atom lists the UI renders inline. Embeddings also gave us the worst kind of failure mode — they produced numerically plausible scores for rules the analyst confirmed were unrelated, and we had no way to interrogate the score. The dedup path moved to deterministic atom set math; embeddings were retired from this surface in three commits: `119a687d` deleted the `SigmaSemanticScorer`; `2d0ce5a9` dropped five write-only Vector(768) columns on `SigmaRuleTable` (`title_embedding`, `description_embedding`, `tags_embedding`, `detection_structure_embedding`, `detection_fields_embedding`) — repo-wide grep found no readers; only `embedding` and `logsource_embedding` survive because they are the two vectors `match_article_to_rules` actually scores. `da3fd216` then removed the last embedding vestiges from the `/compare` response.

## Alternatives Considered

- **Embedding + cosine similarity.** Rejected. Loses structure; cannot explain *why* two rules are close; produces plausible-looking false positives that look like signal. Still appropriate for article ingestion and free-text similarity, retained there.
- **Full YAML string diff** (Levenshtein or normalized line diff). Rejected as brittle. Field order, comment placement, list-vs-map authoring style, single-quote-vs-double-quote, and `selection_*` naming all change the string without changing the rule. Worse, the diff size has no useful meaning — a five-line change reordering atoms is "more similar" than a one-character change that flips polarity.
- **`exact_hash` alone.** The `sigma_rules.exact_hash` column (SHA-256 of the canonical-rule JSON) is the right tool for *exact* duplicates and is kept for the explicit DUPLICATE short-circuit. It misses everything else by design. It also has degenerate failure modes — atom-less keyword rules collapse to the same canonical form and would hash-collide across unrelated rules. Fixed in `58fb8bf6` (Item 11) by returning `None` for atom-less canonical rules so `sigma_rules.exact_hash` is NULL and SQL `NULL = NULL` is false, so the column cannot host false duplicates.
- **Run the in-app legacy Jaccard scorer.** This is what the pre-`070a0bdb` `SigmaNoveltyService` did when stored atoms were not available. It used a different atom-key shape (`field|op|op_type|value`) and a different polarity rule than the package extractor, so the precomputed path and the live path scored the same pair differently. That was the root cause of the polarity bug (`6gqhWHxjgpWGHGP3`). Retired in `070a0bdb`: both paths now call `sigma_atom_similarity` for extraction and the same `compare_precomputed_atoms` scorer, so precomputed vs on-the-fly is now a pure timing distinction over identical logic.
- **Pairwise broadcast novelty label** (one verdict per *query* rule, applied to every candidate match). The original `SigmaNoveltyService.classify_novelty` computed one label per assessment and broadcast it. It was wrong on article-coverage views, which need a per-candidate verdict. Replaced in `9310f148` by `classify_match_novelty(match)`, which operates on a single match and returns its own label. The pairwise function is retained as a thin caller for backward compatibility.

## Implementation — Phases and Key Work

The work spans roughly two arcs running in parallel. The **engine arc** built the atom-set scoring infrastructure, fixed canonicalization, and extended canonical-class coverage. The **unification arc** retired the duplicate scoring/rendering surfaces that had grown around it. Phase numbering below follows the unification plan (`docs/development/sigma-similarity-unification-plan-2026-06-05.md`) where it applies; engine-arc work is grouped chronologically.

### Phase 0 — Audit and corpus normalization (2026-06-01 → 2026-06-02)

A 12-item audit (`docs/development/sigma-novelty-audit-followup-2026-06-01.md`) drove the first week. The high-impact fixes:

- **`exact_hash` NULL for atom-less rules** (`58fb8bf6`, Item 11). Keyword-only Sigma detections that the deterministic extractor cannot model previously all hashed to the same degenerate canonical form. The column became a magnet for false DUPLICATE matches. Fix: return `None` from `generate_exact_hash` when the canonical rule has zero atoms.
- **List-of-maps modelled correctly** (`bd71d9cc` and follow-up `84dc0e68`, Item 12). Keyword-list selections like `selection: [{CommandLine|contains: alpha}, {CommandLine|contains: beta}]` previously collapsed into one indistinguishable canonical form. Fixed in both extractors so each scalar/dict produces a distinct atom.
- **Filter polarity** (`f2347bf7`, Item 12 follow-up). `_polarity_for_selection_key` no longer assumes a selection named `filter_*` is negative — the polarity comes from the condition AST. The wrong polarity in the legacy extractor was the visible symptom of the broader two-extractor problem.
- **Canonical-class consolidation** (`267bb1eb`, Item C; `2729b2f9` image_load + network_connection; `c78facd6` web.webserver; `74ff09bd` 7 Sysmon + macOS classes; `8a658584` PowerShell × 3; `a2dcb5cb` network.dns + web.proxy + Windows DNS-Client fold). Corpus coverage went from `windows.process_creation` plus a handful of one-offs to ~21 classes.
- **Wildcard ↔ modifier fold in atom identity** (`0688b0ff`, Item 9). `*foo*`-as-eq and `foo`-as-contains now produce the same identity (`process.image||contains|foo`). The fold spec is shared with `canon_atom` (see *Phase 3*) so the engine and the eval miner can never drift.
- **Deterministic candidate ordering** (`86827bd8`, Item 7). Candidate retrieval now `ORDER BY rule_id` before `LIMIT top_k` so the same query returns the same top-K across runs, replicas, and VACUUMs.

The corpus was replayed against the rebuilt extractors twice (`docs/development/queue-similarity-replay-2026-06-01.md`, `…-2026-06-02.md`); the second replay produced 3,746 atom-bearing rules with no regressions.

### Phase 1 — Unified match serialization (`e14a5425`)

Every similarity endpoint had been hand-shaping the raw match dict differently — nesting, rounding, field pruning, key renaming. A fix in one surface did not propagate. `src/services/similarity_serialization.py::serialize_similarity_match` projects every raw match onto one canonical contract:

```
id, rule_id, title, description, logsource, detection, tags, level, status, file_path,
similarity, atom_jaccard, logic_shape_similarity, containment, novelty_label, novelty_score,
similarity_engine, service_penalty, filter_penalty, weighted_before_penalties,
shared_atoms, added_atoms, removed_atoms, filter_differences, atom_details
```

All numeric metrics are rounded to 4 decimal places at one site. Directional containment is lifted out of `atom_details.overlap_ratio_a` to a top-level `containment` field; before the lift, each surface reached for containment from a different place, which is how the same rule could display different containment percentages depending on the page. Five response builders wire through the serializer per commit `e14a5425`: `sigma_ab_test /compare`, `sigma_ab_test /compare-to-repository`, `sigma_similarity_test`, `sigma_queue` (HTTP boundary only — the JSONB storage shape is untouched), and `ai.py /sigma-matches` (the article-coverage panel, preserving its `coverage_status` field).

### Phase 2 — Per-match novelty classifier (`9310f148`, `cfd0498e`, `329816c1`)

`classify_match_novelty(match)` lives in `src/services/sigma_novelty_service.py`. It is the single source of truth for the legacy `(atom_jaccard, logic_shape)` thresholds:

- `exact_hash_match: True` → `DUPLICATE`
- `atom_jaccard > 0.95 AND logic_shape > 0.95` → `DUPLICATE`
- `atom_jaccard > 0.80` → `SIMILAR`
- otherwise → `NOVEL`

`logic_shape_similarity = None` is the early-exit perfect-match signal and is treated as `1.0`. The function operates on one candidate at a time; callers that classify many candidates get one verdict per candidate, not a broadcast label.

Frontend mirrors live in `src/web/static/js/components/similarity-display.js`:

```
SIMILARITY_THRESHOLDS = {
  legacy:        { duplicateAtomJaccard: 0.95, duplicateLogicShape: 0.95, similarAtomJaccard: 0.80 },
  deterministic: { duplicateSimilarity:  0.75, similarSimilarity:    0.50 },
  display:       { strongMatch: 0.90, moderateMatch: 0.75 },
}
```

The `legacy` row is keyed to `classify_match_novelty`; the `deterministic` row labels matches when the precomputed engine has produced a `similarity` value (it skips Jaccard/logic-shape and uses the weighted similarity directly). The two rows are config buckets, not the engine names — they are accessed by literal property, not by `similarity_engine` value, so the 2026-06-09 engine-label rename (`deterministic` → `precomputed`, `legacy` → `on-the-fly`) deliberately left these property names alone.

The retired pairwise classifier (`SigmaNoveltyService.classify_novelty`) is preserved as a thin wrapper that classifies the top match and returns its label for backward-compat callers.

### Phase 3 — Engine-independent canonicalization and read-only pair miner (`8c7b46b7`, then ongoing)

Two artifacts:

**`scripts/mine_sigma_pair_candidates.py`** is the eval pair miner. It is **read-only** (the Postgres connection is opened with `readonly=True` and `autocommit=True`), it deliberately **does not call the novelty engine to pick pairs**, and it explicitly **does not use `sigma_rules.exact_hash`** to identify duplicates — both for a load-bearing reason documented at the top of the file.

The reason for not using the engine: the engine is what we are testing. If we asked the engine "give me pairs that look similar," the engine would systematically exclude exactly the blind-spot pairs (atoms written with a wildcard on one side and a modifier on the other) we most want to surface for human labeling. The miner uses an engine-independent canonical Jaccard so the pair set is not biased by the engine's current behavior.

The reason for not using `exact_hash`: even after Item 11 made it NULL for atom-less rules, the column had observed degenerate collisions in the live corpus (one hash shared by 84 unrelated rules with different `positive_atoms` — comment in the script). It is poisoned as a dup signal.

The miner blocks rules by shared canon atoms within each canonical class (skipping any atom shared by more than 300 rules, which is the generic-atom cap), computes Jaccard for both the *raw* stored identities and the *canonicalized* identities, and tiers each pair:

- **T1** (`canon_J ≥ 0.80`) — near-duplicate.
- **T2** (`0.50 ≤ canon_J < 0.80`) — moderate.
- **T3** (`canon_J ≥ 0.50 AND gap ≥ 0.30`) — the blind-spot prize: pairs that score high in canonical form but low in raw form, i.e. pairs the engine *misses* because the syntactic variation defeats the raw atom key. T3 takes priority over T1/T2.
- **NEG** (`canon_J < 0.20 AND shared ≥ 1`) — hard negatives: pairs that share an atom but the engine should not call similar.

The output is CSV with `tier`, `canonical_class`, both Jaccards, the gap, both rules' ids/titles/paths, and the shared / A-only / B-only canonical atoms.

**`canon_atom(s)`** is the engine-independent canonicalization function defined inside the miner. It folds a stored identity (`field|operator|modifier_chain|value` or its 3-slot successor) into `field|op|value` form. Folding rules: drop the `|all` token (it controls list semantics, not behavioral identity), pick the first comparison op in the remaining chain (default `eq`), then apply the wildcard fold (`*X*`-as-eq → contains|X; `*X` → endswith|X; `X*` → startswith|X; `*X*` with a non-eq op strips redundant edge wildcards).

`canon_atom` is the **reference spec** that the engine's `atom_identity` reimplements. The two were intentionally split: the miner needs to be independent of the engine so it can grade the engine. The engine's `_fold_wildcards` in `atom_extractor.py` carries a comment pointing at `canon_atom` as the canonical policy spec, and the test `test_examples_5_and_6_collapse_to_same_key` enforces that both produce the same key for the wildcard-vs-modifier pair the engine previously missed. The full canon_atom suite lives in `tests/sigma_atom_similarity/test_canon_atom.py` — 10 test functions, several parametrized (spec examples, wildcard-folding inputs, idempotency cases).

**Coverage caveat** (printed at runtime). The miner only operates on rules with non-empty `positive_atoms` in `canonical_class IN ('windows.process_creation', 'linux.process_creation')`. That was the only segment with backfilled atoms when the miner shipped. After the Phase-0 coverage-chain work, more classes have populated atoms, but the miner still gates on those two for stability — a separate mining pass per class is the eventual plan.

**MCP cap discovery.** During corpus exploration via the read-only `huntable-cti-studio` MCP, queries returning more than 200 rows were silently truncated by the MCP server. Worked around by paginating over `rule_id` ranges; documented inline in the script and in the queue-similarity-replay notes. The miner itself uses a direct psycopg2 connection and is not affected.

### Phase 4 — Shared UI rendering component

Five surfaces previously rendered similarity differently: the queue detail pane (`workflow.html`), the workflow-execution detail (`workflow_executions.html`), the rule preview modal (`sigma_queue.html`), the A/B test page (`sigma_ab_test.html`), and the article coverage panel (`article_detail.html`). Fixes to one did not land in the others; the 2026-06-05 NaN% bug and the workflow-modal "bare Similarity: X%" omission were both visible only on a subset of pages.

Phase 4 collapsed all five onto `src/web/static/js/components/similarity-display.js::renderSimilarityDisplay(data, options)`. The component takes a normalized match dict and renders either the `compact` mode (engine badge + similarity % + score breakdown grid + atom diff) or the `expanded` mode (adds collapsed YAML, surface scores, reason flags, and the full breakdown). Both modes share one normalizer (`normalizeSimilarityData`) that pulls metrics from the canonical contract or from any of the surviving legacy aliases.

`src/web/static/js/components/similar-rule-modal.js` is the unified "Similar Rule Details" modal launched from rule-preview modals. It collapses the two previously-divergent copies in `workflow.html` and `workflow_executions.html` into one definition, renders the behavioral breakdown via `renderSimilarityDisplay({ mode: 'compact', includeExplainability: true })`, escapes all interpolated rule fields, supports both `window.ModalManager` (the newer modal stack) and `pushModal` (the legacy fallback), and handles ESC-to-close.

Atom diff color coding lives in the explainability section of the shared component:

- **Green** (`bg-green-50` / dark `bg-green-900`) — shared atoms (`shared_atoms`).
- **Yellow** (`bg-yellow-50` / dark `bg-yellow-900`) — atoms in the current rule but not in the candidate (`removed_atoms` from the engine's perspective; the UI labels them "Atoms in Rule A").
- **Orange** (`bg-orange-50` / dark `bg-orange-900`) — atoms in the candidate but not in the current rule (`added_atoms` from the engine's perspective; labelled "Atoms in Rule B").
- **Purple** — filter differences (NOT-clause symmetric difference).

Each atom is rendered through `_atom_identity_to_display` (`sigma_novelty_service.py`) which projects the 3-slot identity (`field|modifier_chain|value`) onto `field|op:value` form so the displayed text matches the full-parse explainability format.

The modal stack design intentionally **does not** carry Approve/Reject controls. Those live on the parent rule-preview modal (the queue triage view), because the similarity sub-modal is a *read-only* explanation surface — the analyst opens it to understand *why* a candidate was flagged, then makes the queue decision in the parent view. Keeping the verdict-side controls separate from the explanation-side controls is the same separation behind serializing the match in Phase 1 and classifying it in Phase 2.

Other Phase-4 fixes worth recording: `eeceb925` converged `/compare` onto the precompute atom extractor (it had still been calling the in-app legacy path); `4e7bf2ae` exposed the directional containment ratio separately from the bucketed logic-shape factor; `e79d321a` fixed the test-page NaN% by routing through the shared normalizer; `d943834a` and `329816c1` repaired the YAML marker scanner in the A/B test to be line-anchored and read in text order rather than naive substring; `b85437b5` rebuilt the queue detail pane to read the canonical contract directly instead of an ad-hoc remap layer; `da3fd216` dropped the last embedding vestiges from response payloads.

### Phase 5 — Single-extractor timing collapse and atom 3-slot migration

Two cleanups bundled with Phase 5:

**Atom 3-slot identity migration** (`f7ad0813` for the format, `3626e795` for the corpus rewrite). The stored atom string format dropped from `field|operator|modifier_chain|value` to `field|modifier_chain|value`. The operator is recoverable as `modifier_chain.split("|")[0]` (empty ⟺ eq). This eliminated the "endswith|endswith" duplicated-operator display bug visible in the UI and removed an entire class of containment math errors triggered by `|all` modifiers (the redundant slot had been letting one rule's `|all` form fail to match another rule's non-`|all` form for the same atoms).

**Single-extractor timing collapse** (`070a0bdb`, 2026-06-11). Before this commit, the on-the-fly novelty path used `SigmaNoveltyService.extract_atomic_predicates` — a separately-maintained extractor whose polarity, field-aliasing, and list-handling logic diverged from the package extractor used at precompute time. The two extractors disagreed on which atoms were positive vs negative for the same rule, which produced the filter-polarity bug. The fix makes the on-the-fly path call `extract_atom_fields(rule_data, require_canonical_class=False)` — the same function the precompute path uses, with the strict canonical-class gate relaxed since the on-the-fly path needs to score rules whose telemetry class is not yet modeled. After this, "precomputed" vs "on-the-fly" is purely a timing label over identical extraction logic. The 83 affected unit tests stayed green; the engine-label rename (`55148f64`) updated the labels to reflect the new reality (`deterministic` → `precomputed`, `legacy` → `on-the-fly`).

The engine labels are aliased on read in both Python (`similarity_serialization.alias_engine_label`) and JavaScript (`similarity-display.js::aliasEngineLabel`). Rows persisted in `sigma_rule_queue.similarity_scores` before the rename still carry the old labels; the alias maps them on read rather than running a destructive backfill. Symmetry was added to the aggregate `engine_used` field at `sigma_matching_service.py:648` in `8968e315`.

### Phase 6 — Observability and prompt hygiene (peripheral)

Two related but non-engine commits inside the window:

- **Langfuse trace tagging** (`2afcbc2d`). Sigma generation traces are tagged with `execution_id`, `article_id`, and `model` so a debugging session can pivot from "queue rule X is wrong" to "the LLM call that produced X" in one step.
- **Sigma repair retry count surfaced as a Langfuse score** (`2645761a`). The number of LLM repair attempts (how many times the validator round-tripped the rule back to the LLM) is now a scored metric, surfaced via `score_langfuse_trace()` and `get_active_trace_id()` in `langfuse_client.py`.
- **Sigma generation hygiene** (`2780b467`, Finding B). `sigma_generation.txt` now forbids `service: sysmon` / `service: security` without a paired `EventID`; a pre-enqueue lint flags any rule whose logsource cannot resolve to a canonical class and tags it with `logsource_lint_failures`. Mirrored into the 9 quickstart preset variants (`3ebd0767`) so new installs do not regress.

### Tests

The full test surface is:

- `tests/sigma_atom_similarity/test_canon_atom.py` — 24 cases covering the wildcard fold, regex passthrough, `|all` handling, idempotency, single-segment pass-through, the lossy `|`-in-value edge case, and the load-bearing example-5-vs-example-6 collapse.
- `tests/sigma_atom_similarity/test_similarity_engine.py` — full-result shape, no-shared-atoms returns `J=0` with reason flag, determinism on identical JSON, the vssadmin regression case, and case-mismatch regressions (PascalCase vs snake_case fields produce the same identity; `contains|all` is case-folded; `|cased` preserves case).
- `tests/sigma_atom_similarity/test_canonical_class.py` — registry resolution including the EventCode/EventID alias and the consolidated `registry_*` / `file_*` families.
- `tests/sigma_atom_similarity/test_filter_and_atoms.py` — the filter formula, the "filters never increase similarity" invariant, field-alias resolution across PascalCase / snake_case / lowercase, value case-folding for each case-insensitive operator, regex preserving case, keyword-list selections producing atoms (the Item 12 fix), and the 3-slot identity format invariants.
- `tests/sigma_atom_similarity/test_regression_case_sensitive_atoms.py` and `test_wildcard_fold.py` — targeted regressions.
- `tests/services/test_sigma_atom_precompute.py` — `is_sigma_similarity_available`, dict shape, unknown logsource handling, the `require_canonical_class` contract (strict at index time, relaxed at compare time).
- `tests/services/test_sigma_novelty_service.py` — the full `assess_novelty` flow, the exact-hash short-circuit, the atom-less exact-hash NULL contract (Item 11), keyword-list-of-strings producing one atom per scalar (Item 12), the soft exe-jaccard fallback, and the candidate-retrieval `phase1_path` tagging.
- `tests/services/test_classify_match_novelty.py` — per-match classifier behavior including the None-logic-shape-as-perfect rule.
- `tests/services/test_similarity_serialization.py` — canonical contract, containment lifted from `atom_details`, the engine-label alias (`deterministic` → `precomputed`, `legacy` → `on-the-fly`, new values pass through).
- `tests/services/test_soft_exe_jaccard.py` — the cross-field soft-Jaccard fallback for process-exe fields.
- `tests/playwright/sigma_similarity_unification.spec.ts` — 6 cases covering the 4 UI surfaces (YAML toggle, metrics rendering, modal stacking, A/B canonical contract).

The full unit suite was 3500+ green at Phase 5 close; the API suite was 391 green. Both numbers are corroborated by the in-session `.remember/` notes from the operator and by post-merge Playwright verification.

## Current Limitations and Known Issues

- **Corpus coverage gap.** Only `windows.process_creation` and `linux.process_creation` rules have `positive_atoms` populated in the live corpus per the miner's runtime caveat. The remaining canonical classes are in the registry but their rules largely fall through to the `logsource_key` + top-K=20 fallback path (`SigmaNoveltyService.retrieve_candidates`). Until atoms backfill across classes, the engine's recall on registry/file/network/DNS/PowerShell rules is bounded by what `top_k=20` happens to retrieve.
- **Atom-less rules are unassessable.** Keyword-only SigmaHQ detections (XSS/SSTI/Log4j/path-traversal shapes) that produce no atoms are routed to `needs_review` rather than NOVEL. This is correct behavior — the engine cannot say anything about them — but the pile is growing.
- **`mine_sigma_pair_candidates` only mines process_creation.** The script gates on `canonical_class IN ('windows.process_creation', 'linux.process_creation')`. Extending it to other classes requires only changing the WHERE clause once those classes have backfilled atoms, but no separate per-class mining pass exists yet.
- **T3 blind-spot pairs are surfaced, not auto-fixed.** The miner finds pairs where canon-J ≥ 0.5 and the raw-J → canon-J gap ≥ 0.3 — pairs the engine should match but does not. Each new fold (the wildcard fold of `0688b0ff`, the case-folding of `4b94e175`, the registry-class consolidation) closes one slice. There is no automated regression-on-the-miner — the pairs are exported to CSV for human labeling and become the held-out eval set for future folds.
- **Cross-telemetry scheduled-task remains in separate buckets.** The same scheduled-task behavior can land in `windows.process_creation` (schtasks.exe), `windows.file_event` (\Tasks\ writes), or `windows.registry_event` (TaskCache keys). The engine does not bridge them; rules targeting the same task creation across these sources can produce false-NOVEL. Documented in `canonical_logsource.py` as a known limitation.
- **PowerShell field aliasing across log sources is deliberately not modelled.** ScriptBlockText (EID 4104) vs Payload (EID 4103) vs Data (EID 400) are three distinct telemetry classes. Bridging them is a field-alias decision with false-merge risk and is intentionally deferred.
- **A small residual "semantic" naming pocket exists outside the dedup engine.** Specifically `calculate_semantic_overlap` / `semantic_overlap_ratio` in `src/web/routes/ai.py:2297` (the A/B page value-overlap, not the dedup engine) and the `getScoringModeLabel` else-branch in `similarity-display.js` returning "LLM / Embedding" (now likely dead since the LLM/embedding scorer was removed). Tracked as Todoist task `6gqxxh7q8Jw285qV` (p4); not load-bearing.
- **`SigmaNoveltyService.compute_atom_jaccard` carries a soft-exe-jaccard fallback** (`_soft_exe_jaccard_from_atom_strings`) that grants partial credit when two rules reference the same executable value across different process-exe fields (e.g. `process.image` vs `process.command_line`). It is dampened by 0.5 and is intentionally weaker than exact-atom matching, but it is a heuristic — the engineering choice is "0.5 is better than 0.0 when the analyst can see the cross-field match", but it is not a structural property of the algorithm.

## Novelty Claim

Medium. The atom-Jaccard-times-containment-minus-filter formula is not a new algorithm — Jaccard is decades old, containment as a directional asymmetry is well-known in set similarity, and combining them as `J × B` is a reasonable engineering choice that exploits the fact that Sigma rules decompose cleanly to sets. The novelty is in applying this disciplined deterministic shape to the Sigma rule-novelty problem in a way that respects telemetry-class boundaries and produces analyst-readable explanations, instead of reaching for the embedding hammer that the open-source landscape (RuleGenie, SigmAIQ, and most analyst-facing tooling) defaults to. The miner's T3 blind-spot tier — selecting the pairs the *current engine* gets wrong with an *engine-independent* canonical Jaccard so the engine can be regressed against its own blind spots — is the part most worth pointing at.

This is not a research contribution. It is a deliberate engineering bet that structure beats fuzziness for this specific problem.

## Consequences

The subsystem makes possible:

- **Determinism.** The same rule pair produces the same `(jaccard, containment_factor, filter_penalty, similarity)` every run, across replicas, after VACUUM, after a year. No LLM-driven scoring jitter. No "the verdict changed because we reindexed."
- **Explainability.** Every similarity match comes with `shared_atoms`, `added_atoms`, `removed_atoms`, and `filter_differences` rendered inline. The analyst can see *why* before approving or rejecting. No black-box similarity scores.
- **One scoring surface from five entrypoints.** The workflow LangGraph node (`similarity_search` in `agentic_workflow.py`), `/sigma-queue` triage, `/sigma-ab-test/compare`, the article coverage panel, and the workflow execution detail page all read the same canonical contract from the same serializer. A fix lands once.
- **One rendering surface.** All four UI surfaces (modal + queue pane + A/B page + test page) go through `renderSimilarityDisplay`. UI bug fixes propagate.
- **Held-out eval pairs.** The miner CSV is reusable as a regression suite. T3 pairs that pass after a fold change are evidence the engine improved; T3 pairs that still fail are the next fold to design.
- **A path to extend coverage.** Adding a canonical class is now a registry-tuple entry plus an optional field-alias addition and a recompute pass. Adding atoms for a new class is a precompute backfill.

The subsystem constrains:

- **The engine cannot score rules with no atoms.** This is correct behavior, but it pushes a growing pile to `needs_review`. Decisions on keyword-rule treatment will become more pressing as more such rules accumulate.
- **The engine cannot bridge telemetry classes.** A scheduled-task creation observable via `process_creation`, `file_event`, and `registry_event` will not be compared across those buckets. Bridging requires per-pair field-alias work and accepting some false-merge risk.
- **The two scoring labels (`precomputed` vs `on-the-fly`) survive as a timing distinction.** They are now identical logic at different times, but they are still surfaced. Future cleanups could collapse the label entirely if the precompute backfill ever reaches 100% of the corpus.

Future work the subsystem unlocks:

- Per-class mining passes once `positive_atoms` backfills across the registry. Each pass produces a per-class T3 set and a per-class fold-fix queue.
- Field-alias decisions (PowerShell-across-sources, scheduled-task-across-sources, ProcessHashes ↔ Hashes) become bounded changes with measurable T3 evidence rather than open-ended discussions.
- Customer-corpus dedup. The same engine, pointed at a customer's own Sigma repo (already indexed via the daily Celery beat task added in `26565e24`), surfaces rules the customer already has so generated rules do not re-pave existing ground.

## Files and Entry Points

### `sigma_atom_similarity/` (Python package, COPY'd into Docker images at build time)

- `sigma_similarity/similarity_engine.py` — `compare_rules(rule_a, rule_b) -> SimilarityResult`. The public entry point. Orchestrates canonical-class resolution, normalization, DNF, atom extraction, surface, containment, filter, and final similarity.
- `sigma_similarity/atom_extractor.py` — `atom_identity(node)`, `extract_positive_atoms(dnf)`, `extract_negative_atoms(dnf)`, `_fold_wildcards`, `FIELD_ALIAS_MAP`.
- `sigma_similarity/canonical_logsource.py` — `CANONICAL_CLASS_REGISTRY`, `resolve_canonical_class(rule)`. Raises `UnknownTelemetryClassError` if no class matches.
- `sigma_similarity/containment_estimator.py` — `compute_containment` (Equivalent / Subset / Superset / Else buckets).
- `sigma_similarity/filter_analyzer.py` — `filter_penalty` (capped at 0.5).
- `sigma_similarity/surface_estimator.py` — `surface_score_from_dnf` (DNF branch count).
- `sigma_similarity/detection_normalizer.py` — recursive-descent condition parser, selection resolver, keyword-scalar synthesizer.
- `sigma_similarity/ast_builder.py` — `build_ast`, `_parse_field_spec` (`field|modifier|modifier` → `(field, operator, modifier_chain)`).
- `sigma_similarity/dnf_normalizer.py` — `ast_to_dnf` with deterministic expansion limit.
- `sigma_similarity/models.py` — `SimilarityResult` dataclass.
- `sigma_similarity/errors.py` — `UnknownTelemetryClassError`, `UnsupportedSigmaFeatureError`, `DeterministicExpansionLimitError`.

### `src/services/`

- `sigma_atom_precompute.py` — `extract_atom_fields(rule_data, *, require_canonical_class)`, `precompute_atom_fields(rule_data)`. The boundary between the standalone package and the app. Strict mode at index time; relaxed mode at compare time.
- `sigma_novelty_service.py` — `SigmaNoveltyService.assess_novelty`, `compare_precomputed_atoms`, `classify_match_novelty`, `NoveltyLabel`, `_normalize_atom_identity`, `_atom_identity_to_display`, `generate_exact_hash`, `retrieve_candidates` (with `phase1_path` tagging: `exact_hash` / `canonical_class` / `logsource_fallback`).
- `sigma_matching_service.py` — `SigmaMatchingService.assess_rule_novelty`. Shared entry called by the workflow LangGraph node and by UI routes. Pre-fetches candidate rows in one SELECT to avoid N+1. Applies the conditional `logsource_key` safety gate scoped to the fallback path.
- `similarity_serialization.py` — `serialize_similarity_match(match)`, `alias_engine_label(value)`. Phase 1 canonical contract. Single rounding policy. Read-time engine-label alias.

### `src/web/routes/`

- `sigma_ab_test.py` — `POST /api/sigma-ab-test/compare`, `POST /api/sigma-ab-test/compare-to-repository`. Routes that drive the A/B test page. Both pass through `serialize_similarity_match`.
- `sigma_queue.py` — queue list, queue detail, queue similarity. All paths use `serialize_similarity_match`.
- `ai.py` — article coverage panel (`calculate_semantic_overlap` is a separate value-overlap calculation, not the dedup engine; see Limitations).

### `src/web/static/js/components/`

- `similarity-display.js` — `renderSimilarityDisplay(data, options)`, `normalizeSimilarityData(match)`, `calculateNoveltyLabel`, `aliasEngineLabel`, `SIMILARITY_THRESHOLDS`, `METRIC_LABELS`.
- `similar-rule-modal.js` — `showSimilarRuleDetails`, `closeSimilarRuleModal`. Renders the breakdown through the shared component.

### `src/cli/`

- `sigma_commands.py` — `recompute-atoms` CLI (renamed from `recompute-semantics` in `ed83cf19`). Repopulates `canonical_class`, `positive_atoms`, `negative_atoms`, `surface_score` across the corpus.

### `scripts/`

- `mine_sigma_pair_candidates.py` — read-only eval pair miner. Defines `canon_atom(s)` as the engine-independent reference spec. CSV output. T1 / T2 / T3 / NEG tiers.
- `migrate_sigma_atom_op_slot.py` — one-shot migration that rewrote stored atom identities from 4-slot to 3-slot.

### `src/database/models.py` — `SigmaRuleTable` columns read or written by this subsystem

- `exact_hash` (`String(64)`, indexed, nullable) — SHA-256 of canonical JSON; NULL for atom-less rules.
- `logsource_key` (`String(100)`, indexed, nullable) — `product|category` fallback retrieval key.
- `canonical_class` (`String(100)`, indexed, nullable) — resolved telemetry class.
- `positive_atoms` (`JSONB`, nullable) — sorted list of 3-slot identity strings.
- `negative_atoms` (`JSONB`, nullable) — sorted list of 3-slot identity strings for NOT clauses.
- `surface_score` (`Integer`, nullable) — DNF branch count.

`sigma_rule_queue.similarity_scores` (JSONB) — persists the per-match output of the engine for queue rows. Engine-label aliasing is read-time.

### Tests

- `tests/sigma_atom_similarity/` — package-level tests, no Huntable imports.
- `tests/services/test_sigma_atom_precompute.py`, `test_sigma_novelty_service.py`, `test_sigma_matching_service.py`, `test_classify_match_novelty.py`, `test_similarity_serialization.py`, `test_soft_exe_jaccard.py`, `test_sigma_similarity_deterministic.py` — service-layer tests.
- `tests/playwright/sigma_similarity_unification.spec.ts` — UI verification across 4 surfaces.

### Reference docs

- `docs/development/sigma-similarity-unification-plan-2026-06-05.md` — phase plan that drove Phases 1–5.
- `docs/development/sigma-novelty-audit-followup-2026-06-01.md` — the 12-item audit that drove Phase 0.
- `docs/development/queue-similarity-replay-2026-06-01.md`, `…-2026-06-02.md` — corpus-replay diagnostics.
- `docs/sigmasimRefactor.md` — a retrospective Slack-summary writeup of the same period (working note, parallel to this ADR).
