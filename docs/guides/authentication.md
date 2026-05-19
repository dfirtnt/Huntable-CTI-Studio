# Authentication

Huntable CTI Studio runs as a local single-user app on `127.0.0.1` and **does not require API key authentication** for any endpoint.

The `X-API-Key` / `ADMIN_API_KEY` mechanism that previously gated backup, cron, and source-management endpoints was removed in the 2026-05-03 cleanup -- it added friction to the Settings UI (which never sent the header) without protecting against any in-scope threat. See the `[Unreleased]` section of [`docs/CHANGELOG.md`](../CHANGELOG.md) for the full rationale and the list of affected endpoints.

## If You Need Authentication

The deployment model for this application is single-user, local-only. If you intend to expose the web UI publicly or share access with other users:

- Put the app behind an authenticating reverse proxy (Caddy, nginx + auth_basic, Cloudflare Access, Tailscale, etc.). This is simpler, more secure, and uniform across endpoints.
- Do **not** re-introduce the in-app `X-API-Key` check -- the regression test `tests/api/test_backup_cron_api.py::test_backup_endpoints_require_no_admin_auth` will fail and the Settings UI will silently break (it sends no header).

## Backup Endpoints

All backup, cron, and source-management endpoints accept requests without any authentication header. See [`docs/guides/backup-and-restore.md`](backup-and-restore.md) for usage.

_Last updated: 2026-05-16_
