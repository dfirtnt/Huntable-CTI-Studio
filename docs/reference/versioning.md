# Huntable CTI Studio Versioning System

Huntable CTI Studio uses a combination of semantic versioning and planetary moon names for major releases.

## Version Format

**Major.Minor.Patch "Moon Name"**

- **Major**: Significant architectural changes or breaking changes
- **Minor**: New features, backward compatible
- **Patch**: Bug fixes, backward compatible
- **Moon Name**: Named after prominent planetary moons

## Current Version

**v6.1.0 "Io"** - Current stable release
**v6.0.0 "Io"** - Previous stable release
**v5.3.0 "Callisto"** - Earlier stable release
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

### v6.1.0 "Io" (2026-04-27)
<!-- TODO: fill Significance and Features before merging to main; pull content from docs/CHANGELOG.md [6.1.0] section. -->
- **Named After**: <fill>
- **Significance**: <fill>
- **Features**: <fill>

### v5.3.0 "Callisto" (Unreleased)
<!-- TODO: verify: fill Significance and Features once 5.3.0 is cut; in-progress changes are tracked under `[Unreleased]` in docs/CHANGELOG.md. -->
- **Named After**: Second-largest moon of Jupiter, one of the four Galilean moons (codename reused from the 5.0.0/5.1.0 line)

### v5.2.0 "Ganymede" (2026-03-26)
- **Named After**: Largest moon in the solar system (Jupiter)
- **Features**: Read-only `huntable_mcp` MCP server; `sigma_corpus` embedding stats via `GET /api/embeddings/stats`; multi-round source auto-healing with audit trail; Langfuse from Settings; v3 deep probes (RSS, sitemap, WordPress API, JS-render cues); Zscaler ThreatLabz source; Red Canary removed from default `config/sources.yaml`

### v5.1.0 "Callisto" (2026-03-13)
<!-- TODO: verify: fill Significance and Features from docs/CHANGELOG.md entries between 2026-01-15 and 2026-03-13. -->
- **Named After**: Second-largest moon of Jupiter, one of the four Galilean moons

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
