# MCP setup (Todoist)

Todoist MCP is configured in `.cursor/mcp.json` using **Todoist’s official hosted MCP** (current API).

- **URL:** `https://ai.todoist.net/mcp` (via `npx -y mcp-remote`)
- **Auth:** OAuth in the client. No API token in the config. When you first use the Todoist MCP in Cursor, you’ll be prompted to sign in with Todoist and authorize the app.

**To use it:**

1. Restart Cursor (or reload MCP) after any change to `.cursor/mcp.json`.
2. Use the Create Issue skill or any Todoist tool; when prompted, complete the Todoist OAuth flow in the browser.

**Manual fallback:** If MCP is unavailable, create the issue in Todoist manually: open project **CTIScraper** → section **Intake** → add the main task and its subtasks.
