# Unified Keyword Registry with Platform-Tagged Scoring — Design Spec

- Date: 2026-06-20
- Status: **Phases 1–3 SHIPPED + §9 vocabulary SHIPPED (2026-06-21).** The faceted registry
  (`config/keyword_registry.yaml`) is the single source of truth; `HUNT_SCORING_KEYWORDS` is a
  byte-equal-parity-tested derived projection; `project_platform` reuses `PlatformClassifier`
  over the registry's platform entries (subsuming `platform_classification_kb.yaml`). Phase 2:
  `os_classification` is computed at scoring time and stored in `article_metadata` at every
  hunt-score persistence site (ingest/scrape/pdf/reprocess/rescore), go-forward. Phase 3:
  `os_detection_node` consumes that precomputed verdict (via `detect_os(precomputed=...)`) instead
  of re-scanning; the LLM-adjudication tail + Windows safety net + ATT&CK reinforcement are
  unchanged; legacy articles (0/5321 currently carry the verdict — go-forward) fall back to a fresh
  scan. **Carrier drift-fix SHIPPED (§9.5):** 7 platform-discriminative §9 carriers now feed
  `project_platform`. **G4 cleanup SHIPPED (§14):** `platform_classification_kb.yaml` deleted,
  `classify_platforms`/`DEFAULT_KB_PATH` retired, and the `detect_os` fallback repointed to
  `project_platform` — the registry is now the **sole** platform vocabulary. **Phase 4 (engine
  dedup) = WON'T-DO** (the scans don't share a matcher; parity-breaking for marginal gain on a
  low-traffic axis — see §13). **The spec is complete** (Phase 4 deliberately not built).
- Branch: europa-dev
- Operator directives shaping scope (2026-06-20):
  1. *"Every keyword (existing and future) gets a metadata value indicating what platform
     they are evidence for."* → the core of this spec: one keyword registry, each entry
     platform-tagged; OS classification is a projection of keyword matches already collected
     during scoring.
  2. *"The minimum score is still blocking."* → this spec does **not** weaken, bypass, or
     lower any eligibility gate (`min_hunt_score`, `junk_filter_threshold`, `ranking_threshold`).
     OS classification is additive metadata; gate semantics are unchanged.
  3. Junk filter (corrected per docs review): it is a **chunk-level RandomForest content
     reducer** (drops non-huntable chunks pre-LLM; terminates only when none survive), **not** a
     keyword-driven or per-platform article gate. Its only keyword tie is the 92 shared perfect
     discriminators. Out of scope to change; trivially parity-safe under platform tagging.
  4. **Operator decision 2026-06-21: non-Windows detections matter a lot** (answers the §12
     product question). Promotes the platform-complete-huntability work from §9-future to the
     priority payoff and reorders the roadmap (Phase 1 registry = substrate; §9 vocabulary =
     the high-leverage step). The gate *threshold* still does not move (N1 stands) — only the
     vocabulary is made platform-fair.
- Related: [`2026-06-19-entity-driven-platform-classification-design.md`](2026-06-19-entity-driven-platform-classification-design.md)
  (the platform classifier this spec subsumes the *scan* of),
  [`2026-06-17-platform-telemetry-expansion-design.md`](2026-06-17-platform-telemetry-expansion-design.md)

---

## 1. Problem

The codebase scans article content for weighted keyword/regex hits in **two independent
places that share no source of truth**:

1. **Huntability axis** — `ThreatHuntingScorer.score_threat_hunting_content`
   (`src/utils/content.py`) scans against `HUNT_SCORING_KEYWORDS` (perfect / good / lolbas /
   intelligence / negative) and emits the article-level `threat_hunting_score` + matched-keyword
   lists, **at ingest, on full article content** (`processor.py:321`, `scrape.py:517`).

2. **Platform axis** — `PlatformClassifier` (`src/services/platform_classifier.py`) runs a
   **separate** content scan against `config/platform_classification_kb.yaml` inside the
   workflow (`os_detection_node`), post-trigger, to decide the OS.

So the same expensive operation (compile keyword → scan content → weight → aggregate) is
implemented twice over two disjoint vocabularies, and the two vocabularies can drift even
though a single token (`osascript`) is legitimately *both* a huntable LOLBin and a macOS
indicator. The platform scan is also redundant: by the time `os_detection_node` runs, the
content has already been scanned once for scoring.

**The junk filter is a different thing (not in this overlap).** `ContentFilter`
(`src/utils/content_filter.py`) is a **chunk-level RandomForest content *reducer*** (20
structural v3 features: `cmdline_artifact_count`, `process_lineage_count`, `has_code_blocks`,
densities, negative detectors) that drops non-huntable *chunks* before the LLM and terminates
the run only when *zero* chunks survive. Its **only** keyword coupling is the **92 perfect
discriminators**, *shared* with the hunt scorer as a protective override (a chunk hitting one is
auto-kept). It is **not** keyword-driven article gating, and platform tags never touch its
RandomForest — so it is out of scope here and trivially parity-safe (§7). See
`docs/features/content-filtering.md`, `docs/architecture/scoring.md`.

### 1.1 What this spec is NOT

Per operator directive (2), this is **not** a gate change. The fact that Windows-biased
huntability scoring keeps non-Windows articles below `min_hunt_score` is a *separate*
concern (see §9 Future). Here we only make OS classification fall out of the scan that
already happens, from a single platform-tagged keyword source of truth.

---

## 2. Goals / Non-Goals

### Goals
- **G1.** One keyword registry is the source of truth; every entry carries a platform-evidence
  tag (`windows` / `linux` / `macos`, multi-valued, or platform-agnostic).
- **G2.** OS classification is computed from the platform tags of keywords matched during the
  existing scoring scan — no second content scan for the deterministic platform verdict.
- **G3.** Subsume `platform_classification_kb.yaml`'s vocabulary into the registry so platform
  knowledge has exactly one home.
- **G4.** `os_detection_node` consumes the precomputed deterministic OS verdict; LLM
  adjudication for the low-confidence/Unknown tail and ATT&CK reinforcement stay where they are.
- **G5.** **Zero behavior change** to `threat_hunting_score`, the junk filter, and content
  filtering (parity gate — §7).

### Non-Goals
- **N1.** No change to any eligibility gate (`min_hunt_score`, `junk_filter_threshold`,
  `ranking_threshold`, `auto_trigger_hunt_score_threshold`).
- **N2.** No backlog rescue / mass re-processing / auto-trigger of newly-classified articles.
- **N3.** No retraining of the junk-filter ML model.
- **N4.** No change to the Domains/Products dimensions (separate axes; natural future extension).
- **N5.** No removal of the embedding stack (already deferred in the prior spec).

---

## 3. Current state (verified 2026-06-20)

| Component | File | Role | Keyword source |
|---|---|---|---|
| `ThreatHuntingScorer` | `src/utils/content.py:1202` | hunt score (geometric, capped per tier) | `HUNT_SCORING_KEYWORDS` (dict, ~661–1188) |
| `ContentFilter` (junk filter) | `src/utils/content_filter.py` | **chunk-level** RandomForest reducer (20 structural v3 features); drops non-huntable chunks, terminates only when none survive (`no_huntable_content`) | ML model `content_filter.pkl` + **92 shared perfect discriminators** (protective override) + pattern sets — *not* the full keyword set |
| `keyword_resolution` | `src/utils/keyword_resolution.py` | display/highlight layer | per-article matched-keyword metadata |
| `PlatformClassifier` | `src/services/platform_classifier.py` | OS verdict (argmax + margin + evidence floor) | `config/platform_classification_kb.yaml` |
| `attack_platform_signal` | `src/services/attack_platform_signal.py` | ATT&CK technique → platform reinforcement | `config/attack_technique_platforms.json` |

Gates (defaults): `min_hunt_score` 97.0, `junk_filter_threshold` 0.8, `ranking_threshold` 6.0.
Hunt score is computed **at ingest**; OS detection runs **inside the workflow**, post-gate.

---

## 4. Design

### 4.1 The registry: one entry, multiple facets

A single keyword registry replaces the disjoint vocabularies. Each entry carries an optional
**huntability** facet and an optional **platform** facet — a keyword may have one or both:

```yaml
# config/keyword_registry.yaml  (illustrative)
keywords:
  - match: "osascript"
    huntability: lolbas          # contributes to hunt score / junk filter as today
    platforms: [macos]           # contributes to OS classification
  - match: "comsvcs.dll"
    huntability: perfect
    platforms: [windows]
  - match: "/etc/cron"
    platforms: [linux]           # platform-only marker; huntability omitted (0 hunt points)
  - match: "lsass"
    huntability: perfect
    platforms: [windows]
  - match: "scheduled task"
    huntability: good
    # no platforms → platform-agnostic; contributes nothing to OS
```

- **huntability** ∈ {perfect, good, lolbas, intelligence, negative} — unchanged semantics
  and weights. Omitted ⇒ the keyword is a *platform marker only* and contributes **zero** to
  the hunt score and junk filter (preserves G5/parity).
- **platforms** ⊆ {windows, linux, macos}, multi-valued. Omitted ⇒ platform-agnostic.
- Per-platform weight (the platform KB's strong/medium/weak = 3/2/1) is derived from a
  default-by-huntability-tier mapping, overridable per entry with an explicit `platform_weight`.
  This preserves the existing platform KB's evidence-floor calibration.

**Source-of-truth decision (locked 2026-06-20 — D-A):** keep `HUNT_SCORING_KEYWORDS` values
*byte-identical* by **generating** them from the registry at load time (or asserting equality
in a test), rather than hand-rewriting the load-bearing dict. The registry is authoritative;
`HUNT_SCORING_KEYWORDS` becomes a derived projection. This is the lowest-risk migration path
and is what the parity gate (§7) enforces.

### 4.2 Scan once, decide N

A shared `WeightedKeywordScan` does the expensive part once:

```
matches = scan(content, registry)        # [(keyword, span, huntability?, platforms?, weight)]
hunt    = project_huntability(matches)   # existing geometric scorer — identical output
os      = project_platform(matches)      # existing argmax + margin + evidence floor
```

- `project_huntability` reproduces `ThreatHuntingScorer`'s current math exactly (geometric,
  per-tier caps, negative penalty). Output dict identical to today.
- `project_platform` reproduces `PlatformClassifier`'s current decision (weighted sum per
  platform, `HIGH_MARGIN`, `MIN_EVIDENCE_WEIGHT`) over the platform-tagged matches.
- The two deciders stay **separate functions** — we share the *scan*, not the *math*
  (consistent with the earlier "don't merge ThreatHuntingScorer" position).

### 4.3 Where OS is computed and stored

- At **ingest scoring time** (`processor.py`, `scrape.py`, `rescore` CLI — wherever
  `score_threat_hunting_content` already runs), also run `project_platform` and write
  `article_metadata["os_classification"] = {os, confidence, evidence, method: "kb_scoring"}`
  alongside `threat_hunting_score`. One pass, two outputs.
- `os_detection_node` is simplified: **read** `article_metadata["os_classification"]` instead
  of re-scanning. The existing low-confidence/Unknown → **LLM adjudication** and the
  **ATT&CK reinforcement** paths are unchanged (they run on the precomputed deterministic
  verdict). `skip_os_detection` (eval path) is unchanged.

### 4.4 What stays separate
- ATT&CK→platform reinforcement (`attack_platform_signal`) — different input (technique IDs,
  not content keywords); remains a post-scan reinforcement of the platform projection.
- Domains/Products — separate axes, separate KBs (N4). The registry pattern *could* later grow
  `domains`/`products` facets, but not in this spec.
- `keyword_resolution` display layer — unaffected (still reads per-article matched metadata).

---

## 5. Data flow (after)

```
INGEST  ── scan(content, registry) ──┬─ project_huntability → threat_hunting_score  (unchanged)
                                     └─ project_platform   → os_classification       (NEW, stored)
                                                              │
WORKFLOW (post-gate, unchanged gates) │
  junk_filter_node   (unchanged; 92 shared perfect discriminators come from the registry; RF model untouched)
  rank_article_node  (unchanged)
  os_detection_node  ── reads os_classification ── LLM-adjudicate tail ── ATT&CK reinforce
  extract / sigma    (unchanged)
```

---

## 6. Schema / contract impact
- **No DB migration.** `os_classification` lives in the existing `article_metadata` JSON
  column (same as `threat_hunting_score`).
- `workflow_config_schema.py` / `models.py` — unchanged (no new config fields required; the
  platform decision constants stay in the classifier).
- `config/platform_classification_kb.yaml` — **migrated into** the registry, then removed (or
  kept as a generated artifact during transition).
- No `src/prompts/*.txt` changes ⇒ no quickstart-preset updates required.

---

## 7. Backward compatibility & parity gate

The change is **safe only if** the derived outputs are identical. Acceptance requires:

- **P1 — hunt-score parity:** for a corpus sample (≥ the 251 processed articles, ideally a
  larger random sample), `score_threat_hunting_content` output is **byte-identical** before
  vs. after the registry migration (same score, same matched-keyword lists).
- **P2 — junk-filter parity:** `ContentFilter` `is_huntable` + confidence identical on the
  same sample. (Trivially preserved — platform tags are additive metadata and the RandomForest
  uses structural features, not the keyword tags; the only shared surface is the 92 perfect
  discriminators, whose *values* are held byte-identical by P1.)
- **P3 — OS parity:** `project_platform` agrees with the current `PlatformClassifier` on the
  processed set (the platform KB is migrated 1:1; any diff is a migration bug, not a feature).

If P1–P3 don't all hold, the migration is wrong — fix the registry, don't accept drift.

---

## 8. Migration plan (phased, each independently shippable)

- **Phase 0 — Confirm (docs already answer this).** Per `docs/architecture/scoring.md` the hunt
  scorer runs **at ingest on full article content**, *upstream* of the in-workflow chunk-level
  content filter (the ~86% reduction happens later, pre-LLM). So `project_platform` at ingest
  scoring time sees the full text — carriers are visible, not stripped. One assertion test
  (a known macOS carrier survives into the ingest scan) replaces the spike.
- **Phase 1 — Registry + shared scan, parity-locked. ✅ SHIPPED 2026-06-21.** `config/keyword_registry.yaml`
  (591 entries: 528 tier'd + 63 platform, generated from `HUNT_SCORING_KEYWORDS` + `platform_classification_kb.yaml`);
  `src/utils/keyword_registry.py` with `load_registry`/`build_hunt_scoring_keywords`/`platform_entries`/
  `project_huntability`/`project_platform`; `src/utils/content.py` now derives `HUNT_SCORING_KEYWORDS`
  from the registry (576-line literal removed). Parity proven (`tests/test_keyword_registry.py`):
  P1 derived dict byte-equal to a committed legacy snapshot; P3 `project_platform` verdict ==
  `classify_platforms`; G3 platform entries subsume the platform KB. 184 consumer tests green; no
  behavior change. **Deviation:** the single-pass `WeightedKeywordScan` (one matcher for both
  axes) is deferred to Phase 4 — the hunt scorer uses word-boundary regex and the platform
  classifier uses substring match, so unifying the *matching* is a behavior change; Phase 1 ships
  the shared registry + parity-preserving projections instead.
- **Phase 2 — OS at scoring time. ✅ SHIPPED 2026-06-21.** `build_os_classification(content)`
  (`keyword_registry.py`) returns the compact `detect_os`-shaped record (operating_system,
  platforms_detected, confidence, method, similarities, capped evidence). Stored in
  `article_metadata["os_classification"]` at every hunt-score persistence site:
  `ContentProcessor._enhance_metadata` (the canonical ingest seam, which `actions.py` reprocess +
  `rescore.py` both consume), plus the direct `scrape.py` and `pdf.py` ingest paths. Go-forward
  only (N2): existing rows pick it up on the next `rescore`. Tests: `build_os_classification`
  unit (3) + ingest-seam integration (1). Real-article verdicts validated (2729/1800/3330
  MacOS·high, 19 Windows·high, 1225 Linux·high, 4441/5487 multiple). No consumer reads it yet —
  Phase 3 wires `os_detection_node` to consume it.
- **Phase 3 — Simplify `os_detection_node`. ✅ SHIPPED 2026-06-21.** `detect_os` gained a
  `precomputed` param: when the node passes `article_metadata["os_classification"]` (Phase 2), it
  reuses that verdict and skips the `classify_platforms` re-scan; the Windows-keyword safety net,
  the low-confidence LLM-adjudication tail, the Windows-similarity override, and ATT&CK
  reinforcement are all unchanged. Legacy articles (no stored verdict — 0/5321 today, go-forward)
  fall back to the fresh scan, so the backlog behaves exactly as before. Tests: 3 `detect_os` unit
  (precomputed-high reuse, precomputed-low → safety net, precomputed=None → fallback) + 1
  node-level (`test_os_detection_node_reuses_precomputed_verdict`: Windows content + macOS
  precomputed → node reports macOS, proving no re-scan). 58 regression tests green.
  Follow-up: the G4 KB-file removal (done — see §14).
- **G4 cleanup — ✅ SHIPPED 2026-06-22 (§14).** The fallback was migrated to the registry and the
  legacy KB path deleted.
- **Phase 4 (optional) — fold `attack_platform_signal` + entity-dimension scans onto the shared
  `WeightedKeywordScan`** (the earlier "rule of three" engine dedup). **WON'T-DO — see §13.**

---

## 9. Platform-complete huntability — PROMOTED to priority (operator decision 2026-06-21)

Operator answered the §12 product question: **non-Windows detections matter a lot.** This moves
from "future" to the **highest-leverage work** and reorders the roadmap — Phase 1's registry is
the *substrate*; the payoff is giving huntability scoring a **platform-complete vocabulary** so
genuinely-huntable macOS/Linux articles score on their own merits and clear the *existing* gates.

**Reconciled with directive 2 ("minimum score still blocks"):** the gate *threshold* is NOT
lowered (N1 stands). The *vocabulary* is made platform-fair — validated low-FP non-Windows
carriers (see memory `reference_macos_lowfp_detection_tokens`; e.g. `do shell script`,
`osascript -e`, `launchctl load`, `/Library/Launch{Agents,Daemons}`, `xattr -d`, `dscl`,
`/etc/cron`, `systemctl`, `chmod +x`) are added to the huntability registry **with platform
tags**, so non-Windows articles *earn* a passing score rather than being let through on a
lowered bar.

**Two gates must clear — calibration review required before any vocabulary change:**
1. **Hunt-score auto-trigger.** Geometric caps mean only **perfect discriminators (75 pt)**
   meaningfully move a high threshold; lolbas (10 pt) barely does — so the strongest carriers
   likely need *perfect*-tier placement. Behavior-changing → **intentionally breaks §7 P1 parity
   for non-Windows articles** (Windows scores unchanged); validated instead by "rescues the right
   articles without FP," measured on the corpus + the eval set (**do not mutate eval rows**).
2. **Content/junk filter.** Its RandomForest is Windows-trained, but the 92 perfect
   discriminators are a **protective override** — adding non-Windows perfect discriminators
   auto-preserves their chunks **without** retraining (N3 holds for now). If measurement shows the
   RF still drops non-Windows huntable chunks, RF retraining with non-Windows annotations is a
   follow-on.

**Reordered roadmap:** Phase 0 (confirm) → Phase 1 (registry substrate, parity-locked) →
**§9 platform-complete vocabulary (priority, behavior-changing, calibration-gated)** → Phase 2
(OS at scoring) → Phase 3 (simplify `os_detection_node`) → Phase 4 (optional engine dedup).

**Recommended first action: a read-only calibration spike** — for the previously-dropped
non-Windows huntable articles, measure (a) the current hunt score + auto-trigger threshold,
(b) what tier each carrier needs to clear both gates, and (c) the FP cost — *before* changing
any vocabulary.

### 9.1 Calibration spike results (2026-06-21)

- **Gate = 85.0** (`auto_trigger_hunt_score_threshold`; `min_hunt_score` 97 is a separate higher
  filter). Geometric caps mean an `n_perfect=0` article is **mathematically capped at ~25**
  (good 5 + lolbas 10 + intel 10). Root cause confirmed: every clearly-huntable non-Windows
  article sits at `n_perfect=0` (BlueNoroff macOS 23.7, Bad Apples 12.3, Lazarus xattr 8.7,
  Quasar Linux 12.4, Shai-Hulud 8.7, SHub macOS 12.5). The non-Windows articles that *did* clear
  85 did so only via incidental **Windows** discriminators (the cross-platform Axios/ClickFix set).
- **Fix must be perfect-tier (75 pt);** lolbas (10 pt) cannot lift ~20→85. Clearing 85 needs ~3
  distinct perfect hits.
- **FP tiering** (from current-low-score population per carrier):
  - **PERFECT-safe (macOS, command/path, clean):** `do shell script`, `com.apple.quarantine`,
    `xattr -d`/`xattr -c`, `TCC.db`, `launchctl`, `/Library/LaunchAgents`, `/Library/LaunchDaemons`,
    `dscl`, `osascript`, `.plist`, `plutil`, `kextload`.
  - **NOT perfect (Linux generic, benign-sysadmin overlap → good/lolbas only):** `crontab`
    (16 low-scorers), `/dev/shm` (10), `/etc/shadow` (10), `ld_preload` (11/11), `systemctl` (6),
    `chmod +x` (5). Linux high-fidelity *persistence paths* (`/etc/cron.d`, `/etc/systemd/system`,
    `ld.so.preload`) may go perfect.
- **Impact (limited by geometry):** of currently-blocked non-Windows carrier articles, **5 carry
  3+ distinct carriers** (likely clear 85), **7 carry 2** (borderline), **22 carry 1** (stay
  blocked). Vocabulary is **necessary but not sufficient** — granular perfect entries raise
  per-article hit counts (real rescue likely > the coarse 5), and the single-carrier long tail
  only clears if the user lowers the (configurable) threshold. **Operator decision 2026-06-21:**
  proceed with the vocabulary additions (option A); threshold lever left to the user.
- **Bonus — fixes gate 2 for free:** `ContentFilter` auto-preserves any chunk containing a
  perfect discriminator, so adding non-Windows perfect discriminators makes macOS/Linux command
  chunks survive the junk filter **without** RF retraining (N3 holds).

### 9.2 Implemented + validated (2026-06-21)

Added to `HUNT_SCORING_KEYWORDS` (`src/utils/content.py`): macOS carriers added/promoted to
**perfect** (`osascript`, `do shell script`, `launchctl`, `LaunchAgents`, `LaunchDaemons`,
`com.apple.quarantine`, `xattr`, `TCC.db`, `dscl`, `plutil`, `kextload`, `.plist`) — `osascript`/
`TCC.db` *moved* up from good (no perfect+good double-count); Linux high-fidelity persistence
(`ld.so.preload`, `cron.d`) perfect; Linux generic (`systemctl`, `crontab`, `chmod +x`, `nohup`)
good. Tests: `tests/test_threat_hunting_scorer.py::TestNonWindowsHuntScoring` (5, TDD red→green) +
125 content-filter/keyword-resolution consumers green — no regression.

**Real-article re-score (in-container, live DB) — the rescue is *partial*:** scores lift
dramatically, but the **perfect bucket asymptotes at 75 while the gate is 85**, so an article also
needs supporting-bucket (intel/good) accumulation to cross:

| Article | old → new | perfect | result |
|---|---|---|---|
| 1800 BlueNoroff macOS | 23.7 → **89.4** | 3 | clears 85 |
| 2915 Bad Apples macOS | 12.3 → **85.0** | 5 | clears 85 |
| 4236 SHub macOS | 12.5 → 78.1 | 3 | under |
| 3330 Lazarus xattr | 8.7 → 74.4 | 3 | under |
| 4047 Shai-Hulud | 8.7 → 74.4 | 3 | under |
| 1826 Mac Malware | 14.7 → 70.9 | 2 | under |
| 3723 Quasar Linux | 12.4 → 12.4 | 0 | no carriers matched |

**Conclusions:** (1) the macOS vocabulary works — it lifts the stuck cluster from ~10–24 to
**70–89**; (2) the **85 gate + 75 perfect-asymptote** is now the binding constraint — a cluster
sits at 70–80, *just* under, so the **configurable auto-trigger threshold** (operator's dial;
~70–75 rescues the cluster) is the decisive next lever, not more vocabulary; (3) Linux needed its
own pass (below). Scores apply go-forward at ingest; the existing backlog needs an
operator-controlled `rescore` run.

### 9.3 Linux carrier pass (2026-06-21)

Validated Linux carriers by context (not assumption). **Perfect-tier (malware-specific, low FP):**
`xmrig` (cryptominer tool name — 36 corpus articles), `memfd_create` (fileless execution),
`chattr +i` (immutable anti-removal persistence), `proc/self/exe` (container-escape/fileless),
`history -c` (anti-forensics), `rc.local`, plus `ld.so.preload`/`cron.d` from §9.2. **Good-tier
(benign-sysadmin/driver overlap):** `insmod` (mixed: rootkit *and* firmware binary lists),
`modprobe`, `chmod 777`, `bashrc`, `base64 -d`, `dev/shm`. Tests: 2 new (red→green) + 37
content-filter/keyword consumers green.

**Real-article re-score (live DB) — same geometry wall as macOS:**

| Article | old → new | clears 85? |
|---|---|---|
| 1225 PeerBlight Linux backdoor | 73.1 → **90.7** | ✅ |
| 3205 Linux incident | 20.0 → **90.3** | ✅ |
| 24 WebLogic→XMRig | 52.5 → 71.2 | ✗ |
| 910 Linux detection-eng | 12.5 → 68.7 | ✗ |
| 2288 chattr+i miner | 8.7 → 65.0 | ✗ |
| 218 / 582 XMRig miners | ~12 → ~50 | ✗ (1 carrier) |
| 142 / 1181 LKM rootkits | ~8 → ~46 | ✗ (1 carrier: memfd_create) |
| 3723 Quasar RAT / 5021 C0XMO | unchanged | ✗ (no carriers — RAT/botnet, not miner/fileless) |

**Conclusion (both platforms):** vocabulary lifts the stuck clusters to ~45–90 and outright
rescues the dense articles, but the **85-vs-75 geometry** leaves single/double-carrier articles
just under. The decisive remaining lever is the **configurable auto-trigger threshold** (~65–70
rescues the bulk across macOS *and* Linux) — operator's call, since lowering it also increases
overall (incl. Windows) processing volume. RAT/botnet articles with no command/persistence
carriers remain out of scope for vocabulary and would need the content-filter RF retraining path.

### 9.4 Good→perfect promotions after review (2026-06-21)

Operator asked whether any good-tier additions qualify for perfect. Context review promoted two:
- **`base64 -d`** (decode-and-execute) and **`chmod 777`** (world-writable payload staging) — every
  CTI-corpus occurrence is a malware command chain (e.g. `base64 -d /tmp/x.b64 > /tmp/x && chmod
  777 /tmp/x`; `echo | base64 -d > file.php`). The 75-cap geometry means a lone benign mention
  (n=1 → 37.5) never auto-triggers.
- **Kept good (declined):** `dev/shm` (legit shared-memory mount → benign FP + content-filter
  chunk-preservation cost), and `systemctl` / `crontab` / `chmod +x` / `nohup` / `insmod` /
  `bashrc` (common benign sysadmin / driver usage). `chmod +x` deliberately stays good while
  `chmod 777` goes perfect.

Effect: e.g. article 910 (Linux detection-eng) 68.7 → 78.1. Conclusion unchanged — promotions
nudge the cluster up but the **85-vs-75 geometry** still leaves single/double-carrier articles
under; the configurable threshold remains the decisive lever. Tests: +1 (red→green); 64
hunt + content-filter green.

### 9.5 Carrier drift-fix — §9 carriers feed OS classification (SHIPPED 2026-06-21)

The §9 carriers boosted *huntability* but carried no platform tag, so a carrier-rescued article
got no OS signal from the same token (the drift surfaced in the Phase 1–2 audit). Fix: merge
platform tags into the registry carrier entries so `project_platform`/`build_os_classification`
see them. **Calibrated by the carrier-vs-platform distinction** — only carriers that are *both*
platform-discriminative *and* not already covered by an overlapping KB entry are tagged:

- **Tagged (7, weight 3):** macOS `do shell script`, `launchctl`; Linux `memfd_create`,
  `chattr +i`, `proc/self/exe`, `rc.local`, `ld.so.preload`.
- **Deliberately NOT tagged:** `xmrig`/`base64 -d`/`chmod 777` (cross-platform — run on Windows
  too), `xattr`/`history -c` (cross-Unix), and `osascript`/`LaunchAgents`/`com.apple.quarantine`/
  `cron.d`/`TCC.db`/`dscl`/… (already covered by overlapping KB entries — tagging would
  double-count on the same text).

Hunt-score parity preserved (tiers untouched → P1 byte-equal holds). `project_platform` is now a
**superset** of the legacy `classify_platforms` (P3 test re-scoped: exact-parity on legacy vocab +
a new test locking the carrier-driven detections). **Real-corpus impact:** of 27 carrier-bearing
articles, **6 change verdict** — 3 genuine rescues from Unknown (4619→macOS, 2984/5444→Linux) + 3
refinements (spurious co-label dropped, a cross-platform campaign gains its Linux label). Modest
because dense malware reports already trip the legacy KB; the win is the sparse long tail where OS
detection was weakest. Go-forward (existing stored verdicts update on rescore). 134 regression
tests green.

---

## 10. Acceptance / verification (DoD)

1. **Parity (P1–P3)** proven by a printable test run — hunt score + junk filter byte-identical;
   OS verdict matches the current classifier on the processed set. Transcript output is the
   evidence.
2. `run_tests.py` targeted suites green: `tests/services/test_platform_classifier.py`,
   `test_os_detection_service.py`, hunt-scoring tests, `tests/workflows/test_platform_telemetry_phase_one.py`,
   plus a new `tests/**/test_keyword_registry.py` (registry loads; every entry validates;
   `HUNT_SCORING_KEYWORDS` projection equals the legacy dict).
3. A processed macOS article (e.g. 2729 Sapphire Sleet, 3330 Lazarus xattr) shows a stored
   `os_classification` of macOS produced at scoring time, and `os_detection_node` consumes it
   with **no** second scan (assert via log/trace).
4. Regression suite green; ruff clean.

---

## 11. Decisions (locked 2026-06-20)
- **D-A — registry format:** the registry is the **authoritative source of truth**;
  `HUNT_SCORING_KEYWORDS` becomes a **generated projection asserted byte-equal to the legacy
  dict in a test** (not a hand-rewrite, not a side-car map). Lowest-risk migration; enforced by
  the §7 parity gate.
- **D-B — per-platform weight:** platform weight is **derived from the huntability tier via a
  default mapping, with an explicit per-entry `platform_weight` override**. Keeps the migration
  mechanical and preserves the platform KB's evidence-floor calibration.
- **D-C — projection input:** `project_platform` runs at **ingest on full article content**
  (upstream of the content filter), per `docs/architecture/scoring.md`. No degraded-input
  branch; Phase 0 is a one-line confirmation test.

---

## 12. Risk: is the platform apparatus over-engineered? (assessment recorded 2026-06-21)

Operator raised the question directly. Honest verdict: **partially — and the problem is
*sequencing and unused outputs*, not baroqueness of any single piece.** Recorded here (not
acted on) so the unification work proceeds with eyes open.

**Evidence (this session):**
- Throughput vs. capability mismatch: of 251 processed articles, **2 produced Sigma on a
  non-Windows path and zero macOS rules exist**; macOS content is rare corpus-wide
  (`launchctl` in 6 articles, `keychain` 38, mostly prose). A 3-platform capability matrix,
  per-(platform, telemetry, logsource) grouping, macOS-exclusion, Linux guidance, a 210-entry
  ATT&CK map, and an LLM adjudication tail all serve that trickle.
- **Outputs with no consumer** (grep-confirmed 2026-06-21):
  - **Domains + Products (Phase D)** — classified in `os_detection_node` and stored, but
    nothing routes/gates/generates on them. Display-only.
  - **Per-observable `platform_confidence` / `platform_rationale`** — only the producer and the
    trace API serializer touch them; Sigma grouping keys off `platform` alone. Display-only.

**Lean / correct — keep:** capability routing + skip records (prevents wasted Windows-only
extractor calls; a dict + intersection check), explicit Sigma `logsource`, the macOS no-Sigma
guard. These are correctness, not gold-plating.

**Root cause — mis-sequencing:** the rich platform *downstream* sits behind a ~99% Windows-tuned
*upstream* gate (hunt score / content filter), which drops non-Windows content before this
machinery runs. By construction it cannot pay off until the upstream huntability signal is
platform-complete — which D/§9 deliberately defers ("minimum score still blocks"). The
unification in this spec is the *anti*-over-engineering move (fewer scans, one source of truth),
but it still polishes the same low-traffic axis.

**Resolving product question (open, operator's to answer):** how much do non-Windows detections
matter? *A lot* → fix upstream first (platform-complete huntability) so the downstream earns its
keep. *A little* (Windows ≥95% of real use) → trim to "Windows vs. non-Windows→classify-and-skip"
and drop Domains/Products + confidence/rationale until something consumes them.

**Safe trims available regardless (not taken):** park Domains/Products; drop per-observable
confidence/rationale. Both are pure carrying cost today. Left in place per operator (option b).

---

## 13. Phase 4 (single-pass engine dedup) — WON'T-DO (decided 2026-06-21)

Phase 4 proposed folding `attack_platform_signal` + the entity-dimension scans onto a shared
`WeightedKeywordScan`. Investigation of the actual matchers killed it:

| Scan | Matcher | Domain |
|---|---|---|
| Hunt scorer | **word-boundary regex** (`\bwin32_\b`) | keyword tokens |
| Platform classifier | **plain substring** (`token in text`) | keyword tokens |
| entity_dimension | **plain substring** | entity tokens |
| attack_platform_signal | **ATT&CK technique-ID scan** | `Txxxx` codes, not keywords |

A true single pass can't unify these: word-boundary vs substring give different results (folding
them breaks parity for one consumer — the discipline that governed Phases 1–3), and
`attack_platform_signal` scans technique IDs, not keyword tokens (category mismatch). The only
matcher-compatible pair (platform + dimension) is two cheap scans at different layers/times, so
deduping saves ~nothing. Combined with §12 (low-traffic axis), building it would be the
over-engineering this project repeatedly rejected. **Decision: not built.** The faceted registry
(Phase 1) already delivers the real win — one source of truth — without forcing one matcher.

---

## 14. G4 cleanup — registry is the sole platform vocabulary (SHIPPED 2026-06-22)

The drift-fix (§9.5) tagged carriers in the registry but the `detect_os` *fallback* still used
`classify_platforms` → the legacy 63-entry KB, so a sparse article could classify differently on
the precomputed vs fallback path. G4 closes that:

- **`detect_os` fallback** (`os_detection_service.py`) now scans via `project_platform` (registry)
  instead of `classify_platforms` (KB) — precomputed and fallback share one vocabulary.
- **`platform_classifier.py`** retired `classify_platforms`, the `_default_classifier`,
  `DEFAULT_KB_PATH`, and `_load_kb`; `PlatformClassifier(entries=...)` is now the engine and
  `entries` is required (every caller passes the registry's `platform_entries()`).
- **`config/platform_classification_kb.yaml` deleted** — the registry is the single source for
  both hunt-scoring tiers and platform classification.
- Tests updated: the G3-subsume + P3-vs-`classify_platforms` parity tests (Phase-1 invariants now
  historical) were replaced with registry-native classification tests; the two engine integration
  tests repointed to `project_platform`. 133 regression tests green.

End-to-end proof: the `detect_os` fallback now classifies `memfd_create`/`chattr +i` content as
Linux (was Unknown pre-G4 — the KB lacked those carriers), confirming fallback ≡ precomputed.

**Spec status: COMPLETE.** Phases 1–3 + §9 vocabulary + §9.5 drift-fix + §14 G4 shipped; Phase 4
(engine dedup) deliberately not built (§13).
