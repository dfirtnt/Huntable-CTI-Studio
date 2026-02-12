# MCP setup (Todoist)

Todoist MCP is configured in `.cursor/mcp.json` and can point to either the hosted service or a self-managed MCP docker image, depending on your needs.

## Hosted MCP (default)

- **URL:** `https://ai.todoist.net/mcp` (via `npx -y mcp-remote`)
- **Auth:** OAuth in the client. No API token is configured inside `.cursor/mcp.json`; when you first invoke the Todoist MCP in Cursor you will be redirected to complete the Todoist OAuth flow and authorize the app.

## Local MCP (optional)

If you prefer to run a local MCP proxy, add a `todoist` entry to `.cursor/mcp.json` that points to the `ghcr.io/koki-develop/todoist-mcp-server:latest` image and forwards the `TODOIST_API_TOKEN` from your environment. Example entry:

```json
{
  "mcpServers": {
    "todoist": {
      "command": "docker",
      "args": [
        "run",
        "-i",
        "--rm",
        "-e",
        "TODOIST_API_TOKEN",
        "ghcr.io/koki-develop/todoist-mcp-server:latest"
      ],
      "env": {
        "TODOIST_API_TOKEN": "<your token>"
      }
    }
  }
}
```

Start the server locally with the same command so it listens for connections:

```
docker run -i --rm -e TODOIST_API_TOKEN ghcr.io/koki-develop/todoist-mcp-server:latest
```

Replace `<your token>` with a valid Todoist API token (store it securely and do not check secrets into git). After starting the container, restart Cursor or reload MCP so it picks up the new `todoist` entry.

## Usage notes

1. Restart Cursor (or reload MCP) after any change to `.cursor/mcp.json`.
2. Use the Create Issue skill or any Todoist tool; when prompted, complete the Todoist OAuth flow in the browser (hosted MCP) or ensure your local proxy can reach Todoist (local MCP).

**Manual fallback:** If MCP is unavailable, create the issue in Todoist manually: open project **Huntable CTI Studio** → section **Intake** → add the main task and its subtasks.
