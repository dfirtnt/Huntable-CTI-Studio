---
name: huntable-eval-retrieval
description: Retrieve and compare Huntable CTI Studio evaluation runs, article eval bundles, and workflow traces through MCP. Use this whenever the user mentions eval bundles, eval runs, config selectors such as v5139a/v5139b, article evaluation traces, CmdlineExtract evaluation, or comparing replicate runs. Start with the get_eval_run convenience tool and split bundle and trace retrieval when payload size could be large.
compatibility: Requires the Huntable CTI Studio MCP server with eval retrieval tools registered.
---

# Huntable eval retrieval

Use the MCP eval tools to retrieve read-only evaluation evidence. Prefer the
convenience tool so callers do not need to remember low-level parameters.

## Default workflow

1. Call `get_eval_run` with the run selector, for example `v5139a`.
2. If comparing replicates, call it again for `v5139b` and compare `run_index`,
   article IDs, and execution IDs.
3. For one article, call `get_eval_run` with both the run selector and
   `article_id`.
4. For a trace, take the returned `execution_id` and call
   `get_workflow_execution_trace` separately.
5. Report schema versions, selected records, skipped/capped records, and any
   MCP size-limit errors clearly.

## Tool selection

- `get_eval_run`: normal entry point. Accepts a run label such as `v5139a` and
  optional `article_id` or `subagent`.
- `get_eval_bundles_by_config`: use when the caller explicitly needs a larger
  config-wide export or needs control over the bundle cap.
- `get_article_eval_bundle`: use for direct article bundle retrieval when the
  caller needs explicit `slim`, Langfuse, or trace settings.
- `get_workflow_execution_trace`: use for the workflow trace. Keep
  `include_eval_bundles=false` unless the caller explicitly requests embedded
  bundles and the response is known to fit the MCP limit.
- `get_eval_bundle`: use when an exact execution ID and agent name are already
  known.

## Run labels

- `v5139` selects all completed runs under numeric config version 5139.
- `v5139a` selects the first chronological completed replicate per article and
  subagent (`run_index=0`).
- `v5139b` selects the second (`run_index=1`).

Do not infer equivalence from the numeric version alone when a lettered run
selector is provided. Compare execution IDs to prove whether runs differ.

## Safety and output limits

All retrieval tools are read-only. Do not call diagnosis or write tools unless
the user separately requests that action. Keep bundles slim by default and
retrieve traces separately; a combined article bundle plus trace can exceed the
MCP client's 1 MB result limit.

## Example user request

“Compare v5139a and v5139b, then inspect article 2 from v5139a and retrieve
its bundle and trace.”

Translate that into MCP calls without asking the user to supply low-level
flags unless the requested result cannot fit or the user needs a non-default
subagent.
