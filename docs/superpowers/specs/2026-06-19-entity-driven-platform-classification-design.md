# Entity-Driven Platform Classification — Design Spec

- Date: 2026-06-19
- Status: **Phases A, B & C implemented** (entity-KB gate is the primary decider; ATT&CK
  technique citations reinforce it; LLM adjudicates only the low-confidence/Unknown tail).
  Phase D proposed.
- Architecture: **hybrid confirmed by operator 2026-06-19** — deterministic KB gate
  runs first; the LLM is invoked *only* for the low-confidence / Unknown tail (never
  LLM-always). The KB doubles as the cost gate that decides when to spend an LLM call.
- Branch: europa-dev
- Related: [`2026-06-17-platform-telemetry-expansion-design.md`](2026-06-17-platform-telemetry-expansion-design.md)
  (phase one), [`2026-06-19-platform-telemetry-followups.md`](2026-06-19-platform-telemetry-followups.md)

---

## 1. Problem

Phase-one Platform Telemetry Expansion shipped capability-based routing, per-platform
Sigma grouping, and observable-level platform metadata. But the **article-level platform
classifier** (step 0, `OSDetectionService`) cannot reliably identify non-Windows
articles, which blocks the Linux pilot that phase-one's §10 promotion criteria depend on.

### 1.1 Measured failure (2026-06-19)

`OSDetectionService.detect_os` was run (local, no LLM, free) on four clearly-Linux
articles — 4441 (Linux intrusion, MS Defender), 3633 (AdaptixC2 operator toolkit),
1542 (Linux PHP webshells, MS Defender), 4417 (UNC2891, Linux/Unix/Solaris):

| Article | CTI-BERT | SEC-BERT | CTI-BERT on junk-filtered |
|---|---|---|---|
| 4441 | `Other` → unknown | `Windows` 0.86 "high" | `Windows` 0.57 / Linux 0.53 |
| 3633 | `Windows` (keyword) | `Windows` (keyword) | `Windows` (keyword) |
| 1542 | `Windows` 0.54 | `Other` 0.84 | `Windows` 0.56 / Linux 0.51 |
| 4417 | `Unknown` → cross_platform | `Windows` 0.82 | empty after filter → skipped |

**0/4 classified Linux**, with either encoder, raw or filtered.

### 1.2 Root causes

1. **Windows-only keyword fast path.** `_check_windows_keywords` returns `Windows`
   immediately on ≥3 Windows keyword hits, before embeddings run. There is no Linux (or
   any other) keyword set, and it does not yield when Linux signal is also present
   (3633 misrouted this way).
2. **Embedding similarity is non-discriminative.** Cosine of a document embedding vs.
   short OS-indicator-text profiles collapses all classes together (CTI-BERT ~0.45–0.55,
   SEC-BERT ~0.78–0.86); the `Other`/`multiple` tie-break pseudo-classes frequently win.
   SEC-BERT additionally reports `confidence="high"` on ~0.04 margins (margin-blind).
3. **Truncation on raw content.** Detection runs at step 0 on raw `article.content`
   *before* the junk filter (step 1). BERT's 512-token cap means it embeds only the
   article head (intro/boilerplate), not the telemetry body. Filtering improves class
   separation (4441: Linux 0.47→0.53, `Other` 0.51→0.46) but does **not** flip any
   verdict, and the junk filter empties ~86% of articles (4417 → 0 chars).

Conclusion: the embedding-similarity method is the wrong tool for OS/platform
classification. Swapping encoders or pre-filtering content does not fix it.

---

## 2. Goal

Replace embedding-based article classification with an **explainable, entity-driven,
multi-label classifier** that:

- reliably identifies the platform(s) an article concerns (Linux first-class, not just
  Windows-or-not);
- produces evidence for every label (analyst trust);
- keeps cost near-zero for the common case and uses an LLM only as a low-confidence
  adjudicator;
- reuses the entity/keyword/scoring machinery the codebase already has;
- extends cleanly from a single Platform dimension to Domains and Products later.

### Non-goals

- Rebuilding observable-level extraction (it already works and is authoritative per
  phase-one §3).
- Supervised ML training or a fine-tuned classifier.
- Shipping the full three-dimension taxonomy in the first increment (see §6 phasing).

---

## 3. Architecture

```text
Threat article (telemetry-dense content; see §5.4)
    ↓
Cheap entity extraction      (regex / KB match — NOT the LLM ExtractAgent)
    ↓
Normalization                (alias → canonical entity)
    ↓
Knowledge-base mapping       (entity → platform/domain/product, with weight)
    ↓
Label scoring                (weighted evidence per label → confidence)
    ↓
LLM adjudication             (ONLY when low-confidence / conflicting / sparse)
    ↓
Final multi-label classification (+ evidence)
```

Two distinct entity layers must not be conflated:

- **Classification entity pass (new):** cheap, deterministic regex/KB matching over the
  article, used to *route*. Runs at step 0. No LLM.
- **Huntable extraction (existing):** the LLM `ExtractAgent` sub-agents that pull
  structured observables for Sigma. Runs at step 3. Unchanged.

The classifier's output drives capability routing (phase-one §3) and is a *hint*;
observable-level platform metadata remains authoritative for rule-generation eligibility.

---

## 4. Taxonomy (three independent dimensions)

A single "Windows/Linux/Network" bucket is replaced by three orthogonal label sets:

- **Platforms:** Windows, Linux, macOS, Android, iOS, Network Device, Container,
  Cloud Workload.
- **Domains:** Identity, Cloud, Network, Endpoint, Email, OT/ICS, SaaS.
- **Products:** Active Directory, Entra ID, Okta, Exchange, Cisco ASA, PAN-OS,
  Kubernetes, VMware ESXi, … (open-ended).

Output shape:

```json
{
  "platforms": [{"label": "Linux", "confidence": 0.94, "evidence": ["systemd", "/etc/cron.d", "chmod +x /tmp/x"]}],
  "domains":   [{"label": "Endpoint", "confidence": 0.80, "evidence": ["..."]}],
  "products":  [{"label": "Confluence", "confidence": 0.71, "evidence": ["CVE-2026-…"]}],
  "method": "kb_scoring",          // or kb_scoring+llm_adjudication
  "adjudicated": false
}
```

Phase-one constraint honored: the **Windows-specific artifact taxonomy is not renamed**
(spec §4 of phase one). This classifier sits *above* the extractors; it does not
generalize `registry_artifacts`/`windows_services`/`scheduled_tasks`.

---

## 5. Knowledge base & scoring

### 5.1 Lean on externally-maintained ontologies (the maintenance answer)

The hard problem is taxonomy *maintenance*, so import it where possible instead of
hand-rolling:

- **MITRE ATT&CK** technique → `platforms` tags (techniques are maintained by MITRE).
  Requires adding technique extraction (none exists today — 0 `T1xxx` IDs in prompts).
- **LOLBAS / GTFOBins** binary → OS (Windows / Linux).
- **NVD CPE** CVE → product/vendor.

Hand-maintained KB only fills gaps these feeds do not cover.

### 5.2 Reuse existing assets

- `src/utils/content.py::HUNT_SCORING_KEYWORDS` + its scorer is already a
  keyword-match-and-score engine — reuse the *pattern* with a platform-oriented KB.
- `os_detection_service.py::WINDOWS_OS_KEYWORDS`, `OS_INDICATOR_TEXTS` (Win/Linux/macOS),
  and the cmdline/proctree attention anchors (LOLBAS) seed the Windows + macOS sides.
- `agentic_workflow.py`: `AGENT_PLATFORM_CAPABILITIES`, `WINDOWS_ONLY_OBSERVABLE_TYPES`,
  `_logsource_hint_for_observable`, `_normalize_platform_value`, `_infer_observable_platform`
  already encode entity→platform/telemetry logic at the observable level — the classifier
  should share this vocabulary.

The Linux/network/cloud entity coverage is the genuine net-new KB work.

### 5.3 Scoring & confidence

- Each matched entity contributes a weighted vote to its label(s).
- Confidence is derived from **evidence count and margin between top labels** — never a
  flat similarity score. A small margin = low confidence (the SEC-BERT "high on 0.04"
  bug must not recur).
- Multi-label by design: when Windows and Linux both score highly (mixed article), emit
  both rather than forcing a single bucket.

### 5.4 Content fed to the classifier

Run on telemetry-dense content (junk-filtered or a relevant excerpt) with a **raw
fallback** when the filter empties the article (~86% case). Regex/KB matching is robust
to length, so truncation is not a concern for the KB pass; content choice mainly helps
the optional LLM step.

---

## 6. LLM adjudication

Invoke the LLM (gpt-4o-mini, the configured provider) **only** when the KB pass is:
low-confidence, sparse (few entities), multi-domain, or has conflicting signals.

Prompt returns labels + confidence + supporting evidence across the three dimensions.
This keeps the easy ~80% free and reserves spend for the hard cases. Today's OS detector
uses no LLM; this is an additive, bounded cost.

---

## 7. Integration & migration

- **Retire** the CTI-BERT/SEC-BERT embedding path in `OSDetectionService` as the
  decider (both proven non-discriminative). This removes a model dependency. Keep, at
  most, as a last-resort weak tiebreak — or delete.
- **Replace** the Windows-only keyword fast-path with symmetric KB scoring across
  platforms.
- The classifier emits `platforms_detected` (already a list channel in `WorkflowState`)
  plus the richer multi-label record stored on the execution for UI/trace.
- Phase-one routing, grouping, and observable metadata are unchanged.

### Phasing (incremental; each phase ships independently)

- **Phase A — Platform-KB scoring (unblocks the Linux pilot, $0 to validate). ✅ DONE 2026-06-19.**
  Win/Linux/macOS entity+keyword KB → scored multi-label `platforms_detected`; embedding
  decider retired. Shipped: `config/platform_classification_kb.yaml`,
  `src/services/platform_classifier.py` (margin-based confidence, evidence floor),
  wired into `OSDetectionService.detect_os` as the primary step. Tests:
  `tests/services/test_platform_classifier.py` (12). Probe result on the candidates:
  4441→Linux(high), 4417→Linux(high), 3633→Windows(high, Windows-targeting C2 toolkit),
  1542→Unknown(low, web-layer article, no host signal) — 0/4→2/4 Linux, **no false
  Windows**. The Windows keyword check remains a deterministic safety net for thin
  evidence; the BERT classifier/similarity methods are dormant (delete in Phase D).
- **Phase B — LLM adjudication on the low-confidence/Unknown tail. ✅ DONE 2026-06-19.**
  Shipped `src/services/platform_adjudicator.py` (prompt builder + robust JSON parser +
  `adjudicate_platforms(content, llm_call=...)` with injected LLM call; any failure →
  Unknown). Wired into `os_detection_node` via `_maybe_adjudicate_platform` — fires only
  when the KB gate returns `confidence=="low"`, uses the configured PlatformAdjudicator
  model (falls back to ExtractAgent/RankAgent), and never raises. Tests:
  `tests/services/test_platform_adjudicator.py` (11). Live result: 1542 (KB→Unknown) →
  LLM → Linux(high) with evidence; 4441 stays KB-confident with **no LLM call**. The KB
  is the cost gate — the LLM fires only on the tail it can't resolve.
- **Phase C — ATT&CK technique→platform signal. ✅ DONE 2026-06-19.** Shipped
  `src/services/attack_platform_signal.py` (extract `T1234[.001]` IDs → platform votes),
  `config/attack_technique_platforms.json` (curated discriminative-sub-technique seed),
  and `scripts/build_attack_platform_map.py` (regenerates the full map from MITRE's
  `x_mitre_platforms` — the "import maintained taxonomy" mechanism; needs network).
  Integrated into the KB gate as a **reinforce-only** signal: ATT&CK votes are added only
  to platforms the entity KB already evidences (`score>0`), at supplement weights
  (single=2, multi=1, below the floor). Rationale (live-validated on article 1542): a
  KB-blank article citing only Unix techniques would otherwise be forced to
  `multiple(linux,macos)`, which degrades observable platform inference to `unknown` and
  *suppresses* Linux Sigma — so KB-blank articles defer to the LLM for precise narrowing.
  Tests: `tests/services/test_attack_platform_signal.py` (8) + ATT&CK integration cases
  in `test_platform_classifier.py`.
- **Phase D — Domains + Products dimensions**; delete the embedding path entirely. This
  is the taxonomy generalization phase-one §4 deliberately deferred.
  - **Embedding OS *detection* removed 2026-06-19** (`_detect_with_classifier`,
    `_detect_with_similarity`, `_load_classifier`, `_precompute_os_embeddings`,
    `OS_INDICATORS`; ~143 lines). The embedding *infra* (`_get_embedding`, `_load_model`,
    `train_classifier`, CTI-BERT) is **retained** — still shared by
    `huntable_windows_service` and the OS-classifier training script
    (`scripts/train_os_detection_*`). Model loading is lazy and `detect_os` no longer
    triggers it (the earlier "loads in __init__" concern was moot).
  - Follow-up: the OS-classifier training pipeline now trains a classifier nothing reads
    (KB superseded it); retire it (and then the shared embedding infra) once
    `huntable_windows_service`'s embedding dependency is resolved.
  - Domains + Products dimensions: still proposed.

---

## 8. Acceptance / validation

- **Phase A is proven at $0** by re-running the existing local probe
  (`/tmp/os_probe*.py`, `docker exec -i cti_web python - < …`) on 4441 / 1542 / 4417:
  each must classify Linux (4441/1542/4417) and not regress Windows articles.
- Offline unit tests for the KB scorer: known entity sets → expected labels + evidence;
  margin→confidence mapping; multi-label on mixed input; empty/sparse → low confidence.
- Only after the classifier routes Linux correctly does the paid LLM pilot become
  meaningful (it would otherwise test Windows/unknown routing and waste spend).

---

## 9. Open questions / operator decisions

1. **Platform set for Phase A.** ✅ DECIDED 2026-06-19: **Windows + Linux + macOS**.
   Network Device / Container / Cloud Workload deferred to Phase D. macOS stays
   display-only (no Sigma) per phase one.
2. **Embedding path: retire or keep as weak tiebreak?** ✅ DECIDED: retired as decider
   in Phase A (methods left dormant); delete in Phase D.
3. **ATT&CK extraction sequencing.** Build technique extraction in Phase C, or pull it
   forward because it doubles as a Sigma-tagging improvement?
4. **Multi-label routing semantics.** When an article is multi-platform, do we run all
   capable extractors (current behavior) — confirm no change needed.
5. **KB location & format.** ✅ DECIDED (Phase A): single YAML at
   `config/platform_classification_kb.yaml` (entity → {match, platforms, weight}).
   Domains/Products columns added in Phase D.

---

## 10. Out of scope

- Knowledge-graph relationship modeling (entity↔entity edges) — future.
- Retraining or fine-tuning any model.
- Changing observable-level extraction or the Windows artifact taxonomy.
- Backfilling historical executions (consistent with phase-one §8).
