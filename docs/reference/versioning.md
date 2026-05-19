# Huntable CTI Studio Versioning System

Huntable CTI Studio uses a combination of semantic versioning and planetary moon names for major releases.

## Version Format

**Major.Minor.Patch "Moon Name"**

- **Major**: Significant architectural changes or breaking changes
- **Minor**: New features, backward compatible
- **Patch**: Bug fixes, backward compatible
- **Moon Name**: Named after prominent planetary moons

## Current Version

**v7.0.0 "Europa"** - Current stable release
**v6.2.1 "Io"** - Previous stable release
**v6.2.0 "Io"** - Earlier stable release

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

### Available Planetary Moon Names

Fresh candidates for future major releases (not yet used):
Triton, Titan, Enceladus, Phobos, Deimos, Oberon, Titania, Miranda, Ariel, Umbriel, Dione, Rhea, Tethys, Mimas, Hyperion, Iapetus, Phoebe

### Used Names

- Kepler (v4.x)
- Callisto (v5.0 - v5.3)
- Ganymede (v5.2)
- Io (v6.0 - v6.2)

## Version History

### v7.0.0 "Europa" (2026-05-12)
<!-- TODO: fill Significance and Features before merging to main; pull content from docs/CHANGELOG.md [7.0.0] section. -->
- **Named After**: <fill>
- **Significance**: <fill>
- **Features**: <fill>

### v6.2.1 "Io" (2026-05-02)
- **Named After**: Io, innermost of Jupiter's four Galilean moons; most volcanically active body in the solar system
- **Significance**: Test suite green-up, source auto-healing feature removal, and eval bulk export coverage
- **Features**: `all-no-ui` suite restored to 0/0 (2949 tests); source auto-healing subsystem moved to feature branch (~7,400 lines removed); eval bulk export test coverage; 11 MkDocs strict-mode warnings resolved; dead test dependencies removed (faker, flake8, pytest-benchmark)

### v6.2.0 "Io" (2026-04-30)
- **Named After**: Io, innermost of Jupiter's four Galilean moons; most volcanically active body in the solar system
- **Significance**: Extraction QA hardening, eval bundle completeness, and CodeQL static analysis cleanup
- **Features**: RegistryQA explicit `corrections.removed[]` schema; eval bundle surfacing; traceability contract tests; `exclude_evals` filter; Sigma rule preview execution link; `warnings` key in `assess_novelty()`; null-guard hardening; 14 CodeQL alert groups resolved

### v6.1.1 "Io" (2026-04-28)
- **Named After**: Io, innermost of Jupiter's four Galilean moons; most volcanically active body in the solar system
- **Significance**: Security hardening patch -- two CodeQL alerts closed (ReDoS, stack-trace exposure), Vision LLM API key handling hardened, and browser extension MV3 compatibility fixes
- **Features**: Vision LLM proxied through backend; image fetch moved to background service worker (MV3 fix); OCR block append-on-revisit; ReDoS fix; error messages no longer leak internals to HTTP clients

### v6.1.0 "Io" (2026-04-27)
- **Named After**: Io, innermost of Jupiter's four Galilean moons; most volcanically active body in the solar system
- **Significance**: Agentic workflow hardening and infrastructure reliability
- **Features**: Infra guard circuit breaker; ContextLengthExceededError fail-fast; workflow executions table sorting and filtering; cmdline attention preprocessor; multi-rule Sigma generation; OS Detection fallback preset fields

### v6.0.0 "Io" (2026-04-23)
- **Named After**: Io, innermost of Jupiter's four Galilean moons; most volcanically active body in the solar system
- **Significance**: Major version introducing the Io codename -- browser extension Vision LLM mode, source self-healing, SSRF protection, and large-scale UI overhaul
- **Features**: Browser extension Vision LLM extraction mode; source healing trafilatura probe; eval concurrency throttle; GPT-5 family in model catalog; SSRF protection; workflow config v1->v2 migration; extractor contract runtime validators

### v5.3.0 "Callisto" (2026-04-14)
- **Named After**: Second-largest moon of Jupiter, one of the four Galilean moons
- **Significance**: New extraction sub-agents and unified traceability schema
- **Features**: ServicesExtract/ServicesQA; unified traceability envelope; cross-field Sigma similarity; Celery fork-safe DB pool fix; RegistryExtract/RegistryQA; release lock/unlock scripts

### v5.2.0 "Ganymede" (2026-03-26)
- **Named After**: Largest moon in the solar system (Jupiter)
- **Features**: Read-only `huntable_mcp` MCP server; `sigma_corpus` embedding stats; multi-round source auto-healing; Langfuse from Settings; v3 deep probes

### v5.1.0 "Callisto" (2026-03-13)
- **Named After**: Second-largest moon of Jupiter, one of the four Galilean moons
- **Significance**: Sigma deterministic semantic similarity engine, major test infrastructure overhaul
- **Features**: Sigma deterministic precompute; Cron CLI and API; LMStudio made optional; eval articles repo-first; comprehensive test coverage (+38 tests)

### v5.0.0 "Callisto" (2026-01-15)
- **Named After**: Second-largest moon of Jupiter, one of the four Galilean moons
- **Significance**: Represents stability, maturity, and advanced capabilities
- **Features**: Stabilized agentic workflow and evaluation datasets, advanced Sigma rule management, AI-assisted editing and enrichment, GitHub repository integration

### v4.0.0 "Kepler" (2025-11-04)
- **Named After**: Johannes Kepler, known for planetary motion laws
