# Sigma Prompt Audit: Generate, Validate, Enrich (2026-09-03)

Scope: the three LLM prompt surfaces that shape what lands in the Huntable-SIGMA-Rules
repository: workflow generation (`SigmaAgent`), queue validation/repair
(`POST /api/sigma-queue/{id}/validate`), and queue enrichment
(`POST /api/sigma-queue/{id}/enrich`). Each prompt was read against the Sigma
specification, the SigmaHQ conventions, the pySigma validators pinned by the rules
repository's CI (`requirements-ci.txt`: pysigma 1.5.0, pySigma-validators-sigmahq 0.21.0),
and the intent stated in `README.md` of the rules repository and
`docs/contracts/sigma-generate.md`.

Every field-name and tag finding below was confirmed by running `sigma check` with the
rules repository's blocking and advisory configs against probe rules, not inferred.

## Runtime wiring (what the model actually receives)

| Surface | System message | User message |
|---|---|---|
| Generation (DB record is persona-only, the canonical save shape) | persona from DB, else `DEFAULT_SIGMA_SYSTEM_PROMPT` | `src/prompts/sigma_generate_multi.txt` |
| Generation (quickstart preset applied) | the preset's long strategy text (the whole rule standard on this path) | the preset's short `user` scaffold ("Threat Intel Input: ... Generate all applicable rules now."); `parse_sigma_agent_prompt_data` extracts it and it formats cleanly, so the file is not used |
| Generation (raw-text DB record, what `reset-to-defaults` / `bootstrap` write) | `DEFAULT_SIGMA_SYSTEM_PROMPT` | the DB text itself, formatted directly (seeded from `sigma_generation.txt`) |
| Generation repair | same as generation | `sigma_repair_single.txt` (or the DB `SigmaRepair` record) |
| Queue validate, attempt 1 | inline literal in `sigma_queue.py` | inline f-string in `sigma_queue.py` (now `sigma_validate_single.txt`) |
| Queue validate, attempts 2-3 | same | `sigma_repair_single.txt` |
| Queue enrich | modal textarea (JS default) or route fallback literal | `sigma_enrichment.txt` |

Consequence: `sigma_generate_multi.txt` is the live generation prompt only on the persona-only and
file-fallback paths. On the quickstart-preset path the preset's own `system` text is the entire
standard and its `user` scaffold carries no `{date}`/`{author}` placeholders, so the preset text
must be corrected in place (follow-up 1); nothing in the file reaches those runs. On a raw-text
DB record (the shape `reset-to-defaults` writes), the DB copy is formatted directly, so the DB
must be re-seeded after the file changes (follow-up 2). The three copies disagreed before this
audit (tag format, date format, author, field order).

## Findings

### Generation prompt

- **G1. Network section taught field names the rules-repo CI rejects.** The abstraction
  guidance used `url`, `UserAgent`, `HttpMethod`, `HttpRequestHeader`, `HttpReferrer`,
  `ServerName`, `ALPN`, `CertificateIssuer|equalsfield`. None exist in the SigmaHQ taxonomy.
  pySigma parses them, the in-app `SigmaValidator` has no field-name check, and the rule then
  fails `sigmahq_invalid_fieldname` / `sigmahq_unknown_field` (blocking) on the PR. Confirmed:
  `ServerName` under `network_connection` fails blocking; `category: proxy` with
  `product: windows` fails `sigmahq_logsource_unknown`. The SigmaHQ proxy fields
  (`c-uri`, `c-uri-extension`, `c-useragent`, `cs-method`, `cs-host`, `cs-referrer`) pass.
- **G2. Tactic tags with underscores.** The contract, the presets and rules already in the
  repository use `attack.command_and_control`, `attack.credential_access`,
  `attack.defense_evasion`. pySigma's `ATTACKTagValidator` flags every one of them
  (advisory today; 8 hits across the current 18 rules). The Sigma convention is hyphenated.
- **G3. Technique without all of its tactics.** SigmaHQ's
  `sigmahq_tags_techniques_without_tactics` wants every tactic a technique belongs to
  (T1547.001 needs both `persistence` and `privilege-escalation`). 14 hits across the current
  rules. The prompt only said "tactic AND technique".
- **G4. Few-shot example encouraged the behaviour the prompt forbids.** The multi-rule example
  rule was `DestinationPort: 443` alone with `observables_used: []` and `level: high`, a rule
  that fires on every HTTPS connection with no grounding. Models imitate examples over prose.
- **G5. Contradictory metadata rules.** Title "<= 50 chars" (SigmaHQ allows 120, the rules
  repo carries titles over 50), the contract's `author: "Automated CTI Pipeline"` versus the
  code constant `"Huntable CTI Studio"`, `date: YYYY/MM/DD` versus the Sigma specification's
  ISO `YYYY-MM-DD`, and three different field orders across generation, enrichment and the
  contract.
- **G6. Logsource guidance was Windows-and-Sysmon only.** No mention of `registry_set`,
  `process_access`, `wmi_event`, `proxy`, `webserver`, `firewall`, of `definition:`, or that
  `product` is omitted for proxy/webserver/firewall. `service:` guidance said "only when no
  category covers the source" without the EventID pairing that `sigmahq_sysmon_missing_eventid`
  and `sigmahq_category_event_id` enforce.
- **G7. Resilience guidance omitted `|windash`**, the modifier that makes `-flag` also match
  `/flag` and unicode dashes, and never said to pair `Image|endswith` with `OriginalFileName`
  for renamed binaries. Both are standard SigmaHQ practice and both pass the pinned validators.
- **G8. No instruction-boundary statement.** Article content is untrusted input; the prompt
  never told the model to treat instruction-like article text as data.
- **G9. Two seed files drifted.** `sigma_generation.txt` and `sigma_generate_multi.txt` carried
  different logsource rules and different final instructions while serving the same role.

### Validate prompt (queue)

- **V1. Introduced rules for the first time.** The first-attempt prompt was an inline
  f-string with its own (weaker) required-field list and no tag, level, false-positive,
  field-name, logsource or date rules; the repair prompt then introduced "title <= 50 chars",
  "description starts with Detects", and "default level medium" as if new. Neither referenced
  the generation standard.
- **V2. Truncated input.** Retry attempts (and the workflow's repair pass) sent the model the
  first 500 characters of the broken rule. Most rules are longer, so the model repaired a
  fragment and invented the rest.
- **V3. Persona mismatch.** System message "senior cybersecurity detection engineer" carried no
  output constraint; the YAML-only rule lived only in the user message.
- **V4. Could not remove pipeline metadata.** Nothing told the model to drop
  `observables_used` or other custom keys, which pySigma accepts silently and the repo CI blocks
  (`custom_attributes`).

### Enrich prompt (queue)

- **E1. Double-escaped JSON schema.** The file used `{{{{` / `}}}}` for a single `.format()`
  pass, so the model saw `{{ "status": ... }}`, an invalid schema example.
- **E2. Directives duplicated between system and user messages.** The modal's default system
  prompt was a 150-line copy of the file's directive block; both were sent on every call.
- **E3. The two copies contradicted each other on `d5` (author).** The file said "preserve an
  existing author"; the modal default said "append or overwrite". The one the model followed
  depended on which surface the operator had last saved.
- **E4. Default instruction contradicted `d4`.** "better detection logic, more comprehensive
  conditions" asks for broadening; d4 forbids it.
- **E5. No shared rule standard.** Tag format, level vocabulary, field order, date format,
  logsource rules and field-name rules were absent, so enrichment could "polish" a rule into
  something the generation contract forbids.
- **E6. No instruction boundary for article content or the user instruction.**
- **E7. The live modal does not run the default at all.** Opening the enrichment modal on the
  running instance (2026-09-03) loads an operator-saved prompt version from
  `GET /api/sigma-queue/prompt/latest` (about 5,000 characters, "You are a senior detection
  engineer responsible for transforming draft Sigma rules into high-fidelity, production-ready
  detections"). That saved prompt conflicts with the directives the user message enforces: it
  demands detection rewrites and noise reduction (d4 forbids broadening), asks for a prose
  explanation with severity justification after the YAML (the route parses one JSON object), sets
  `author` to "Auto-generated from <source name>" (d5 preserves the existing author, else the
  configured author), keeps `title` under 50 characters and `date` as `YYYY/MM/DD`, and requires
  lowercase tags without the tactic-plus-technique rule. Because the system message wins ties,
  every enrichment on this instance is being pulled in two directions. Reset it to the new default
  (or save a version that only adds environment-specific guidance) before judging enrichment output.

### Pipeline findings outside the prompts (not changed here)

- **P1.** The in-app `SigmaValidator` checks structure, level, status and ATT&CK IDs but not
  field names, custom top-level keys, logsource membership, or tactic/technique pairing. A rule
  can be approved in the queue and still fail the repository's blocking CI. Adding the
  `pySigma-validators-sigmahq` blocking set to the app validator (same config file as the rules
  repo) would close the gap deterministically.
- **P2.** `_call_provider_for_sigma` caps non-reasoning models at `max_tokens=800`. A single
  complete rule is 250-400 tokens, so multi-rule output is truncated for those models.
- **P3.** pySigma 1.5.0 bundles ATT&CK v19, which retired `defense-evasion`; the rules repo
  keeps `attacktag` advisory for that reason. Keep `defense-evasion` (SigmaHQ still uses it).

## Changes made

Rule standard now originates in generation and is mirrored, not re-invented, downstream.

| File | Change |
|---|---|
| `src/prompts/sigma_generate_multi.txt` | Rewritten: input handling and instruction boundary, positive/negative scope, anti-splitting, SigmaHQ field-name table per logsource, category-first logsource rules with EventID pairing, `|windash` and `OriginalFileName` guidance, network abstraction using proxy/dns/network_connection fields only, hyphenated tactics with all-tactics rule, level calibration, metadata conventions (title <= 120, ISO date, author preservation), one grounded example in canonical field order, final check list. |
| `src/prompts/sigma_generation.txt` | Byte-identical to `sigma_generate_multi.txt` (bootstrap seed). |
| `src/prompts/sigma_validate_single.txt` | New. First-attempt validate prompt; fix-only scope, "what not to change", non-Sigma key removal, same standard. |
| `src/prompts/sigma_repair_single.txt` | Rewritten around the same standard; error-to-fix map; corrected example (hyphenated tags, ISO date, `|windash`). |
| `src/prompts/sigma_enrichment.txt` | Restructured: single-pass brace escaping, ground rules with instruction boundary, always-on rule standard, seven directives aligned with generation, JSON contract with status semantics. |
| `src/web/routes/sigma_queue.py` | Validate attempt 1 loads `sigma_validate_single`; validation system prompt is a YAML-only detection-engineering persona that never asks for `observables_used`; enrichment fallback system prompt and default instruction are constants; retry preview cap raised from 500 to 8000 chars. |
| `src/services/sigma_generation_service.py` | `DEFAULT_SIGMA_SYSTEM_PROMPT` refreshed (instruction boundary, nested mappings); repair preview cap 500 -> 8000 (`REPAIR_RULE_MAX_CHARS`); `_sigma_rule_date()` emits ISO `YYYY-MM-DD`. |
| `src/web/static/js/workflow/queue.js` | Modal default system prompt replaced by the same short constant as the route; default instruction aligned with d4. |
| `config/presets/AgentConfigs/quickstart/*.json` (12) | Tactic underscores -> hyphens and `date: YYYY-MM-DD` inside the `SigmaAgent` prompt. The preset network section still teaches non-SigmaHQ field names (see follow-ups). |
| `docs/contracts/sigma-generate.md` | v1.1: hyphenated tactics, all-tactics rule, field-name requirement, author and date corrected, live-file note. |
| `docs/reference/prompt-mapping-table.md` | Added `sigma_validate_single.txt`; clarified enrichment wiring. |
| `src/web/templates/workflow.html` | Static content of the `#enrichSystemPrompt` textarea (a third copy of the old 150-line enrichment system prompt, overwritten by JS at runtime) replaced with the short constant. |
| `src/web/routes/ai.py` | Rule export `date` now ISO `YYYY-MM-DD` (was the last writer of the slash format). |
| `docs/features/sigma-rules.md` | Repair prompt receives the rule up to 8,000 characters, not 500. |

## Follow-ups

1. Rewrite the network abstraction block inside the 3 preset variants with SigmaHQ field
   names (the file prompt is fixed; presets still carry `url`/`UserAgent`/`ServerName`
   examples). Use the `sync-prompt-presets` skill; the variants differ, so apply the delta,
   not a blind overwrite.
2. Reset the saved enrichment prompt version on the running instance (E7) and any customised
   `SigmaAgent` persona in the DB; both keep their old text until reset (Settings -> Workflow
   Config, and the enrichment modal's saved-prompt history).
3. Add the SigmaHQ validator set to the in-app `SigmaValidator` (P1) so queue validation is
   deterministic where the prompt can only advise.
4. Raise `max_tokens` for non-reasoning models in `_call_provider_for_sigma` (P2).
5. `src/web/static/js/workflow/config.js` `LOCKED_SIGMA_USER_TEMPLATE` (the effective-prompt
   preview on the Workflow Config page) is a hand-copied mirror of the pre-audit
   `sigma_generate_multi.txt`; it now shows a template that matches neither the file nor the
   preset path. Serve the real template from the backend instead of maintaining a JS copy. The
   fallback defaults in `src/web/templates/article_detail.html` (old system prompt and user
   template, overwritten when the API fetch succeeds) have the same problem.
6. Re-tag the 8 rules already in Huntable-SIGMA-Rules that carry underscored tactics or a
   technique without its tactic, and add `author`/`date` to the 8 that lack them (advisory
   run output is in the session log).
