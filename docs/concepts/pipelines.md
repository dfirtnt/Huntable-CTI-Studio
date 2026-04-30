# Agentic Workflow Execution Order

The Huntable agentic workflow runs whenever you trigger `/api/workflow/articles/{id}/trigger` or click **Reprocess** on an article. It is **orchestrated by LangGraph** (which manages step sequencing, conditional early-exit gates, and state) and **triggered via Celery tasks**. State is executed by Celery workers and persisted to `agentic_workflow_executions`, with extraction results feeding Sigma generation and similarity matching.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WORKFLOW EXECUTION FLOW                             │
└─────────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────┐
    │  Article Input  │
    └────────┬─────────┘
             │
             ▼
    ┌─────────────────────────────────┐
    │  Step 0: OS Detection           │
    │  ─────────────────────────────  │
    │  • Detect OS (Windows/Linux/etc)│
    │  • Continue if Windows detected │
    │  • Terminate if non-Windows     │
    └────────┬────────────────────────┘
             │
             ▼ (Windows detected)
    ┌─────────────────────────────────┐
    │  Step 1: Junk Filter            │
    │  ─────────────────────────────  │
    │  • Filter low-quality content  │
    │  • Keep huntable chunks        │
    └────────┬────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────┐
    │  Step 2: LLM Ranking            │
    │  ─────────────────────────────  │
    │  • Score article (0-10)         │
    │  • Continue if score ≥ threshold│
    │  • Stop if score < threshold   │
    └────────┬────────────────────────┘
             │
             ▼ (Score ≥ threshold)
    ┌─────────────────────────────────────────────────────────────────────┐
    │  Step 3: Extract Agent (Parallel Sub-Agents)                       │
    │  ────────────────────────────────────────────────────────────────  │
    │                                                                     │
    │  ┌─────────────────────────────────────────────────────────────┐  │
    │  │  Sub-Agent 1: CmdlineExtract 💻                             │  │
    │  │  • Attention Preprocessor (optional): LOLBAS snippets first  │  │
    │  │  • Extract command-line observables                          │  │
    │  │  • QA: CmdLineQA                                            │  │
    │  └─────────────────────────────────────────────────────────────┘  │
    │                                                                     │
    │  ┌─────────────────────────────────────────────────────────────┐  │
    │  │  Sub-Agent 2: HuntQueriesExtract 🔍                          │  │
    │  │  • Extract detection queries (EDR and SIGMA)                 │  │
    │  │  • QA: HuntQueriesQA                                         │  │
    │  └─────────────────────────────────────────────────────────────┘  │
    │                                                                     │
    │  ┌─────────────────────────────────────────────────────────────┐  │
    │  │  Sub-Agent 3: ProcTreeExtract 🌳                           │  │
    │  │  • Extract process lineage/tree                             │  │
    │  │  • QA: ProcTreeQA                                          │  │
    │  └─────────────────────────────────────────────────────────────┘  │
    │                                                                     │
    │                            ▼                                       │
    │                                                                     │
    │  ┌─────────────────────────────────────────────────────────────┐  │
    │  │  ExtractionSupervisorAgent 🎯                             │  │
    │  │  • Aggregate all sub-agent results                         │  │
    │  │  • Combine into unified observables                        │  │
    │  │  • Generate content summary                                │  │
    │  └─────────────────────────────────────────────────────────────┘  │
    └────────┬─────────────────────────────────────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────┐
    │  Step 4: Generate SIGMA         │
    │  ─────────────────────────────  │
    │  • Create detection rules       │
    │  • Validate with pySigma       │
    │  • Retry on validation errors  │
    └────────┬────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────┐
    │  Step 5: Similarity Search      │
    │  ─────────────────────────────  │
    │  • Check against existing rules │
    │  • Calculate similarity scores  │
    │  • Flag duplicates if found     │
    └────────┬────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────┐
    │  Step 6: Promote to Queue       │
    │  ─────────────────────────────  │
    │  • Queue rules for review       │
    │  • Mark execution complete      │
    └────────┬────────────────────────┘
             │
             ▼
    ┌─────────────────────────────────┐
    │      Workflow Complete          │
    └─────────────────────────────────┘


┌─────────────────────────────────────────────────────────────────────────────┐
│                         DETAILED SUB-AGENT FLOW                             │
└─────────────────────────────────────────────────────────────────────────────┘

    Filtered Content
         │
         ├─────────────────────────────────────────────────┐
         │                                                 │
         ▼                                                 ▼
    ┌──────────────────┐                                ┌─────────────────────┐
    │ Cmdline Extract   │                                │ HuntQueries Extract │
    │ (opt: Attn Preproc)│                                └────┬───────────────┘
    └────┬──────────────┘
         │                                                 │
         ▼                                                 ▼
    ┌──────────┐                                      ┌──────────┐
    │CmdLineQA │                                      │HuntQueriesQA│
    └────┬─────┘                                      └────┬─────┘
         │                                                 │
         │                                                 │
         ├─────────────────────────────────────────────────┤
         │                                                 │
         ▼                                                 ▼
    ┌──────────┐                                      ┌──────────┐
    │  Proc    │                                      │Supervisor│
    │ Extract  │                                      │  Agent   │
    └────┬─────┘                                      └────┬─────┘
         │                                                 │
         ▼                                                 │
    ┌──────────┐                                          │
    │ProcTree  │                                          │
    │   QA     │                                          │
    └────┬─────┘                                          │
         │                                                 │
         └─────────────────────────────────────────────────┘
                           │
                           ▼
                    Aggregated Results
                    (All Observables)


┌─────────────────────────────────────────────────────────────────────────────┐
│                         EXECUTION ORDER SUMMARY                              │
└─────────────────────────────────────────────────────────────────────────────┘

0. OS Detection          → Windows check (terminate if non-Windows)
1. Junk Filter           → Content quality filtering
2. LLM Ranking           → Article scoring (continue if ≥ threshold)
3. Extract Agent:
   ├─ CmdlineExtract     → Attention preprocessor (optional) → Command-line observables
   ├─ HuntQueriesExtract → Detection queries (EDR and SIGMA)
   ├─ ProcTreeExtract    → Process lineage
   ├─ RegistryExtract    → Windows registry artifacts (split-hive output)
   ├─ ServicesExtract    → Windows service artifacts
   ├─ ScheduledTasksExtract → Windows scheduled task artifacts
   └─ ExtractionSupervisorAgent → Aggregate all results
4. Generate SIGMA        → Create detection rules
5. Similarity Search     → Check for duplicates
6. Promote to Queue      → Queue for human review

---

## Execution Methods

The workflow can be executed via two methods:

1. **Celery** (Production) - Background execution, fast, used by default from article page
2. **Direct Test** (Testing) - Single agent testing from the configuration page

See [architecture](../internals/architecture.md) for detailed diagrams and flow breakdowns.
<!--stackedit_data:
eyJoaXN0b3J5IjpbLTU0ODgzMTY3MV19
-->