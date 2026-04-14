# src/prompts/

**These files are seed/default prompts, NOT the live prompts used at workflow execution time.**

## How prompts actually load

The live prompts used by agents at runtime live in the **database**, in the
workflow config's `agent_prompts` field. They are edited through the workflow
config UI, which creates versioned history and supports rollback
(`/api/workflow/config/prompts/{agent}/versions`,
`/api/workflow/config/prompts/{agent}/rollback`).

Files in this directory are read only in three situations:

1. **Bootstrap** -- no workflow config exists in the DB yet.
   See `src/web/routes/workflow_config.py:209` and
   `src/services/workflow_trigger_service.py:37`.
2. **Empty-prompt fallback** -- a config exists but its `agent_prompts` is empty.
   See `workflow_config.py:230` and `workflow_trigger_service.py:55`.
3. **Explicit reset** -- a user calls
   `POST /api/workflow/config/prompts/bootstrap` or
   `POST /api/workflow/config/prompts/reset-to-defaults`
   (triggered from the workflow config UI in `workflow.html`).

Loader: `src/utils/default_agent_prompts.py`. The `AGENT_PROMPT_FILES` dict maps
agent name to filename in this directory.

## What happens if you edit a file here

- **Existing installs:** nothing changes. The DB copy wins until someone resets.
- **Fresh installs / empty configs / post-reset:** the new contents become the
  starting prompt for that agent.
- **Eval reproducibility:** evals pin a `config_version` from the DB, not the
  disk file, so historical runs are unaffected by edits here.

## To change live prompt behavior

Edit via the workflow config UI (preferred -- produces a new versioned entry),
or call the config API directly. Do not rely on editing files in this directory
to change the prompts that running workflows use.

## Extract / QA pairing

Most agents come in pairs: an `*Extract` prompt that emits structured JSON from
article text, and a `*QA` prompt that grounds the extraction against the source.
When you change one side of a pair (e.g. add a field to `ServicesExtract`), the
matching QA prompt usually needs a corresponding update, because the traceability
schema is shared across the pair.
