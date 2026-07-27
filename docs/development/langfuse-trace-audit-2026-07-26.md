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

## Verification

Passed:

- Focused unit suite: 34 passed.
- Focused Sigma API suite: 24 passed.
- Ruff checks on all changed source and test files.
- Python compilation of all changed source files.
- `git diff --check`.

Blocked:

- Recent Langfuse trace, observation, score, and session reads. Credentials were unavailable and were not retrieved from protected files or settings.
- The definition-of-done requirement for one recent live execution per agent type therefore remains unverified.

No fresh cloud-provider workflows were run because the task's cost guardrail requires checking provider configuration first, and local LM Studio availability was not established in this audit.
