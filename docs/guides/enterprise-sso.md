# Enterprise SSO Setup

Run Huntable CTI Studio behind Google, GitHub, or Microsoft Entra (or any OIDC
provider) without building a login system into the app. A reverse proxy performs
the OAuth flow and injects verified identity headers; the app maps those to roles
and writes an audit trail.

This guide covers deployment. For the identity, role, CSRF, and audit contract the
app enforces, see [Authentication](authentication.md).

## How it works

```
Browser --TLS--> nginx --auth_request--> oauth2-proxy --> OAuth provider
                   |                                       (Google/GitHub/Entra)
                   '--> app (web:8001)
                        X-Huntable-Verified: true
                        X-Huntable-User-Id / -Email / -Groups
```

The app never speaks OAuth. The proxy authenticates the user, then on every request
**strips any client-supplied `X-Huntable-*` headers and sets verified ones**. The app
trusts those headers only when the `X-Huntable-Verified` marker is present, maps the
groups to roles, and records who did what. Two rules keep this safe:

1. The proxy must strip-then-set identity headers (the supplied nginx config does this).
2. Direct network access to the app port must be blocked so the proxy cannot be bypassed.

The repository ships a ready-to-run edge under `deploy/sso/` (nginx + oauth2-proxy).

## Prerequisites

- A public hostname (for example `cti.example.com`) and a TLS certificate for it.
- An OAuth application registered with your provider.
- Control of the host firewall or Docker port mappings, to block direct app access.

## Option A: guided setup (recommended)

`setup.sh` configures the app side and scaffolds the proxy for you.

```bash
./setup.sh           # answer "yes" at the "Enable enterprise SSO?" prompt
```

It asks for the hostname, provider, and group-to-role mappings, then:

| It writes | Where |
|---|---|
| `AUTH_MODE=trusted_header`, `SECRET_KEY`, `TRUSTED_HOSTS`, `CORS_ALLOWED_ORIGINS`, `CSRF_ENABLED`, `AUTH_*_GROUPS`, optional `APP_ENV=production` | `.env` |
| `nginx.conf` (your hostname substituted) | `deploy/sso/nginx.conf` |
| `oauth2-proxy.env` (provider set, cookie secret generated) | `deploy/sso/oauth2-proxy.env` |

Then finish steps 2-5 below (OAuth credentials, TLS, block direct access, start).

## Option B: manual configuration

For an existing install you are not re-running `setup.sh` on, set these in `.env`
(`SECRET_KEY` must be a strong, non-default value of at least 16 characters or
production startup fails):

```bash
APP_ENV=production
AUTH_MODE=trusted_header
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_urlsafe(48))">
TRUSTED_HOSTS=cti.example.com
CORS_ALLOWED_ORIGINS=https://cti.example.com
CSRF_ENABLED=auto

AUTH_ADMIN_GROUPS=...
AUTH_OPERATOR_GROUPS=...
AUTH_REVIEWER_GROUPS=...
AUTH_ANALYST_GROUPS=...
```

Then copy `deploy/sso/nginx.conf.template` to `deploy/sso/nginx.conf` (replace
`__SSO_HOSTNAME__` with your hostname) and `deploy/sso/oauth2-proxy.env.example` to
`deploy/sso/oauth2-proxy.env`. The full env-var reference is in `.env.example`.

## Changing configuration later (config.sh)

Use `config.sh` to change auth config on an existing install without re-running
`setup.sh` (which regenerates passwords, resets volumes, and restarts everything).
It edits `.env` idempotently and never touches passwords, DB volumes, or `docker compose`.

```bash
./config.sh sso            # (re)configure SSO + regenerate the deploy/sso scaffold
./config.sh sso --disable  # turn SSO off (AUTH_MODE=disabled)
./config.sh rotate-secret  # generate a new SECRET_KEY (invalidates issued CSRF tokens)
./config.sh set KEY VALUE  # set any .env key
./config.sh show           # print current auth config (SECRET_KEY redacted)
```

Config is read at process start, so apply changes with a restart:

```bash
docker restart cti_web cti_worker cti_workflow_worker cti_scheduler
```

## Step 1: register the OAuth application

Set the callback URL to `https://<your-host>/oauth2/callback` and put the resulting
credentials in `deploy/sso/oauth2-proxy.env`.

=== "GitHub"

    1. Create an OAuth App at **Settings -> Developer settings -> OAuth Apps**.
    2. Authorization callback URL: `https://cti.example.com/oauth2/callback`.
    3. In `deploy/sso/oauth2-proxy.env`:
       ```bash
       OAUTH2_PROXY_PROVIDER=github
       OAUTH2_PROXY_CLIENT_ID=<client id>
       OAUTH2_PROXY_CLIENT_SECRET=<client secret>
       OAUTH2_PROXY_GITHUB_ORG=your-org          # restrict to your org
       OAUTH2_PROXY_GITHUB_TEAM=cti-admins,cti-operators
       ```
    Team membership surfaces as groups in the form `your-org:team-slug`. Use those
    strings in the `AUTH_*_GROUPS` maps.

=== "Google"

    1. Create an OAuth client (Web application) in the Google Cloud console.
    2. Authorized redirect URI: `https://cti.example.com/oauth2/callback`.
    3. In `deploy/sso/oauth2-proxy.env`:
       ```bash
       OAUTH2_PROXY_PROVIDER=google
       OAUTH2_PROXY_CLIENT_ID=<client id>
       OAUTH2_PROXY_CLIENT_SECRET=<client secret>
       OAUTH2_PROXY_OIDC_ISSUER_URL=https://accounts.google.com
       ```
    Workspace group membership requires a service account; see the oauth2-proxy
    Google provider docs. Map group emails (for example `cti-admins@example.com`)
    in the `AUTH_*_GROUPS` maps.

=== "Microsoft Entra"

    1. Register an application in Entra ID; add a Web redirect URI
       `https://cti.example.com/oauth2/callback`.
    2. Add the `groups` claim to the token configuration.
    3. In `deploy/sso/oauth2-proxy.env`:
       ```bash
       OAUTH2_PROXY_PROVIDER=oidc
       OAUTH2_PROXY_CLIENT_ID=<application id>
       OAUTH2_PROXY_CLIENT_SECRET=<client secret>
       OAUTH2_PROXY_OIDC_ISSUER_URL=https://login.microsoftonline.com/<tenant-id>/v2.0
       OAUTH2_PROXY_SCOPE=openid email profile groups
       ```
    Entra emits group object IDs (GUIDs); use those GUIDs in the `AUTH_*_GROUPS` maps.

Generate the cookie secret once and add it to the same file:

```bash
python3 -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

## Step 2: map IdP groups to roles

The app grants a role to a request when the user's groups intersect the role's
configured group list. `admin` satisfies every role check.

| Env var | Role | Grants |
|---|---|---|
| `AUTH_ADMIN_GROUPS` | `admin` | Settings, credentials, audit, backup, model management |
| `AUTH_OPERATOR_GROUPS` | `operator` | Sources, scheduled jobs, workflow actions |
| `AUTH_REVIEWER_GROUPS` | `rule_reviewer` | Sigma queue review actions |
| `AUTH_ANALYST_GROUPS` | `analyst` | Annotations, ingest, article mutations |

Each accepts a comma-separated list of provider group identifiers. Do not commit real
group names to source control.

## Step 3: add a TLS certificate

Place a certificate at `deploy/sso/tls/fullchain.pem` and key at
`deploy/sso/tls/privkey.pem`. For a local test, generate a self-signed pair:

```bash
mkdir -p deploy/sso/tls
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -keyout deploy/sso/tls/privkey.pem -out deploy/sso/tls/fullchain.pem \
  -subj "/CN=cti.example.com"
```

## Step 4: block direct access to the app

The trusted-header model is only safe when the proxy is the sole path to the app.
In `docker-compose.yml`, remove the `ports: ["8001:8001"]` mapping from the `web`
service, or bind it to `127.0.0.1`. On a VM or Kubernetes, enforce the same with a
firewall rule or NetworkPolicy.

!!! warning "Tests cannot prove this"
    Application tests verify header parsing and spoof rejection. They cannot verify
    network isolation. Confirm the app port is unreachable from outside the proxy.

## Step 5: start the proxy

```bash
docker compose -f docker-compose.yml -f deploy/sso/docker-compose.sso.yml up -d
```

Visit `https://<your-host>/`. The proxy redirects to the provider login, then back
to the app.

## Verify

- **Login**: an unauthenticated visit redirects to the provider and returns signed in.
- **Roles**: confirm a low-privilege user is denied an admin action (HTTP 403) and an
  admin is allowed.
- **Audit**: as an admin, `GET /api/audit/events` shows `auth.request_*` and mutation
  events with the actor's identity.
- **Spoof rejection**: a request sent directly to the app (bypassing the proxy) with a
  forged `X-Huntable-*` header is treated as unauthenticated. If this succeeds, direct
  access is not blocked (revisit Step 4).

## Local testing without a domain (login gate)

To try SSO on `localhost` with no domain and no TLS, use the login-gate variant in
`deploy/sso/local/`: oauth2-proxy sits in front of the running app and requires a
login, but the app keeps its default access (no per-user roles). It attaches to the
app's Docker network, so the auth code does not need to be deployed. Microsoft and
Google both allow `http://localhost` redirect URIs for this. See
`deploy/sso/local/README.md` for the steps. Use this to confirm the provider/OIDC
flow works, then move to the full RBAC setup above for roles.

## Production checklist

- [ ] `APP_ENV=production` and the app starts (fail-closed checks pass).
- [ ] `SECRET_KEY` is strong and non-default.
- [ ] `TRUSTED_HOSTS` and `CORS_ALLOWED_ORIGINS` are your real host, not wildcards.
- [ ] Direct access to the app port is blocked; only the proxy can reach it.
- [ ] `AUTH_*_GROUPS` map to your real IdP groups; a test user gets the expected role.
- [ ] TLS certificate is valid for the hostname.
- [ ] Audit export or DB logs are forwarded to a SIEM (the DB-backed audit log is
      mutable by database admins; see [Authentication](authentication.md)).

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Redirect loop at login | `OAUTH2_PROXY_REDIRECT_URL` or callback URL mismatch | Make both exactly `https://<host>/oauth2/callback` |
| 403 on every form submit | CSRF active but token missing | Confirm pages render through the proxy; do not call the app directly from a browser |
| User authenticates but every action is 403 | Groups not mapped to roles | Check the `AUTH_*_GROUPS` values match the provider's group strings (see Verify -> Audit for the actual groups received) |
| Identity ignored, user treated as anonymous | Missing `X-Huntable-Verified` marker or wrong header names | Use the supplied `nginx.conf`; do not change `AUTH_*_HEADER` without matching the proxy |
| Startup aborts in production | `AUTH_MODE=disabled`, wildcard hosts/CORS, or weak `SECRET_KEY` | Set real values; the fail-closed checks are intentional |

## See also

- [Authentication](authentication.md) - the identity, role, CSRF, and audit contract.
- `deploy/sso/README.md` - the proxy scaffold and file layout.
- `.env.example` - the full environment-variable reference.
