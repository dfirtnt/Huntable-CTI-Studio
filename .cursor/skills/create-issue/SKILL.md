---
name: create-issue
description: Summarizes problems or bugs from the open chat (or uses user-provided content), proposes a Todoist issue with Title and Description and optionally subtasks, then creates tasks in the CTIScraper Todoist project via Todoist MCP after user approval. Use when the user says "Create Issue", "create issue", or asks to turn chat discussion into Todoist tasks in CTIScraper.
---

# Create Issue

Turns chat-surfaced problems/bugs (or user-provided text) into Todoist tasks in the **CTIScraper** project. Default section: **Intake**. User may override with a section name (e.g. "Up Next", "WIP").

## When to use

- User says "Create Issue" or "create issue"
- User asks to log bugs/tasks from the conversation in CTIScraper/Todoist

## Workflow

### 1. Gather content

- **If user did not provide title/description:** Summarize problems or bugs from the open chat into a single, clear issue (or one per distinct problem if that’s what the user wants).
- **If user provided title and/or description:** Use those; fill in only what’s missing from the chat.

### 2. Propose draft

Output a single **Create Issue Proposal** in this shape:

```markdown
## Create Issue Proposal

**Title:** [Short, actionable title]

**Description:** [1–3 sentences: what’s wrong, where it shows up, impact if obvious]

**Section:** Intake *(or user-specified: Up Next | WIP | Someday / Maybe)*

**Subtasks:** *(none | or list below)*
- **1.** [Subtask title] — [Brief description]
- **2.** …
```

- **Subtasks:** Add them only when the issue naturally breaks into 2+ concrete, separate steps or sub-bugs. Otherwise use "*(none)*".

Do **not** call Todoist yet. Ask for approval, e.g. “Approve to create in CTIScraper?” or “Say 'yes' / 'go' to create, or edit Title/Description/Section/Subtasks.”

### 3. Apply user feedback

- If the user edits Title, Description, Section, or Subtasks, update the proposal and repeat until they approve (or cancel).

### 4. Create in Todoist (only after approval)

When the user clearly approves (e.g. “yes”, “go”, “create it”):

1. **Resolve project and section** (official Todoist MCP: **find-projects**, **find-sections**)
   - Call **find-projects** with `{"search": "CTIScraper"}` (or no search and find by name in the list). Get the project `id` for CTIScraper.
   - Call **find-sections** with `{"projectId": "<CTIScraper id>", "search": "<Section>"}` (e.g. `"Intake"`) or omit search and find the section by name. Get the section `id`. Match case-insensitively; normalize "Up Next", "WIP", "Someday / Maybe" if needed.

2. **Create the main task** (official Todoist MCP: **add-tasks**)
   - Call **add-tasks** with `{"tasks": [{"content": "<Title>", "description": "<Description>", "projectId": "<CTIScraper id>", "sectionId": "<resolved section id>"}]}`. From the response, capture the created task’s `id` for subtasks.

3. **Create subtasks** (if any)
   - Call **add-tasks** with `{"tasks": [{"content": "<Subtask title>", "parentId": "<main task id>"}, ...]}` for each subtask (optionally include `description` per subtask). Subtasks inherit project/section from the parent.

4. **Report**
   - Confirm: main task (+ link if returned) and count of subtasks created.
   - If section or project couldn’t be resolved, say what failed and do not create.

## Section names

Use the **exact** section names from the CTIScraper board when matching (after normalizing case):

- **Intake** (default)
- **Up Next**
- **WIP**
- **Someday / Maybe**
- **Cancelled** (use only if user explicitly asks for it)

## Tool reference (Official Todoist MCP: https://ai.todoist.net/mcp)

- **find-projects**: `{"search": "CTIScraper"}` (or omit for all) → returns projects with `id`, `name`. Use CTIScraper’s `id`.
- **find-sections**: `{"projectId": "<project id>", "search": "Intake"}` (or omit search) → returns sections with `id`, `name`. Use section’s `id`.
- **add-tasks**: `{"tasks": [{"content": "...", "description": "...", "projectId": "...", "sectionId": "..."}]}` for main task; response includes created task `id`. For subtasks: `{"tasks": [{"content": "...", "parentId": "<main task id>"}, ...]}`.

**Setup:** Uses OAuth (no token in config). Restart Cursor after editing `.cursor/mcp.json`. On first use, complete the Todoist sign-in when prompted.

## Example proposal

```markdown
## Create Issue Proposal

**Title:** Dashboard sort drops active filters when changing column

**Description:** On the Articles table, changing sort by column clears current filters (source, date range). Reproduces in Chrome; need to confirm other browsers.

**Section:** Intake

**Subtasks:**
- **1.** Reproduce and document exact steps — Include screen, filters, and sort column.
- **2.** Fix filter reset on sort change — Preserve existing filters when sort is updated.
```

After user says “yes” or “go”, resolve CTIScraper + Intake, create the main task, then the two subtasks with `parentId` set to that task’s id.
