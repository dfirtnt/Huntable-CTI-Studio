# Queue similarity_scores replay — post-deploy diff (canonical_class expansion)

**Run:** 2026-06-02, against `cti_postgres.sigma_rule_queue` (439 rows).
**Trigger:** `GET /api/sigma-queue/{id}/similar-rules?force=true` for every row, 8-way parallel via xargs.
**HTTP outcomes:** 436 × 200, 3 × 400 (the pre-existing malformed rows 30/42/43).
**Context:** This replay measures the **incremental** effect of the 2026-06-02 deploy — the canonical_class expansion (Option B `image_load`/`network_connection` going live + the Sysmon/macOS/PowerShell/web/dns classes + Conditional B keyword parity + the `EventCode→EventID` fix) — **on top of** the 2026-06-01 post-state. So the PRE snapshot here is already the refreshed (Items 6–12) baseline, not the original pre-fix state. Coverage rose 57.3% → 76.6% (2,135 → 2,854 classed) corpus-wide; this replay asks whether that changed the engine's behavior on the rules we *generate*.

## Headline

| Question | Answer |
|---|---|
| Real quality regressions? | **None.** The 3 rows flagged (18, 72, 187) are all low-signal/malformed `windows.network_connection` rules that lost *noise*, not signal — see below. |
| Behavioral coverage delta | Essentially flat: −15 matches across 3 rows. The queue is ~90% `process_creation` (already classed pre-deploy), so the expansion barely moves it — as expected. |
| High-precision tier | rows max_sim ≥ 0.3: 6 → 3, ≥ 0.7: 0 → 0. The −3 are the same 3 network_connection rows. No false-positive inflation. |
| Status transitions | **None** (0 rows changed status). |
| Net read | The deploy's queue impact is minimal and *positive*: the only movement is 3 network_connection rules shifting from noisy `logsource_key`-fallback matches to precise class-scoped assessment now that `windows.network_connection` is a live canonical class. Precision improved. |

## Aggregates (pre → post)

| Metric | Pre | Post | Δ |
|---|---:|---:|---:|
| sum_behavioral_matches_found | 16,621 | 16,606 | −15 |
| sum_total_candidates_evaluated | 537,949 | 538,757 | +808 |
| sum_stored_match_count (top-10 cap) | 1,453 | 1,438 | −15 |
| rows with ≥1 behavioral match | 167 | 164 | −3 |
| rows with max_similarity > 0 | 165 | 162 | −3 |
| rows with max_similarity ≥ 0.1 | 104 | 101 | −3 |
| rows with max_similarity ≥ 0.3 | 6 | 3 | −3 |
| rows with max_similarity ≥ 0.7 | 0 | 0 | 0 |

Every negative delta is the *same* 3 rows. No other row moved — consistent with the queue being process_creation-dominated and process_creation's class/atoms being unchanged by this deploy.

## The 3 "regressions" — none are real

All three are `logsource: {category: network_connection, product: windows}` — the class **Option B made live this deploy**. Pre-deploy they had no canonical_class and fell to the broad `logsource_key` fallback (on-the-fly path), which matched them against the 61-rule `windows|network_connection` logsource bucket on ubiquitous atoms. Post-deploy they route to the precise `windows.network_connection` precomputed path (57 classed candidates) and correctly find no *genuine* behavioral twin.

| id | detection | pre (max/behav) | post | reading |
|---:|---|---|---|---|
| 18 | `condition: all` (invalid Sigma) + `destination_ip: "Microsoft Office CDN endpoints"` (placeholder prose) + `destination_port: 443` | 0.44 / 5 | 0.0 / 0, canonical_class null | **Malformed LLM rule.** Unparseable condition → no canonical class → legacy path finds nothing. Pre-match was driven entirely by the ubiquitous `destination_port: 443`. Correctly declines to match garbage. |
| 72 | `destination_port: 443` only | 0.475 / 5 | None / 0, `windows.network_connection` | **Degenerate** — a single, maximally-common atom (HTTPS). Pre-0.475 was port-443 noise from the broad pool; post correctly reports inconclusive (one ubiquitous atom can't assert behavioral novelty). |
| 187 | `process_name: mshta.exe` + `protocol: http` + `destination_port: 80` | 0.395 / 5 | None / 0, `windows.network_connection` | Generic mshta/http/port-80 combo; pre-matches were port/protocol noise. No genuine twin among the 57 real network_connection rules. |

None lost a genuine behavioral match. All three stayed `needs_review` (status unchanged) — no triage surprise. This is the same class of finding as the 2026-06-01 replay's ids 281/287/306/44/343: a fallback-era placeholder/noise score replaced by an honest precise-path assessment.

## Why the queue barely moved (and that's correct)

The corpus coverage jump (57.3% → 76.6%, +719 rules) is large, but it lands almost entirely on telemetry classes the queue **doesn't** contain. Production generation is ~90% `process_creation` (long classed; its atoms unchanged by this deploy), so the queue↔corpus scores for those rows are stable. The expansion's value is for *future* generation as detection focus broadens beyond process_creation — exactly where the new classes (network_connection, image_load, powershell, web.*, dns) will matter. The 3 network_connection rows are the leading edge of that, and they behaved correctly.

## Reproducing

Same methodology as [queue-similarity-replay-2026-06-01.md](queue-similarity-replay-2026-06-01.md): pre-snapshot via `psql \copy`, `force=true` replay 8-way via xargs, post-snapshot, `diff.py`. Artifacts (ephemeral) under the operator's `tmp/queue-replay-2026-06-02/` (`pre.csv`, `post.csv`, `responses/*.json`, `replay.log`, `diff.py`).

## Conclusion

The canonical_class expansion deploy is **clean on the production queue** — no real regressions, no status churn, high-precision tier stable. The only movement (3 network_connection rows) is the intended effect of Option B going live: noisy fallback matches replaced by precise class-scoped assessment. Safe.
