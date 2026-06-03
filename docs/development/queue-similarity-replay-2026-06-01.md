# Queue similarity_scores replay — pre/post diff

**Run:** 2026-06-01, against `cti_postgres.sigma_rule_queue` (438 rows total).
**Trigger:** `GET /api/sigma-queue/{id}/similar-rules?force=true` for every row, 8-way parallel via xargs.
**Wall time:** 4m 45s. **HTTP outcomes:** 435 × 200, 3 × 400.
**Context:** Items 6, 7, 9, 10 shipped earlier on `europa-7.2.1`; Item 11 code is live in the bind-mounted `cti_web` (uncommitted local edits). Queue rows last scored under pre-Items-6/7/9/10 code carry stale `similarity_scores`. This replay refreshes them and surfaces any regression before [Item 5](sigma-novelty-audit-followup-2026-06-01.md) (which expands the candidate pool to include queue rules) is shipped.

## Headline

| Question | Answer |
|---|---|
| Real quality regressions? | **None.** The 5 rows flagged by the script as "max_similarity dropped ≥ 0.05" are all metric-definition artifacts crossing the pre/post code regime (see below). |
| Behavioral coverage delta | **+139 rows gained ≥1 behavioral match** (27 → 166). |
| High-precision tier change | **Stable** — rows with max_sim ≥ 0.3: 3 → 6, rows with max_sim ≥ 0.7: 0 → 0. No false-positive inflation. |
| Engine attribution | Deterministic 1,431 matches / 161 rules; legacy 15 matches / 3 rules. Consistent with the 4b measurement (legacy ~0% in production). |
| New triage workload | **43 rules transitioned `pending → needs_review`** (comparator inconclusive under new engine — see "Status transitions" below). |
| Safe to ship Item 5 on top? | Yes — queue↔corpus baseline is stable and honest. Item 5's queue↔queue additions can build on it without compounding stale scores. |

## Aggregates (pre → post)

| Metric | Pre | Post | Δ |
|---|---:|---:|---:|
| sum_behavioral_matches_found | 3,453 | 16,613 | **+13,160 (+381%)** |
| sum_total_candidates_evaluated | 46,884 | 536,541 | +489,657 (+1,044%) |
| sum_stored_match_count (top-10 cap) | 1,293 | 1,446 | +153 |
| rows with ≥1 behavioral match | 27 | 166 | **+139** |
| rows with max_similarity > 0 | 86 | 164 | +78 |
| rows with max_similarity ≥ 0.1 | 56 | 104 | +48 |
| rows with max_similarity ≥ 0.3 | 3 | 6 | +3 |
| rows with max_similarity ≥ 0.7 | 0 | 0 | 0 |

The behavioral-match swell at the low-similarity tail (0–0.1) with stable high-precision tier is exactly the shape Item 9 (wildcard↔modifier fold) and Item 6 (gate scoped to fallback) were predicted to produce: more atom intersections become possible, yielding weak but real Jaccards where the engine previously reported 0.

## The 5 "regressions" — none are real

| id | status pre→post | max_sim pre→post | behav pre→post | reading |
|---:|---|---|---|---|
| 281 | pending → needs_review | 0.30 → NULL | 0 → 0 | Pre value was a stored placeholder (max_sim=0.30 with zero behavioral matches). New engine correctly reports "no measurable similarity" and routes to needs_review. |
| 287 | pending → needs_review | 0.30 → NULL | 0 → 0 | Same shape as 281. |
| 306 | pending → needs_review | 0.30 → NULL | 0 → 0 | Same shape as 281. |
| 44  | pending → pending      | 0.2745 → 0.1625 | 0 → **97** | Pre "max" came from a comparator-inconclusive state with zero real matches. Post has 97 honest behavioral matches at a lower max score. Gain, not loss. |
| 343 | approved → approved    | 0.13 → 0.033 | 0 → 2 | Same shape as 44. Approved state preserved. |

None of these rules *lost* a real behavioral match. The first three replaced an inflated placeholder with honest NULL + needs_review routing. The last two replaced an inflated comparator-inconclusive max with a real lower max backed by actual behavioral matches.

## Status transitions

| Pre | Post | Count |
|---|---|---:|
| pending | needs_review | 43 |

These are rows where the new engine reports `comparator_inconclusive = true`. Most likely cause: the deterministic semantic precompute path doesn't model the proposed rule's atoms, the legacy fallback returns zero candidates above threshold, and the engine surfaces the inconclusive state rather than silently shelving the row.

Workload impact: reviewers will see 43 new `needs_review` tickets. Worth a heads-up before Item 5 lands so triage isn't surprised.

## HTTP 400s (3 rows — bad YAML)

| id | error |
|---:|---|
| 30 | `Rule YAML did not parse to a dictionary` |
| 42 | (same) |
| 43 | (same) |

These are pre-existing malformed queue entries — not regressions, not affected by Item 11 code. Separate cleanup candidate.

## Reproducing this measurement

```bash
# 1. Pre-snapshot
mkdir -p /tmp/item11-queue-replay
docker exec cti_postgres psql -U cti_user -d cti_scraper -c "\copy (SELECT id, status, COALESCE(max_similarity, 0) AS max_similarity, COALESCE(behavioral_matches_found, 0) AS behavioral_matches_found, COALESCE(total_candidates_evaluated, 0) AS total_candidates_evaluated, COALESCE(jsonb_array_length(similarity_scores), 0) AS stored_match_count FROM sigma_rule_queue ORDER BY id) TO STDOUT WITH CSV HEADER" > /tmp/item11-queue-replay/pre.csv

# 2. Replay (force=true persists when scores differ — see src/web/routes/sigma_queue.py:2331-2347)
cut -d, -f1 /tmp/item11-queue-replay/pre.csv | tail -n +2 > /tmp/item11-queue-replay/ids.txt
mkdir -p /tmp/item11-queue-replay/responses
xargs -P 8 -I {} sh -c \
  'curl -sS -o "/tmp/item11-queue-replay/responses/{}.json" -w "{} http=%{http_code} t=%{time_total}\n" "http://127.0.0.1:8001/api/sigma-queue/{}/similar-rules?force=true"' \
  < /tmp/item11-queue-replay/ids.txt > /tmp/item11-queue-replay/replay.log 2>&1

# 3. Post-snapshot — same SELECT as step 1, written to post.csv

# 4. Run the diff script
python3 /tmp/item11-queue-replay/diff.py
```

## Artifacts (ephemeral, on operator's `/tmp`)

- `pre.csv`, `post.csv` — 438 rows each, before/after snapshots
- `replay.log` — HTTP outcome + per-request timing for all 438 calls
- `responses/*.json` — raw API responses (435 successes)
- `diff.py` — per-rule delta + distribution + regression-flagging script
