# Langfuse Trace Quality Audit - 2026-07-26

## Scope and method

This audit covers active provider-touching paths in the workflow, services, web routes, and shared provider clients. The static inventory searched for `request_chat`, `openai_chat_completions`, direct OpenAI and Anthropic endpoints, `LMStudioChatClient`, and `post_anthropic_with_retry`.

The live-data portion could not be run in this environment. `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and `LANGFUSE_HOST` were unset. The audit did not read `.env` or database-held credentials, and it did not start fresh cloud-provider workflow runs.

## Coverage matrix

| Call site | Trace shape | Static coverage | Metadata and payload | Live verification |
| --- | --- | --- | --- | --- |
| `src/workflows/agentic_workflow.py` rank path via `LLMService.rank_article` | Nested generation under workflow trace | Covered | `agent_name=rank_article`, `attempt` where applicable, execution/article IDs, model, messages, output, usage, standard tags | Not run |
| `src/workflows/agentic_workflow.py` six extraction agents via `LLMService.run_extraction_agent` | Per-attempt generation linked to workflow session | Covered | Known agent name, attempt, execution/article IDs, model, full messages, output, usage, standard tags | Not run |
| `src/workflows/agentic_workflow.py` platform adjudication | Nested generation under workflow trace | Covered; added article ID propagation | Agent name, execution/article IDs, model, full messages, output, usage, error category | Not run |
| `src/workflows/agentic_workflow.py` workflow root | Root observation | Covered | Trace name, execution/article IDs, session, user, standard tags, input/output; `workflow_crashed` child on early failure | Not run |
| `src/services/sigma_generation_service.py` generation and repair attempts | Per-call generation linked to workflow | Covered | Agent name, attempt, execution/article IDs, model, messages, output, usage, provider, finish reason | Not run |
| `src/services/eval_diagnosis_service.py` | Standalone or session-linked generation | Fixed and covered | Diagnosis agent, attempt, execution/article IDs when present, bundle ID, full prompt, output, usage, finish reason, classified errors | Not run |
| `src/services/llm_generation_service.py` | Central wrapper around its provider methods | Fixed and covered | `llm_generation`, attempt, provider, model, messages, output, usage, classified errors | Not run; no active repo callers found |
| `src/web/routes/sigma_queue.py` enrichment and validation | Standalone route generation | Fixed and covered | Agent name, attempt, provider, queue/article IDs, model, full messages, output, usage, classified errors | Not run |
| `src/web/routes/ai.py` legacy rank routes | Standalone route generation | Fixed and covered | Rank agent, article ID, model, full prompt, output, usage, classified errors | Not run |
| `src/web/llm_optimized_endpoint.py` duplicate optimized rank route | Standalone route generation using shared route helper | Fixed and covered | Rank agent, article ID, model, full prompt, output, usage, classified errors | Not run |
| `src/web/routes/scrape.py` vision extraction | Standalone generation | Fixed and covered | Vision agent, provider/model, redacted image placeholder, prompt, output, usage when returned; image length only | Not run |
| API-key and LM Studio connection probes | Standalone connection-test generation | Fixed and tagged separately | `connection_test=true`, connection-test agent/name, messages, output or classified error; excluded from production agent grouping | Not run |
| `src/services/openai_chat_client.py`, `src/services/llm_client.py`, provider clients | Transport layer only | Covered through traced callers; transport itself does not create duplicate observations | Caller owns trace name, context, payload, output, usage, and errors | Not run |
| `src/web/routes/ai.py` deprecated `custom-prompt` block | Commented-out code | Not executable; excluded | N/A | N/A |

## Metadata and error checks

- `trace_llm_call` sets a standalone trace name and propagates session attributes when an execution ID is available.
- `_build_langfuse_tags` remains the standard tag source for execution, article, and model context.
- Completion logging records messages in the observation input/model parameters, output text, and provider usage where returned.
- Error logging uses `classify_llm_error` and records the error type and category.
- `sigma_repair_attempts` is emitted by the workflow and covered by `tests/workflows/test_sigma_repair_score.py`.
- Early workflow failures emit a `workflow_crashed` child observation when the graph fails before `ainvoke` completes.
- Session-to-trace lookup and workflow debug-link code remain present in `src/utils/langfuse_client.py` and `src/web/routes/workflow_executions.py`.

## Findings and changes

1. High: eval diagnosis called `LLMService.request_chat` without a Langfuse generation. Fixed in `src/services/eval_diagnosis_service.py` and covered by a metadata regression test.
2. High: Sigma enrichment and validation routes called provider clients directly. Fixed by routing all three providers through `_call_traced_sigma_provider` in `src/web/routes/sigma_queue.py`.
3. High: legacy article-ranking routes and the duplicate optimized route called OpenAI directly. Fixed with the shared traced article-analysis helper.
4. Medium: vision extraction called OpenAI or Anthropic directly. Fixed with a redacted-input trace wrapper and usage propagation.
5. Medium: connection probes were not distinguishable from production calls because they were not traced. They now use explicit `connection_test` metadata and names.
6. Medium: platform adjudication omitted `article_id` even though the workflow state had it. Fixed by propagating the ID into the trace.

## Live verification - 2026-08-02

The live Huntable stack was healthy at verification time (`/health` returned healthy, database connected). Langfuse settings were present in the application database; credential values were not read or displayed.

Read-only Langfuse queries covered the preceding 14 days:

- 100 recent traces were returned on the first page, and sampled workflow traces had a `workflow_exec_<id>` session link.
- 159 `GENERATION` observations were returned. The observed agent names were `cmdlineextract_extraction`, `proctreeextract_extraction`, `huntqueriesextract_extraction`, `registryextract_extraction`, `servicesextract_extraction`, `scheduledtasksextract_extraction`, `networkindicatorextract_extraction`, `generate_sigma`, and one `test_generation` connection probe.
- With the documented v2 field groups requested (`core,basic,io,usage,model`), 158/159 generations had input, 100/159 had output, 159/159 had usage details, and 158/159 had a model identifier. The missing outputs were error-level generations, not successful completions.
- Representative workflow traces for executions 3669 and 3670 contained nested generations with parent observation IDs. The 3670 trace covered extraction agents and Sigma generation; its error-level Sigma generations had no output, as expected for failed calls.
- No scores were returned for the preceding 14 days, including no `sigma_repair_attempts` score. The all-time score set contained 95 older scores (`accuracy`, `count_diff`, `exact_match`, `mean_count_diff`, `passed`, and `Hallucination`) but no `sigma_repair_attempts`.
- The recent window contained no live rank, platform-adjudication, evaluation-diagnosis, route, or vision observations. No fresh provider workflow was run because RankAgent is configured for OpenAI and the cost guardrail prohibits an unapproved cloud run.

The live query also exposed a compatibility issue: Langfuse's v2 observations endpoint returns only `core,basic` fields by default. `EvalBundleService._fetch_langfuse_generation` now explicitly requests `core,basic,io,usage,model`, so trace-bundle exports receive the input, output, usage, and model fields observed above.

## Verification

Passed:

- Focused unit suite: 34 passed.
- Focused Sigma API suite: 24 passed.
- Ruff checks on all changed source and test files.
- Python compilation of all changed source files.
- `git diff --check`.
- Live read-only Langfuse query: 159 recent generations inspected with input, output, usage, model, parent-observation, and error-level summaries.
- Live trace-bundle export for execution 3669: Langfuse messages and response usage were fetched without reconstruction; usage total was present.

Blocked:

- Live coverage for the disabled rank path, evaluation diagnosis, route, and vision paths because no recent observations exist. Platform adjudication is now covered by the local Qwen3 runs, but the article workflows terminated before ranking/extraction completion.
- `sigma_repair_attempts` is not present in the recent score data; the existing code path is covered by tests, but live population remains unverified.

No fresh cloud-provider workflow was run. Local LMStudio was available, so a follow-up Qwen3-only verification was run against four short stored articles (executions 3671-3674; article IDs 6557, 1285, 1126, and 6484) after loading the committed Qwen3 preset. All four executions completed without workflow errors and linked to `workflow_exec_<id>` Langfuse sessions. Each produced a `workflow_completed` trace and a `platform_adjudication` trace. The representative execution 3671 contained 15 Qwen3 generations across `generate_sigma`, `huntqueriesextract_extraction`, `proctreeextract_qa`, `proctreeextract_extraction`, `cmdlineextract_qa`, and `cmdlineextract_extraction`; generation observations had input, usage details, model IDs, and parent-observation linkage. Expected QA generations had no output, while successful extraction/Sigma generations had output. The platform trace carried `article_id`, `execution_id`, and `model:qwen/qwen3-8b` tags.

The short articles' stored text was degraded or too short for the production junk filter, so all four runs terminated at `junk_filter` before ranking/extraction completion; no `sigma_repair_attempts` score was emitted. The Qwen3 preset also intentionally has `rank_agent_enabled=false` and `sigma_fallback_enabled=false`. Therefore this fresh run closes the local workflow/session-linkage evidence gap, but does not satisfy live coverage for the disabled rank path, evaluation diagnosis, Sigma/AI/vision routes, or live Sigma repair scoring. Those remain explicit follow-up evidence gaps rather than being marked verified.
