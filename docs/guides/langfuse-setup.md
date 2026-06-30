# Langfuse Setup

Use this guide to connect Huntable CTI Studio to Langfuse for workflow and LLM tracing.

!!! warning "Cloud-only support and security boundary"
    Huntable CTI Studio supports **Langfuse Cloud only**. Local or self-hosted Langfuse deployments are **not supported** by this project.

    This is also a security boundary. Langfuse tracing exports operational telemetry off-box to a third-party cloud service. Depending on the workflow, traces may include prompts, article excerpts, extracted observables, model outputs, workflow metadata, and debugging context. Enable Langfuse only if your organization permits sending that telemetry to Langfuse Cloud and the traced data meets your policy requirements.

## Why connect Langfuse

Huntable CTI Studio's agentic pipeline is a multi-step, multi-model process: articles are ranked, observables are extracted by specialized agents, and Sigma rules are generated — all as a chain of LLM calls orchestrated by LangGraph. Without tracing, the only thing visible is the final output. Langfuse makes the interior of each run auditable.

**Full prompt/response replay per agent call.** Every LLM call — ranking, extraction, Sigma generation — is recorded as a child span inside the workflow trace. You can see the exact system prompt, user message, and model completion for each agent, not just the aggregated result.

**One-click navigation from any execution to its trace.** The workflow execution detail view includes a deep link into Langfuse that jumps directly to the session for that run (`/project/{id}/sessions/workflow_exec_{execution_id}`). No searching by trace ID.

**Retroactive eval enrichment.** The eval pipeline pulls LLM generation data back from Langfuse when building evaluation bundles. If an agent's prompt or response wasn't stored locally at run time, Langfuse fills the gap — keeping historical executions evaluable.

**Experiment and prompt-version tracking.** Eval runs are linked to Langfuse experiment IDs, enabling side-by-side comparison of prompt changes, model swaps, or agent config changes in the Langfuse UI.

**Operational health signal.** The `/health` endpoint and the diagnostics page report Langfuse as configured or not, so tracing failures are visible rather than silent.

## What the app uses Langfuse for

Huntable CTI Studio emits traces from the LangGraph/Celery workflow runtime and from individual LLM calls. Users do not run or connect to standalone "Langfuse agents."

The application enables tracing only when both of these values are configured:

- `LANGFUSE_PUBLIC_KEY`
- `LANGFUSE_SECRET_KEY`

`LANGFUSE_HOST` defaults to `https://cloud.langfuse.com` in the runtime client. `LANGFUSE_PROJECT_ID` is optional, but recommended because it gives the workflow UI enough metadata to build stronger deep links into Langfuse.

## Before you start

Create a Langfuse Cloud account and project first. In Langfuse Cloud, generate the project API keys you want Huntable CTI Studio to use.

Use the cloud host that matches your Langfuse account region. Common Langfuse Cloud hosts include:

- `https://cloud.langfuse.com`
- `https://us.cloud.langfuse.com`
- `https://hipaa.cloud.langfuse.com`

If your account uses a different cloud region, set `LANGFUSE_HOST` to the hostname shown by Langfuse for that project.

## Configuration values

| Setting | Required | Purpose |
| --- | --- | --- |
| `LANGFUSE_PUBLIC_KEY` | Yes | Enables tracing and authenticates requests to Langfuse Cloud |
| `LANGFUSE_SECRET_KEY` | Yes | Secret credential paired with the public key |
| `LANGFUSE_HOST` | No | Langfuse Cloud host; defaults to `https://cloud.langfuse.com` |
| `LANGFUSE_PROJECT_ID` | No | Improves workflow debug links and trace deep-linking in the UI |

## Configure Huntable CTI Studio

Huntable CTI Studio reads Langfuse settings in this order:

1. Settings saved in the web UI
2. Environment variables
3. Built-in default for `LANGFUSE_HOST`

That means a value saved in the Settings UI overrides the same variable in `.env`.

### Option 1: Configure in the Settings UI

1. Start the stack and open `http://localhost:8001/settings`.
2. In the workflow configuration area, enter:
   - Langfuse Public Key
   - Langfuse Secret Key
   - Langfuse Host
   - Langfuse Project ID (recommended)
3. Save settings.
4. Click **Test Langfuse Connection**.

### Option 2: Configure via environment variables

Set these in `.env` before starting the stack:

```bash
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
LANGFUSE_PROJECT_ID=your-project-id
```

Then start or restart the stack:

```bash
./start.sh
```

## Verify the integration

1. Use **Test Langfuse Connection** in the Settings page.
2. Trigger a workflow from the UI or API.
3. Open the workflow execution details and use the trace/debug link.

When Langfuse is configured correctly:

- the connection test succeeds;
- the health endpoint reports Langfuse as configured;
- workflow executions can open a Langfuse trace directly, or fall back to searching by `session_id`.

## Troubleshooting

### Connection test fails because keys are missing

Tracing is disabled unless both `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY` are present.

### Connection test fails with authorization or API errors

Verify that:

- the keys belong to the intended Langfuse Cloud project;
- the secret key and public key were not mixed up;
- `LANGFUSE_HOST` points at the correct Langfuse Cloud region for that project.

### Workflows run, but debug links are weaker than expected

Tracing can still work without `LANGFUSE_PROJECT_ID`, but the UI may have to fall back to broader trace search URLs instead of project-scoped deep links.

### A workflow has no trace

Traces only exist for executions that ran while Langfuse tracing was enabled. If keys were missing at run time, the workflow still executes but no Langfuse trace is emitted.

## Related docs

- [Installation](../getting-started/installation.md)
- [Configuration](../getting-started/configuration.md)
- [Debugging](../development/debugging.md)

_Last updated: 2026-06-30_
