# Agentic Workflow Execution Order

The Huntable agentic workflow runs whenever you trigger
`/api/workflow/articles/{id}/trigger` or click **Reprocess** on an article.
It is **orchestrated by LangGraph** (which manages step sequencing, conditional
early-exit gates, and state) and **triggered via Celery tasks**. State is
persisted to `agentic_workflow_executions`, with extraction results feeding
Sigma generation and similarity matching.

```
+---------------------------------------------------------------------------+
|                         WORKFLOW EXECUTION FLOW                           |
+---------------------------------------------------------------------------+

    +------------------+
    |  Article Input   |
    +--------+---------+
             |
             v
    +---------------------------------+
    |  Step 0: OS Detection           |
    |  -----------------------------  |
    |  Detect OS (Windows/Linux/etc)  |
    |  Continue if Windows detected   |
    |  Terminate if non-Windows       |
    +--------+------------------------+
             |
             v (Windows detected)
    +---------------------------------+
    |  Step 1: Junk Filter            |
    |  -----------------------------  |
    |  Filter low-quality content     |
    |  Keep huntable chunks           |
    +--------+------------------------+
             |
             v
    +---------------------------------+
    |  Step 2: LLM Ranking            |
    |  -----------------------------  |
    |  Score article (0-10)           |
    |  Continue if score >= threshold |
    |  Stop if score < threshold      |
    +--------+------------------------+
             |
             v (Score >= threshold)
    +---------------------------------+
    |  Step 3: Extract Agent          |
    |  (Sequential Sub-Agents)        |
    |  -----------------------------  |
    |  CmdlineExtract                 |
    |    Attention Preprocessor (opt) |
    |    -> CmdLineQA                 |
    |  HuntQueriesExtract             |
    |    -> HuntQueriesQA             |
    |  ProcTreeExtract                |
    |    -> ProcTreeQA                |
    |  RegistryExtract                |
    |    -> RegistryQA                |
    |  ServicesExtract                |
    |    -> ServicesQA                |
    |  ScheduledTasksExtract          |
    |    -> ScheduledTasksQA          |
    |  Aggregate -> extraction_result |
    +--------+------------------------+
             |
             v
    +---------------------------------+
    |  Step 4: Generate Sigma         |
    |  -----------------------------  |
    |  Create detection rules         |
    |  Validate with pySigma          |
    |  Retry on validation errors     |
    +--------+------------------------+
             |
             v
    +---------------------------------+
    |  Step 5: Similarity Search      |
    |  -----------------------------  |
    |  Check against existing rules   |
    |  Calculate similarity scores    |
    |  Flag duplicates if found       |
    +--------+------------------------+
             |
             v
    +---------------------------------+
    |  Step 6: Promote to Queue       |
    |  -----------------------------  |
    |  Queue rules for review         |
    |  Mark execution complete        |
    +--------+------------------------+
             |
             v
    +------------------+
    |  Workflow Complete|
    +------------------+
```

## Execution Order Summary

```
0. OS Detection             -> Windows check (terminate if non-Windows)
1. Junk Filter              -> Content quality filtering
2. LLM Ranking              -> Article scoring (continue if >= threshold)
3. Extract Agent (sequential):
   +- CmdlineExtract        -> Attention preprocessor (optional) -> command-line observables
   +- HuntQueriesExtract    -> Detection queries (EDR and Sigma)
   +- ProcTreeExtract       -> Process lineage
   +- RegistryExtract       -> Windows registry artifacts (split-hive output)
   +- ServicesExtract       -> Windows service artifacts
   +- ScheduledTasksExtract -> Windows scheduled task artifacts
   +- Aggregation           -> Merge all results into extraction_result
4. Generate Sigma           -> Create detection rules
5. Similarity Search        -> Check for duplicates
6. Promote to Queue         -> Queue for human review
```

## Execution Methods

1. **Celery** (production) — background execution, used by default from the article page
2. **Direct Test** (testing) — single agent testing from the workflow configuration page

See [Workflow Data Flow](../architecture/workflow-data-flow.md) for state and
persistence details, and [Agents](agents.md) for per-agent responsibilities.

_Last updated: 2026-05-01_
