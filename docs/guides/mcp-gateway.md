# Docker MCP Gateway

Huntable's MCP tools are normally launched over **stdio** — `.mcp.json` points at `scripts/run_mcp_server.sh`, which runs the server inside the Docker `cli` container and passes JSON-RPC through stdin/stdout. That works for Claude Code, Claude Desktop, and Cursor, but not for **Docker MCP Gateway**: the Gateway is itself a container, and the launcher shells out to `docker compose run` on the host.

The Gateway does connect to **remote** MCP servers over streamable-HTTP. The `mcp` compose profile serves the same `FastMCP` instance — same tools, same resources, same [write risk tiers](../reference/mcp-tools.md#write-risk-tiers) — over HTTP instead.

## What you get

Nothing about the tools changes. `execute_sql` stays permanently read-only, confirmation-required writes still refuse to apply production mutations through MCP, and every audited write still writes its `audit_events` row. Only the transport differs.

## Setup

**1. Generate a token.** The endpoint fronts `execute_sql` and the write tools, so it is bearer-protected and refuses to start without a token of at least 32 characters.

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put it in `.env`:

```dotenv
HUNTABLE_MCP_TOKEN=<generated value>
HUNTABLE_MCP_PORT=8009
```

**2. Start the endpoint.**

```bash
docker compose --profile mcp up -d mcp_http
```

The port is published on `127.0.0.1` only — the Gateway reaches it through `host.docker.internal`, and nothing off-host can.

**3. Register it with the Gateway.** `docker mcp` resolves `file://` server references under `~/.docker/mcp/catalogs`, so the entry gets copied there first. (Commands verified against `docker mcp` v0.43.1 — older builds used a `catalog import` verb that no longer exists.)

```bash
cp config/mcp-gateway/huntable-server-entry.yaml ~/.docker/mcp/catalogs/
```

```bash
docker mcp catalog server add custom --server file://huntable-server-entry.yaml
```

```bash
docker mcp secret set huntable.mcp_token=<the same token>
```

```bash
docker mcp server enable huntable-cti-studio
```

`custom` is the Gateway's built-in local catalog. To keep Huntable out of it, create a dedicated one instead — `docker mcp catalog create huntable:latest --title Huntable --server file://huntable-server-entry.yaml`.

**4. Verify.**

```bash
docker mcp catalog server ls custom
```

```bash
docker mcp tools list --server huntable-cti-studio
```

## Checking the endpoint by hand

`/healthz` is deliberately open, so a container healthcheck and the Gateway's reachability probe do not need the token:

```bash
curl -fsS http://localhost:8009/healthz
```

The MCP endpoint itself is at `/mcp` and rejects anything without the right bearer token:

```bash
curl -s -o /dev/null -w '%{http_code}\n' -X POST http://localhost:8009/mcp
```

That returns `401`. A correct request needs the token plus the streamable-HTTP `Accept` header:

```bash
curl -s -X POST http://localhost:8009/mcp \
  -H "Authorization: Bearer $HUNTABLE_MCP_TOKEN" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"0"}}}'
```

## Notes and limits

- **The token is the whole authorization model.** There are no per-tool scopes on this transport; anything holding the token gets every tool the stdio server exposes. Treat it like the database password it effectively wraps.
- **Fails closed.** With `HUNTABLE_MCP_TOKEN` unset or shorter than 32 characters, `build_app()` raises before a socket is bound, so the container exits rather than serving unauthenticated.
- **Same database as the app.** The service joins `cti_network` and talks to the internal `postgres` service, exactly like `web` and `cli`.
- **Not the default.** The stdio path is untouched; `.mcp.json` still uses it, and running the `mcp` profile is opt-in.
- **Restart on dependency changes.** `src/` is bind-mounted, so tool edits need only a `docker restart cti_mcp_http`. Dependency or Dockerfile changes need `docker compose build`.
