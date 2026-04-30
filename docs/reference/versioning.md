# Huntable CTI Studio Versioning System

Huntable CTI Studio uses a combination of semantic versioning and planetary moon names for major releases.

## Version Format

**Major.Minor.Patch "Moon Name"**

- **Major**: Significant architectural changes or breaking changes
- **Minor**: New features, backward compatible
- **Patch**: Bug fixes, backward compatible
- **Moon Name**: Named after prominent planetary moons

## Current Version

**v6.2.0 "Io"** - Current stable release
**v6.1.1 "Io"** - Previous stable release
**v6.1.0 "Io"** - Earlier stable release
**v4.0.0 "Kepler"** - Earlier stable release

## Planetary Moon Naming System

Major versions are named after prominent planetary moons, honoring discovery, exploration, and planetary science achievements.

### Why Planetary Moons?

- **Scientific Theme**: Aligns with exploration and discovery in planetary science
- **Systematic**: A rich set of well-known moons across the solar system
- **Memorable**: Names are recognizable and distinctive
- **Meaningful**: Ties releases to milestones in space exploration

### Named After

Planetary moons recognized by the International Astronomical Union (IAU), honoring:
- Astronomers, scientists, and explorers tied to the parent body
- Mythological figures associated with the parent planet
- Historic missions and discoveries

## Version History

### v6.2.0 "Io" (2026-04-30)
<!-- TODO: fill Significance and Features before merging to main; pull content from docs/CHANGELOG.md [6.2.0] section. -->
- **Named After**: <fill>
- **Significance**: <fill>
- **Features**: <fill>

### v6.1.1 "Io" (2026-04-28)
- **Named After**: Io, innermost of Jupiter's four Galilean moons; most volcanically active body in the solar system
- **Significance**: Security hardening patch -- two CodeQL alerts closed (ReDoS, stack-trace exposure), Vision LLM API key handling hardened, and browser extension MV3 compatibility fixes
- **Features**: Vision LLM proxied through backend (API keys no longer stored in extension); image fetch moved to background service worker (MV3 fix); OCR block append-on-revisit; force-scrape hash dedup short-circuit; ContextLengthExceededError fail-fast; infra-failure detection marks executions as failed; context-overflow and infra-not-ready flags in eval API; ReDoS fix (bounded quantifiers + input cap); error messages no longer leak internals to HTTP clients; codex-mini removed from model allowlist; Langfuse session URL path fix

### v6.1.0 "Io" (2026-04-27)
- **Named After**: Io, innermost of Jupiter's four Galilean moons; most volcanically active body in the solar system
- **Significance**: Agentic workflow hardening and infrastructure reliability -- infra-failure detection, context-length fast-fail, execution tracking overhaul, and three dependency security fixes (PyPDF2, aiohttp, jaraco.context CVE)
- **Features**: Infra guard circuit breaker (LLM never invoked with empty messages); ContextLengthExceededError fail-fast with per-subagent continuation; workflow executions table sorting and filtering; cmdline attention preprocessor; multi-rule SIGMA generation with phased approach; OS Detection fallback preset fields; Chosen/Rejected article classification removed; Ollama and LangSmith support removed; eval bundle illegal-state detection

### v6.0.0 "Io" (2026-04-23)
- **Named After**: Io, innermost of Jupiter's four Galilean moons; most volcanically active body in the solar system
- **Significance**: Major version introducing the Io codename -- browser extension Vision LLM mode, source self-healing with trafilatura and platform auto-detection, SSRF protection, and large-scale UI and test-suite overhaul
- **Features**: Browser extension Vision LLM extraction mode (GPT-4o / Claude Vision) with Hybrid fallback; OCR Tesseract.js MV3 CSP fix; source healing trafilatura probe and Ghost/Substack platform detection; eval concurrency throttle with per-article stagger; GPT-5 family in model catalog; SSRF protection on scrape endpoint; workflow config v1->v2 migration and agent normalization; extractor contract runtime validators; prompt UI sub-agent full JSON display; in-app RAG Chat removed (moved to Huntable MCP); UI test suite pruned 952->257 active tests

### v5.3.0 "Callisto" (2026-04-14)
- **Named After**: Second-largest moon of Jupiter, one of the four Galilean moons (codename reused from the 5.0.0/5.1.0 line)
- **Significance**: New extraction sub-agents and unified traceability schema -- ServicesExtract, RegistryExtract, cross-field SIGMA similarity, Celery fork-safe DB pool, and release automation scripts
- **Features**: ServicesExtract/ServicesQA sub-agent (Windows services artifacts); unified traceability envelope across all five extract sub-agents (value, source_evidence, extraction_justification, confidence_score); cross-field soft matching for SIGMA similarity (50%-dampened partial credit across process fields); Celery fork-safe DB pool fix; RegistryExtract/RegistryQA sub-agent; source-check distributed Redis lock; dashboard ingestion health scoring; release lock/unlock scripts; real scraper metrics from source_checks; OpenAI model catalog narrowed to allowlist

### v5.2.0 "Ganymede" (2026-03-26)
- **Named After**: Largest moon in the solar system (Jupiter)
- **Features**: Read-only `huntable_mcp` MCP server; `sigma_corpus` embedding stats via `GET /api/embeddings/stats`; multi-round source auto-healing with audit trail; Langfuse from Settings; v3 deep probes (RSS, sitemap, WordPress API, JS-render cues); Zscaler ThreatLabz source; Red Canary removed from default `config/sources.yaml`

### v5.1.0 "Callisto" (2026-03-13)
- **Named After**: Second-largest moon of Jupiter, one of the four Galilean moons
- **Significance**: Sigma deterministic semantic similarity engine, major test infrastructure overhaul, and LMStudio made optional
- **Features**: Sigma deterministic precompute (canonical_class, positive/negative atoms, surface_score); Cron CLI and API for backup scheduling; LMStudio made optional (missing provider now raises clear error); eval articles repo-first (no network fetch at install); cloud LLM keys stripped at test startup; sigma observables_used in prompts and UI; agent evals historical results per-column display; preset layout consolidated under config/presets/; Anthropic and OpenAI model list filtering (latest-only); comprehensive test coverage (+38 tests); integration test full-system confidence suite

### v5.0.0 "Callisto" (2026-01-15)
- **Named After**: Second-largest moon of Jupiter, one of the four Galilean moons
- **Significance**: Represents stability, maturity, and advanced capabilities
- **Features**: Stabilized agentic workflow and evaluation datasets, advanced SIGMA rule management with similarity searching, AI-assisted editing and enrichment, GitHub repository integration

### v4.0.0 "Kepler" (2025-11-04)
- **Named After**: Johannes Kepler, known for planetary motion laws
- **Significance**: Represents precision and mathematical understanding
- **Features**: Agent prompt version control system, database schema improvements, enhanced workflow configuration UI

### v3.0.0 "Copernicus" (2025-06-15)
- **Named After**: Nicolaus Copernicus, astronomer who revolutionized our understanding of the solar system
- **Significance**: Represents revolutionary changes and new paradigms
- **Features**: SIGMA rule similarity search, weighted hybrid embeddings, enhanced threat intelligence matching

### v2.0.0 "Tycho" (2025-01-15)
- **Named After**: Tycho Brahe, Danish astronomer known for accurate astronomical measurements
- **Significance**: Represents precision and systematic measurement
- **Features**: Major architectural rewrite with PostgreSQL, async support, Docker containerization

## Version Naming Convention

### Major Versions (X.0.0)
- Named after prominent planetary moons
- Each name represents a significant milestone
- Names are chosen for scientific significance, recognizability, and alignment with release goals

### Minor Versions (X.Y.0)
- Use military phonetic alphabet suffixes
- Example: v2.1.0 "Tycho-Alpha", v2.2.0 "Tycho-Bravo"

### Patch Versions (X.Y.Z)
- Numeric only
- Example: v2.1.1, v2.1.2

## Available Planetary Moon Names

The solar system's named moons provide a rich pool of candidates for future versions:

- **Io** - Volcanic Jovian moon
- **Europa** - Jovian moon with subsurface ocean
- **Titan** - Largest moon of Saturn
- **Enceladus** - Saturn's icy moon
- **Triton** - Largest moon of Neptune

### Selection Criteria

When choosing planetary moon names for major versions:
1. **Recognition**: Well-known moons from the solar system
2. **Scientific Significance**: Named after important figures or discoveries
3. **Relevance**: Names that fit the platform's exploration theme
4. **Pronunciation**: Easy to say and remember
5. **Uniqueness**: Distinctive and memorable

## References

- [International Astronomical Union (IAU)](https://www.iau.org/)
- [USGS Planetary Names](https://planetarynames.wr.usgs.gov/)

---

**Note**: This versioning system provides a unique and meaningful way to identify major releases while maintaining the scientific and technical theme of the Huntable CTI Studio platform.
