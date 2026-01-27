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

1. **Resolve project and section**
   - Call `get_projects`; find the project whose `name` is **CTIScraper**.
   - Call `get_sections(projectId)` for that project; find the section whose `name` matches the chosen **Section** (default **Intake**). Match case-insensitively; normalize "Up Next", "WIP", "Someday / Maybe" if needed.

2. **Create the main task**
   - `create_task(content=<Title>, description=<Description>, projectId=<CTIScraper id>, sectionId=<resolved section id>)`

3. **Create subtasks** (if any)
   - For each subtask: `create_task(content=<Subtask title>, description=<Subtask description>, projectId=<CTIScraper id>, parentId=<id of the main task created above>)`
   - Omit `sectionId` for subtasks; they inherit from the parent.

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

## Tool reference

- **Todoist MCP** (server that provides Todoist tools): `get_projects`, `get_sections`, `create_task`.
- **create_task** (concept): `content` = task title; `description` = body; `projectId` and `sectionId` or `parentId` as above.

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
