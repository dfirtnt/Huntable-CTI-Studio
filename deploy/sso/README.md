# Enterprise SSO (reverse-proxy OAuth)

Huntable CTI Studio does not implement OAuth itself. A reverse proxy performs the
OAuth flow (Google / GitHub / Microsoft Entra / any OIDC) and injects **verified
identity headers** that the app consumes, maps to roles, and audits. This directory
is a ready-to-run **nginx + oauth2-proxy** edge.

```
Browser --TLS--> sso-nginx --auth_request--> oauth2-proxy --> OAuth provider
                     \--> web:8001  (X-Huntable-Verified + verified identity headers)
```

See [`docs/guides/authentication.md`](../../docs/guides/authentication.md) for the
full identity / role / audit contract.

## Files

| File | Purpose | Committed? |
|---|---|---|
| `docker-compose.sso.yml` | Overlay adding `sso-nginx` + `oauth2-proxy` to the base project | yes |
| `nginx.conf.template` | nginx edge (strip-then-set identity, `auth_request`) | yes |
| `oauth2-proxy.env.example` | Provider + credentials template | yes |
| `nginx.conf` | Generated from the template with your hostname | gitignored |
| `oauth2-proxy.env` | Your real provider credentials | gitignored |
| `tls/fullchain.pem`, `tls/privkey.pem` | Your TLS certificate | gitignored |

`setup.sh` generates `nginx.conf` and `oauth2-proxy.env` for you when you enable SSO.
You can also create them by hand from the templates.

## Quick start

1. **App config** -- set in `.env` (setup.sh does this when you enable SSO):
   ```bash
   APP_ENV=production
   AUTH_MODE=trusted_header
   SECRET_KEY=<strong random value>
   TRUSTED_HOSTS=cti.example.com
   CORS_ALLOWED_ORIGINS=https://cti.example.com
   AUTH_ADMIN_GROUPS=...        # map your IdP groups to roles
   AUTH_OPERATOR_GROUPS=...
   AUTH_REVIEWER_GROUPS=...
   AUTH_ANALYST_GROUPS=...
   ```

2. **OAuth credentials** -- fill `deploy/sso/oauth2-proxy.env`:
   - Create an OAuth app at your provider; callback URL `https://<host>/oauth2/callback`.
   - Set `OAUTH2_PROXY_CLIENT_ID`, `OAUTH2_PROXY_CLIENT_SECRET`, and
     `OAUTH2_PROXY_COOKIE_SECRET` (`python3 -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"`).

3. **TLS** -- put a certificate at `deploy/sso/tls/fullchain.pem` + `privkey.pem`.
   For a local test:
   ```bash
   mkdir -p deploy/sso/tls
   openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
     -keyout deploy/sso/tls/privkey.pem -out deploy/sso/tls/fullchain.pem \
     -subj "/CN=cti.example.com"
   ```

4. **Block direct app access** -- in `docker-compose.yml`, remove the
   `ports: ["8001:8001"]` mapping from the `web` service (or bind it to `127.0.0.1`)
   so only `sso-nginx` can reach the app. Application tests prove header parsing and
   spoof rejection; they cannot prove network isolation -- this step is yours.

5. **Run**:
   ```bash
   docker compose -f docker-compose.yml -f deploy/sso/docker-compose.sso.yml up -d
   ```

## Verify

- Visit `https://<host>/` -> redirected to the provider login -> back to the app.
- Confirm role mapping + the audit trail: `GET /api/audit/events` (admin).
- Confirm a spoof is rejected: a request sent **directly** to the app without the
  `X-Huntable-Verified` marker must be treated as unauthenticated.
