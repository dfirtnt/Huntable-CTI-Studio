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
| Generation (raw-text DB record, what `reset-to-defaults` / `bootstrap` write) | `DEFAULT_SIGMA_SYSTEM_PROMPT` (before the 2026-09-03 parser fix: the raw template itself, unformatted, on top of the user message) | the DB text itself, formatted directly (seeded from `sigma_generation.txt`) |
| Generation repair | same as generation | `sigma_repair_single.txt` (or the DB `SigmaRepair` record) |
| Queue validate, attempt 1 | inline literal in `sigma_queue.py` | inline f-string in `sigma_queue.py` (now `sigma_validate_single.txt`) |
| Queue validate, attempts 2-3 | same | `sigma_repair_single.txt` |
| Queue enrich | modal textarea (JS default) or route fallback literal | `sigma_enrichment.txt` |

Consequence: `sigma_generate_multi.txt` is the live generation prompt only on the persona-only and
file-fallback paths. On the quickstart-preset path the preset's own `system` text is the entire
standard and its `user` scaffold carries no `{date}`/`{author}` placeholders, so the preset text
must be corrected in place (follow-up 1, done); nothing in the file reaches those runs. On a raw-text
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
| `config/presets/AgentConfigs/quickstart/*.json` (12) | Tactic underscores -> hyphens and `date: YYYY-MM-DD` inside the `SigmaAgent` prompt; then (follow-up commit) the network block rewritten with SigmaHQ fields and `{author}`/`{date}` added to the user scaffold. |
| `docs/contracts/sigma-generate.md` | v1.1: hyphenated tactics, all-tactics rule, field-name requirement, author and date corrected, live-file note. |
| `docs/reference/prompt-mapping-table.md` | Added `sigma_validate_single.txt`; clarified enrichment wiring. |
| `src/web/templates/workflow.html` | Static content of the `#enrichSystemPrompt` textarea (a third copy of the old 150-line enrichment system prompt, overwritten by JS at runtime) replaced with the short constant. |
| `src/web/routes/ai.py` | Rule export `date` now ISO `YYYY-MM-DD` (was the last writer of the slash format). |
| `docs/features/sigma-rules.md` | Repair prompt receives the rule up to 8,000 characters, not 500. |

## First live run on the new prompt (execution 3898, 2026-09-03, Codex gpt-5.6-terra)

Same article as the morning's execution 3895 (old prompt, 6 queued rules). A `retry` reuses the
original execution's config snapshot, so execution 3897 silently re-ran the OLD prompt; only a
fresh `POST /api/workflow/articles/{id}/trigger?force=true` snapshots the current config.

- Model compliance: every rule carried tactic + technique tags (3895: 5 of 6 technique-only),
  `|windash` on the `/domain` flag, `all of selection_*` conditions, `level: medium`,
  descriptions starting with "Detects", concrete false positives, ISO dates. The generic
  single-token rules the old prompt produced (net session, net use, msiexec /qn) were not
  emitted, as the negative scope intends.
- Defect found: `author: Microsoft Security Blog - Defender` in 2 of 3 calls although the
  article has no Sigma rule; the author-preservation clause was tightened (see CHANGELOG).
- Defect found (pipeline, not prompt): every queued rule carried `generation_phase`, which the
  rules repo CI would block; fixed in `promote_to_queue`.
- Defect found (pipeline, not prompt; execution 3899): `parse_sigma_agent_prompt_data` treated the
  raw-text record as a persona because of the sibling `model` key, so the template went out
  twice (unformatted as system, formatted as user) and three rules came back with
  `author: '{author}'`. Fixed in the parser; all three runs today were on the doubled prompt.
- Defect found (pipeline, not prompt; execution 3900): the LMStudio context-window truncation ran
  for every provider because the workflow passes `ai_model="lmstudio"` as a placeholder, cutting
  the user prompt at 12,000 characters and removing the tail of the standard on every workflow
  run in the log. The earlier runs only complied because the persona bug had smuggled the whole
  template in as the system message. Fixed: cap keyed on the resolved provider; local models trim
  article content, never instructions. Open: the 13.5k template exceeds the local budgets.
- Behaviour to watch (pipeline, not prompt): 5 rules generated, 2 queued. The wscript -> node.exe
  rule, arguably the best detection in the article, was emitted only inside the
  `network_connection` group's call (observables 5-6 belonged to no eligible group, and the new
  prompt tells the model the group's observables are authoritative), so
  `_rule_logsource_matches_group` dropped it as out-of-class instead of re-homing it to the
  `process_creation` group. Under the old prompt the same rule came out of the process_creation
  call. FIXED the same day: `_find_rehome_group` re-homes such rules (see CHANGELOG), with
  regression tests built from this execution.

## Follow-ups

1. DONE 2026-09-03 (follow-up commit): the network abstraction block inside the 3 preset
   variants was replaced with a SigmaHQ-field version (proxy `c-uri`/`c-useragent`/`cs-method`,
   `dns_query`, `network_connection`, `firewall`; about 12k -> 2.5k characters per preset), the
   REQUIRED FIELDS line now points at the supplied author/date, and every preset's user scaffold
   carries `- author: {author}` / `- date: {date}` so the service's kwargs reach the model.
   Second pass: every-tactic rule, `|windash`, `OriginalFileName` and the instruction boundary
   added to all three variants (field order and title rule to the LMStudio pair); the field-name
   table was left out on purpose (length; the validator layer catches wrong fields).
2. DONE 2026-09-03 on the running instance: `SigmaAgent` reset to the on-disk default via
   `POST /api/workflow/config/prompts/reset-to-defaults` (config version 8371, md5 matches the
   file) and enrichment prompt version 7 saved from the new constants, replacing the
   conflicting version 6 (E7).
3. DONE 2026-09-03: `validate_sigma_rule` runs the rules repo's blocking set
   (`src/services/sigma_validation_blocking.yml`, pySigma-validators-sigmahq 0.21.0); issues
   surface as `SigmaHQ <Issue>` errors and `metadata["sigmahq"]`. See the CHANGELOG entry
   for the three gotchas (grounding keys, per-call validator instances, crash isolation).
4. DONE 2026-09-03: `SIGMA_MAX_TOKENS_STANDARD = 4000` (was 800) in `_call_provider_for_sigma`, with a regression test. `tests/unit/test_sigma_prompt_files.py` now pins the prompt files to their caller kwargs and the seed to the runtime file.
5. DONE 2026-09-03: the preview fetches `GET /api/workflow/config/prompts/defaults/SigmaAgent`
   (file user template + `DEFAULT_SIGMA_SYSTEM_PROMPT`) instead of a JS mirror, prefers the DB
   user template when the record carries one (preset / raw-text path), and labels the code
   default system message. Still open: the fallback defaults in
   `src/web/templates/article_detail.html` (old system prompt and user template, overwritten
   when the API fetch succeeds) are stale but harmless while the fetch works.
6. DONE 2026-09-03: https://github.com/dfirtnt/Huntable-SIGMA-Rules/pull/10 re-tags all 18 rules
   (hyphenated tactics, every tactic per technique, author/date backfilled from first-commit
   date, revoked t1089 dropped); blocking set 0 issues, remaining advisory hits are the bundled
   ATT&CK v19 dataset and style items.
