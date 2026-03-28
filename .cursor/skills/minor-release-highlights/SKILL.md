---
name: minor-release-highlights
description: Proposes 2–3 high-level feature-set themes for a minor or point release compared to the previous minor—user-facing capability or UX shifts, not patches or commit lists. Use when cutting release notes, tagging a minor/point version, summarizing “what changed since x.y.0”, or when the user asks for dot/minor release messaging.
---

# Minor / point release highlights

## Scope (what this is)

- **In scope:** Themes that mark a **line in the sand** versus the **previous minor** (e.g. `2.4.x` vs `2.3.x`): new workflows, expanded product surface, UX model shifts, defaults that change how people work.
- **Out of scope:** Individual commits, PR laundry, long bugfix bullets, dependency bumps listed for their own sake, internal refactors unless they clearly change user capabilities.

**Semver anchor:** “Dot” often means **patch** (`x.y.Z`). Patch releases are usually **fixes and small deltas**; **2–3 major “feature set” themes** are a better fit for **minor** (`x.Y.0`) or an intentional “small release” milestone. If the user is cutting **only** a patch, say so and offer either (a) one light “themes” paragraph only if the delta truly warrants it, or (b) a short “fixes and polish” framing instead of inventing false epics.

## Best practices

1. **Compare to the last minor baseline** — Establish the previous minor tag or `CHANGELOG` section for `x.(Y-1).0` (or agreed baseline). Everything you cite should be **since that baseline**, not “recent work.”
2. **Exactly two or three themes** — Fewer than two rarely earns a minor story; more than three dilutes the message. Each theme is a **named capability story**, not a bucket of tickets.
3. **User- or operator-visible** — Prefer outcomes analysts, admins, or integrators **experience** (screens, APIs, workflows, limits, guarantees). Defer infra-only items unless they unlock a new class of use (e.g. “reliability for 24/7 schedules”).
4. **No fake major** — Language should reflect **meaningful but bounded** change: not a rebranding, not “everything is new,” not deprecation of entire product lines unless that is true.
5. **Evidence over invention** — Ground themes in **merged changes, docs, CHANGELOG, or routes/UI** you can point to. If evidence is thin, label proposals **tentative** and say what would confirm them.
6. **Name themes for scanning** — Each theme: **short title** (3–8 words) + **one paragraph** (what changed, who it helps, why it matters) + optional **examples** (concrete screens, endpoints, or commands).

## Anti-patterns

- Themes that are just “bugs fixed” or “dependency updates.”
- One theme per commit or per PR.
- Vague labels (“improvements”, “enhancements”) without a capability claim.
- Treating a patch bump as a minor marketing release without user-visible substance.

## Workflow for the agent

1. **Confirm release type** — Minor vs patch vs “small release” tag; confirm **comparison baseline** (previous minor version or date).
2. **Gather delta** — `CHANGELOG`, git range vs tag, release notes draft, or user-provided scope; prioritize **behavioral** and **surface-area** changes.
3. **Cluster** — Group related changes into **2–3 narratives** (workflow, scope, UX paradigm, integration contract, etc.).
4. **Propose** — Output themes with titles + paragraphs; **do not** dump commit hashes or exhaustive lists unless the user asks.
5. **Sanity check** — Each theme should answer: “What could a user do or feel **after** this release that they **could not** (or barely) do before?”

## Output shape (template)

Use this structure when presenting to the user:

```markdown
## Release highlights (vs vX.(Y-1).0)

**Theme 1 — [Title]**
[One paragraph: capability / UX shift, primary audience, concrete touchpoints.]

**Theme 2 — [Title]**
[...]

**Theme 3 — [Title]** *(omit if only two themes are justified)*
[...]

**Not emphasized in this pass** (optional one line)
[Brief note: e.g. routine fixes, internal cleanup, deps — unless user wants detail.]
```

## Triggers

User says things like: **minor release**, **point release**, **dot version**, **what’s new since**, **release notes themes**, **high-level changelog** for a version bump that is **not** a major.
