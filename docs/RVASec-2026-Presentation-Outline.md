# From OSINT to Detection: Building an Agentic CTI Pipeline

**RVASec 2026 — Wednesday June 10, 2026 — 10:30–11:20 AM EDT**
**Grand Ballroom F/G**
**Speaker: Andrew Skatoff, Senior Manager Information Security, Federal Reserve Bank of Richmond**

---

## Talk Structure (50 minutes)

| Block | Time | Minutes | Topic |
|-------|------|---------|-------|
| 1 | 10:30–10:40 | 10 | The Human Problem |
| 2 | 10:40–10:50 | 10 | What Is Huntable CTI Studio? |
| 3 | 10:50–11:00 | 10 | Under the Hood — Architecture & Design Choices |
| 4 | 11:00–11:10 | 10 | Agent Config Tuning — The "Studio" in Action |
| 5 | 11:10–11:15 | 5 | Sigma Novelty & Similarity Search |
| 6 | 11:15–11:20 | 5 | Q&A |

---

## Block 1: The Human Problem (10:30–10:40)

**Goal:** Ground the audience in the real-world workflow you're augmenting — before showing any tech.

### Slide: The Detection Engineer's Day

Walk through the manual workflow that every threat hunter / detection engineer lives:

1. **Read** — Scan RSS feeds, vendor blogs, DFIR reports, Twitter/X threads for new threat intel
2. **Triage** — Mentally filter: "Is this relevant to my environment? Windows? Our telemetry?"
3. **Check coverage** — "Do we already have a Sigma rule or SIEM query that catches this?"
4. **Extract** — Pull out command lines, process trees, registry keys, scheduled tasks by hand
5. **Write** — Craft a new Sigma rule (or update an existing one)
6. **Validate** — Test it, tune it, submit it

### Slide: Where It Breaks Down

- **Volume**: Hundreds of articles per week across dozens of sources
- **Latency**: Days between publication and detection rule — attackers move faster
- **Consistency**: Different analysts extract differently; tribal knowledge gets lost
- **Tedium**: The reading-and-extracting part is mechanical but error-prone — classic automation target

### Slide: The Promise

> "What if you could go from a published DFIR report to a validated, deduplicated Sigma rule in hours instead of days — with the analyst still in the loop for every decision that matters?"

**Speaker note:** This is the thesis of the talk. Everything after this answers "how."

---

## Block 2: What Is Huntable CTI Studio? (10:40–10:50)

**Goal:** High-level overview — what it does, why the name, what makes it different.

### Slide: Huntable CTI Studio — One Sentence

> A Docker-first platform that ingests threat intelligence, runs an agentic LLM workflow to extract "huntable" observables, generates Sigma detection rules, and checks them for novelty against SigmaHQ and your own approved rules — all with transparent, auditable pipelines and full analyst control.

### Slide: Why "Huntables"?

- Industry uses "observables" and "IOCs" — but those terms are overloaded
- **Huntables** are enterprise-specific, telemetry-rich observables that can *directly drive detections*
  - Command lines (EDR, EventCode 4688, Sysmon EventCode 1)
  - Process trees (parent→child lineage)
  - Registry artifacts (persistence keys, defense evasion)
  - Services, scheduled tasks
  - Hunt queries (EDR/SIEM queries found inside intel articles)
- As you train the ML model and tune your prompts, huntables become **tailored to your organization**
- Not IOCs (hashes, IPs, domains) — those are perishable. Huntables target *behavior*.

### Slide: Why "Studio"?

Two meanings, both intentional:

1. **Software Studio** — A comprehensive workspace for writing, debugging, testing, and deploying a product
   - Tuning LLM prompts and agentic workflows is iterative — you need a workspace for editing configs, running evals, comparing outputs, and tracking versions
   - The ML junk filter needs a feedback loop for retraining — that's a studio workflow
   - Prompts, QA loops, and eval bundles are all editable in the UI
   - Agent contracts live in the repo as human-reference design docs — not loaded into the LLM, but used to keep prompts honest

2. **Art Studio** — Crafting detection rules is a creative act
   - A Sigma rule is as much art as engineering — balancing false positives vs. coverage, picking the right logsource, deciding what level of specificity matters
   - "Studio" evokes the hands-on, iterative, craft-based nature of the work

### Slide: What the Platform Actually Does (Pipeline Overview)

Show the end-to-end flow (this becomes the architecture diagram in the next block):

```
RSS/Scrape → Ingest → Store (PostgreSQL + pgvector)
                          ↓
                    Agentic Workflow (LangGraph):
                      1. OS Detection (Windows? → continue)
                      2. Junk Filter (ML + patterns → keep/drop)
                      3. LLM Ranking (1-10 quality score)
                      4. Extract Agent (6 sub-agents + QA loops)
                      5. Sigma Generation (LLM + pySigma validation)
                      6. Similarity Search (behavioral novelty scoring)
                      7. Queue for Human Review
```

**Speaker note:** Each of these steps is independently configurable — model, prompt, temperature, QA on/off. That's the "studio" part.

---

## Block 3: Under the Hood — Architecture & Design Choices (10:50–11:00)

**Goal:** Technical depth for the practitioner audience — *why* these choices, not just *what*.

### Slide: High-Level Architecture

Docker Compose stack:
- **FastAPI** web app (UI + API)
- **PostgreSQL + pgvector** (articles, workflow executions, Sigma rules, embeddings)
- **Redis** (Celery broker + cache)
- **Celery workers** (ingestion, background processing)
- **LangGraph** workflow engine (multi-step article analysis)

**Speaker note:** Everything runs in Docker. One `docker-compose up` and you're running. No cloud dependencies required — works fully local with LMStudio.

### Slide: Hunt Scoring — The First Gate

Before the workflow ever fires, every ingested article gets a **regex-based hunt score** (0–100). This is the triage layer that decides: is this article even worth considering?

**How it works — Geometric Series Scoring:**
- Each keyword match adds points with 50% diminishing returns per successive match
- `score = max_points × (1 − 0.5^n)` — approaches but never reaches the category max

**Scoring categories:**
- **Perfect Discriminators** (75 pts max, 92 patterns): `rundll32`, `msiexec`, `lsass.exe`, `hklm`, `powershell.exe`, `.lnk`, `MZ`, cmd.exe obfuscation patterns (`%VAR:~0,4%`, `s^e^t`)
- **LOLBAS Executables** (10 pts max, 239 patterns): Legitimate Windows binaries abused by attackers
- **Intelligence Indicators** (10 pts max, 56 patterns): `APT`, `threat actor`, `ransomware`, `Lazarus`, `FIN7`
- **Good Discriminators** (5 pts max, 89 patterns): `.bat`, `.ps1`, `Event ID`, `c:\windows\`
- **Negative Indicators** (−12.5 pts max, 25 patterns): `what is`, `best practices`, `free trial`

**Real-world distribution** (754 articles): 96.8% score 0–19, only 0.4% score 60+. The scoring is deliberately selective — most security articles are news, not hunt-worthy.

**Speaker note:** This is fast, deterministic, zero-cost — runs on every article at ingestion. It's what lets you process hundreds of articles per day without burning LLM tokens on marketing fluff.

### Slide: The Annotation System — Teaching the Machine Your Definition

- **"Huntable" is subjective** — your team decides what matters. The default training data focuses on behavioral TTPs (command lines, process trees, registry mods). If your team pivots on IOCs instead, the model supports that — it learns whatever labeling you provide.
- **UI-based annotation workflow**: Select text in an article → review character count → Auto-expand to 1,000 chars (matches production chunking) → classify as huntable/not huntable → save to DB
- **ML model (RandomForest)** trained on 278 samples, 27 features per chunk — complements the regex scoring with contextual, adaptive classification
- **ML Feedback Interface**: Analysts mark chunk predictions correct/incorrect during chunk debugging → retrain incorporates all cumulative feedback → progressive improvement over time
- **ML vs Hunt Comparison Dashboard**: Track how ML and regex scores agree/disagree across model versions, monitor accuracy trends, identify where the model needs more training data

**Speaker note:** This is where the "studio" really shows. Your analysts are iteratively teaching the system what matters to *your* organization. The dashboard makes that feedback loop visible.

### Slide: The Junk Filter — Tokenomics and Speed

**The problem:** LLM tokens cost money and time. Most of a CTI article is filler — acknowledgments, marketing copy, "contact us" sections. Sending all of it to the LLM wastes tokens and degrades output quality.

**The solution:** Hybrid ML + pattern-based content filter

- **Chunking**: 1,000-character chunks with 200-char overlap (sentence-boundary aware)
- **Pattern layer**: 92 perfect discriminators, 239 LOLBAS executables, 56 intelligence indicators, 25 "not huntable" patterns — deterministic, instant
- **ML layer**: RandomForest classifier with 27 features per chunk (pattern counts, text characteristics, technical indicators, quality ratios)
- **Perfect discriminator protection**: Chunks containing threat hunting keywords are *never* filtered, regardless of ML score
- **Result**: 20–80% token reduction while preserving all huntable content

**Training data:**
- 1,000-character chunks hand-picked primarily from theDFIRreport.com articles
- 278 total training samples (222 annotations + 81 feedback samples)
- ML Feedback Interface in the UI — analysts mark chunks correct/incorrect, model retrains

**Speaker note:** This is where the "studio" concept kicks in early — the feedback loop for retraining the junk filter is built into the UI. Your team's definition of "huntable" gets encoded into the model over time.

### Slide: Why LLMs for Extraction Instead of NER/NLP?

- Traditional NER (Named Entity Recognition) and NLP pipelines work well for *structured* entities — dates, names, locations, CVE IDs
- But huntable observables are **semi-structured and context-dependent**:
  - A command line might span multiple sentences or be embedded in prose
  - Process trees are described narratively ("the malware spawns cmd.exe which then launches powershell...")
  - Registry keys might appear as part of a remediation section, not an attack description
- LLMs handle ambiguity, context, and implicit relationships that rule-based NER misses
- Trade-off: more expensive per inference, but the junk filter keeps costs manageable

### Slide: Why LangChain → LangGraph?

> "You've probably heard of LangChain — it's great for building LLM-powered pipelines that chain together tools, prompts, and retrievers. LangGraph builds on top of that and adds graph-based orchestration with stateful nodes, conditional routing, and the ability for agents to loop back or hand off to each other — which is what you need when your workflow isn't a straight line."

**The resume analogy:**
> Imagine asking the best model to make you a resume for an important job application. You care about how every sentence is crafted. It will do a *much* better job if you guide it section by section rather than dumping the whole thing in one shot.

**Why this matters technically:**

- **Context management**: LLM results degrade with bigger jobs — even models with 1M token context windows lose focus on instructions buried in the middle. Breaking work into focused agent steps keeps each call tight.
- **Debuggability**: When a Sigma rule comes out wrong, you can trace exactly which agent step failed — was it the extraction? The ranking? The QA check? In a monolithic prompt, good luck.
- **Conditional routing**: OS Detection → non-Windows? → early exit. Rank score below threshold? → skip extraction. These gates save tokens and prevent garbage propagation.
- **QA retry loops**: LangGraph's cycle support lets the QA agent send output back to the base agent with feedback — up to N retries — without custom loop logic.

### Slide: The Config Equation

```
Agent Config = Prompt + Model + Parameters + QA Agent + Attention Preprocessor
```

- **Prompt**: role, task, instructions, json_example (stored in DB, editable in UI)
- **Model**: per-agent — can mix OpenAI, LMStudio local models, different sizes
- **Parameters**: temperature, top_p, context window
- **QA Agent**: optional validator that checks each agent's output for factuality, compliance, completeness — with retry loop
- **Attention Preprocessor**: (Cmdline agent) surfaces LOLBAS-aligned snippets at the top of the prompt to shape LLM attention

Every agent in the pipeline is independently tunable. This is the heart of the "studio."

---

## Block 4: Agent Config Tuning — The "Studio" in Action (11:00–11:10)

**Goal:** Show what it actually looks like to tune the system. This is the practitioner-focused section.

### Slide: Prompt Engineering and Agent Contracts

Each agent has a **contract** — a human-readable design doc that defines:
- What the agent extracts (scope)
- Boundary agreements with other agents (no overlap)
- Required output schema (JSON with specific fields)
- Traceability fields: `value`, `source_evidence`, `extraction_justification`, `confidence_score`

The contract is not loaded into the LLM — it's the *spec* that the prompt must implement. When output drifts, you compare prompt vs. contract to find the gap.

**Speaker note:** This is borrowed from software engineering. The contract is your requirements doc. The prompt is your implementation. QA is your test suite.

### Slide: Sigma Rule Anatomy (Quick Primer for the Audience)

```yaml
title: Suspicious PowerShell Encoded Command    # < 50 chars
id: 12345678-abcd-...                           # UUID
status: experimental
description: Detects ...                        # Starts with "Detects"
logsource:
  category: process_creation                    # CRITICAL — what log source?
  product: windows
detection:
  selection:
    CommandLine|contains:
      - '-encodedCommand'
      - '-enc'
  condition: selection
level: medium
```

**Key fields for similarity/novelty:**
- `logsource` (category + product) — determines which telemetry this applies to
- `detection` (selection + condition) — the actual matching logic
- These two fields are what the similarity engine compares

### Slide: QA Agents — The Safety Net

- QA agents validate base agent outputs for **factuality**, **compliance**, and **completeness**
- Verdicts: `pass` → continue | `needs_revision` → retry with feedback | `critical_failure` → stop
- Each QA agent can use a different model than the base agent (e.g., cheaper model for QA, expensive model for extraction)
- Configurable per-agent: enable/disable QA for each of the 6 extract sub-agents + rank agent
- Max retries configurable (default: 5)

**Design principle:** Fail-closed. When uncertain, recommend revision. No uncertain pass-through.

### Slide: Attention Preprocessor (Cmdline Agent)

- Problem: Long articles bury command lines deep in the text. LLMs lose attention.
- Solution: Scan for LOLBAS-aligned anchors (powershell, rundll32, certutil, etc.) and structural patterns (.exe + args, quoted paths, Windows paths)
- Prepend high-likelihood snippets to the prompt under `=== HIGH-LIKELIHOOD COMMAND SNIPPETS ===`
- Full article still included as `=== FULL ARTICLE (REFERENCE ONLY) ===`
- **Not extraction** — purely attention shaping. The LLM still decides what to extract.

**Speaker note:** This is a cheap, deterministic way to get better LLM results without changing the model or the prompt. It's the kind of trick that comes from iterating in the studio.

### Slide: Agent Evals — Measuring What Matters

You've tuned a prompt, swapped a model, changed the temperature. How do you know it's *better*?

- **Eval bundles**: Curated sets of articles with known-good extraction ground truth
- **Per-agent comparison**: Run the same article through two configs, compare output side-by-side
- **Badges**: `exact` (matches ground truth), `mismatch` (differs), `warning` (close but off), `pending` (not yet scored)
- **Live indicator**: Streaming dot shows when an eval run is in progress

**Speaker note / demo opportunity:** Walk through a real eval comparison — show how changing a prompt or model shifts extraction quality. This is the feedback loop that makes "studio" more than a buzzword.

---

## Block 5: Sigma Novelty & Similarity Search (11:10–11:15)

**Goal:** The payoff — how generated rules get validated against the community corpus.

### Slide: What Is Sigma? (30-Second Primer)

For anyone in the audience who hasn't worked with Sigma:
- Open-source, vendor-agnostic detection rule format (YAML)
- SigmaHQ repository: 5,247+ community rules
- Can be compiled to Splunk SPL, Elastic KQL, Microsoft Sentinel, etc.
- Think of it as "Snort rules for SIEM/EDR" — portable, shareable, versionable

### Slide: The Similarity Problem

You generate a rule. But does it already exist?
- SigmaHQ has 5,247+ rules — manual search is impractical
- Simple text matching misses semantic equivalents (different field names, same behavior)
- LLM-generated rules may use lowercase/snake_case field names vs. SigmaHQ's PascalCase

### Slide: How Similarity Search Works

Two-phase approach:

**Phase 1 — Candidate Retrieval (fast)**
- pgvector cosine similarity on rule embeddings (intfloat/e5-base-v2, 768 dimensions)
- Retrieves top ~50 candidate rules in milliseconds

**Phase 2 — Behavioral Novelty Scoring (precise)**
- Deterministic engine: Jaccard × Containment − Filter penalty
- Extracts canonical atoms from detection logic (field-value pairs)
- Case-insensitive field resolution (LLM lowercase → SigmaHQ PascalCase)
- Cross-field soft matching: same executable in `Image` vs. `CommandLine` gets 50%-dampened partial credit

### Slide: Similarity Interpretation & Action

| Similarity | Meaning | Action |
|------------|---------|--------|
| > 0.9 | Near-duplicate | Use existing rule — skip |
| 0.7–0.9 | Partial overlap | Review for extension |
| < 0.7 | Novel | New detection opportunity → Queue for review |

### Slide: Your Rules Count Too

Similarity search isn't just SigmaHQ:
- Index your own approved rules: `sigma index-customer-repo`
- Customer rules stored with `cust-` prefix, coexist in same search
- Prevents your team from duplicating rules *you've already written*

---

## Block 6: Q&A (11:15–11:20)

**Anticipated questions to prepare for:**

1. "What models do you use?" — Flexible. OpenAI GPT-4o-mini for high-quality generation, local LMStudio models (Llama, Qwen) for cost-free/private operation. Each agent can use a different model.

2. "How do you handle hallucinations?" — QA agents with factuality checks (source_evidence must match article content), pySigma validation for rule syntax, fail-closed design.

3. "Is this open source?" — [Prepare your answer — presumably yes or planned]

4. "How long does the full pipeline take per article?" — Depends on model choice. With local models: ~2-5 minutes. With OpenAI: ~30-60 seconds. Junk filter saves 20-80% of those tokens.

5. "What about non-Windows?" — OS detection gate currently filters to Windows-focused content. Linux/macOS support is architecturally possible (extractors exist for cross-platform patterns) but Windows is the primary focus.

6. "How do you retrain the junk filter?" — UI feedback loop. Analysts mark chunks correct/incorrect. Retrain script combines feedback with existing annotations. New model deployed with a container restart.

---

## Visual Assets Needed

- [ ] Architecture diagram (Docker stack + LangGraph workflow flow)
- [ ] Junk filter pipeline diagram (chunking → pattern → ML → filtered content)
- [ ] Agent pipeline diagram (7 steps with conditional gates)
- [ ] Sigma similarity two-phase diagram (embedding retrieval → behavioral novelty)
- [ ] Screenshot: Workflow execution detail (showing per-agent status)
- [ ] Screenshot: Chunk debug interface (showing kept/removed chunks)
- [ ] Screenshot: Sigma generation conversation log (LLM ↔ pySigma retry loop)
- [ ] Screenshot: Sigma queue with similarity results
- [ ] Screenshot: ML feedback interface
- [ ] Demo video or live demo plan (if time allows — probably not in 50 min)

---

## Key Themes to Weave Throughout

1. **Analyst in the loop** — The system accelerates, it doesn't replace. Every decision point has human review.
2. **Transparency** — Every extraction has source_evidence. Every Sigma rule has a conversation log. Every QA verdict is stored.
3. **Iterative tuning** — The "studio" metaphor. Prompts, models, parameters, QA, ML feedback — all tunable.
4. **Practical tokenomics** — Don't throw money at the problem. Filter first, focus the LLM, use cheap models where quality isn't critical.
5. **Days to hours** — The abstract's promise. Reinforce it with the pipeline timing.

---

## Talk Flow / Narrative Arc

**Opening hook:** "How many of you have read a DFIR report and thought, 'I should write a detection for that' — and then didn't, because you had 47 other things to do?" (Show of hands)

**Build:** Walk through the manual process → show where it breaks → introduce the platform

**Technical depth:** Architecture choices with *rationale*, not just description. Every "why" matters more than the "what."

**Payoff:** Sigma generation + novelty search = the analyst gets a pre-validated, deduplicated rule in their queue, ready for review

**Close:** "The goal isn't to replace the detection engineer. It's to make sure that when a great DFIR report drops at 2pm on a Friday, the detection doesn't wait until Monday."
