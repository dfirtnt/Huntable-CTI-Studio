# Local Entra ID login gate

Require a Microsoft (Entra ID) login to reach the app, on `localhost`, with no
domain and no TLS. This is the simplest SSO test: oauth2-proxy authenticates the
user and proxies to the running app. The app is unchanged and has no per-user
roles behind the gate (everyone who logs in gets the app's default access). For
role mapping, use the full scaffold in the parent directory plus the
[Enterprise SSO guide](../../../docs/guides/enterprise-sso.md).

It attaches to the running app's Docker network and proxies to the `cti_web`
container, so you do **not** need to deploy the `enterprise-auth-audit` branch
to try this.

## 1. Register the app in Entra

Azure portal -> **Microsoft Entra ID -> App registrations -> New registration**:

- Account types: single tenant (your dev directory).
- Redirect URI: platform **Web**, `http://localhost:4180/oauth2/callback`.
- After registering, copy the **Application (client) ID** and **Directory (tenant) ID**.
- **Certificates & secrets -> New client secret** -> copy the secret **Value**.

(No API permissions or group claims are needed for a login gate.)

## 2. Configure oauth2-proxy

```bash
cd deploy/sso/local
cp oauth2-proxy.env.example oauth2-proxy.env
```

Edit `oauth2-proxy.env`:

- Put the tenant ID into `OAUTH2_PROXY_OIDC_ISSUER_URL` (replace `__TENANT_ID__`).
- Set `OAUTH2_PROXY_CLIENT_ID` and `OAUTH2_PROXY_CLIENT_SECRET`.
- Generate `OAUTH2_PROXY_COOKIE_SECRET`:
  ```bash
  python3 -c "import secrets,base64; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
  ```

## 3. Start the gate

```bash
docker compose -f docker-compose.entra-gate.yml up -d
```

Open `http://localhost:4180`. You are redirected to Microsoft, sign in, and land
on the app. The app is still directly reachable at `http://localhost:8001` (the
gate does not block that) -- that is fine for a test; close the port when you
move to a real deployment.

## 4. Tear down

```bash
docker compose -f docker-compose.entra-gate.yml down
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| Redirect URI mismatch error from Microsoft | The Entra redirect URI must be exactly `http://localhost:4180/oauth2/callback` |
| Login succeeds but oauth2-proxy returns 403 / "no email" | Entra v2 tokens may omit `email`; set `OAUTH2_PROXY_OIDC_EMAIL_CLAIM=preferred_username` (and `OAUTH2_PROXY_INSECURE_OIDC_ALLOW_UNVERIFIED_EMAIL=true`) in `oauth2-proxy.env` |
| oauth2-proxy can't reach the app | Confirm the app is running and on `huntable-cti-studio_cti_network` (`docker inspect cti_web`); the proxy upstream is `http://cti_web:8001` |
| Cookie/login loop | Ensure `OAUTH2_PROXY_COOKIE_SECURE=false` (set in the compose file) since this is plain http |

## Next: roles (RBAC)

A login gate does not give per-user roles. For that, the app must run the
`enterprise-auth-audit` code in `trusted_header` mode behind a proxy that injects
the verified-identity marker, and Entra must emit a groups claim mapped to the
`AUTH_*_GROUPS` env vars. See the [Enterprise SSO guide](../../../docs/guides/enterprise-sso.md).
