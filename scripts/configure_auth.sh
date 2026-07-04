#!/usr/bin/env bash
# Enterprise SSO configuration helpers shared by setup.sh and config.sh.
#
# The sourcing script must provide these helpers (both setup.sh and config.sh do):
#   print_header, print_status, print_warning   -- logging
#   prompt_yes_no, prompt_input                 -- interactive input
#   startup_set_env_key                         -- from scripts/startup_common.sh
#
# All file operations are relative to the current working directory (the repo root).

# Generate the active nginx + oauth2-proxy configs from the committed templates.
scaffold_sso_proxy() {
    local hostname="$1"
    local provider="$2"
    local dir="deploy/sso"

    if [[ ! -f "$dir/nginx.conf.template" ]] || [[ ! -f "$dir/oauth2-proxy.env.example" ]]; then
        print_warning "deploy/sso templates not found; skipping reverse-proxy scaffold."
        return 0
    fi
    mkdir -p "$dir/tls"

    if [[ -f "$dir/nginx.conf" ]]; then
        print_status "deploy/sso/nginx.conf already exists; leaving it unchanged."
    else
        sed "s|__SSO_HOSTNAME__|${hostname}|g" "$dir/nginx.conf.template" >"$dir/nginx.conf"
        print_status "Wrote deploy/sso/nginx.conf (host ${hostname})."
    fi

    if [[ -f "$dir/oauth2-proxy.env" ]]; then
        print_status "deploy/sso/oauth2-proxy.env already exists; leaving credentials unchanged."
    else
        sed -e "s|__SSO_PROVIDER__|${provider}|g" -e "s|__SSO_HOSTNAME__|${hostname}|g" \
            "$dir/oauth2-proxy.env.example" >"$dir/oauth2-proxy.env"
        # Prefill a url-safe cookie secret so only the OAuth client id/secret remain to fill in.
        local cookie_secret
        cookie_secret=$(openssl rand -base64 32 | tr '+/' '-_' | tr -d '=')
        startup_set_env_key "$dir/oauth2-proxy.env" "OAUTH2_PROXY_COOKIE_SECRET" "$cookie_secret"
        print_status "Wrote deploy/sso/oauth2-proxy.env (provider ${provider}, cookie secret generated)."
    fi
}

# Prompt for SSO settings, write them to the env file, and scaffold the proxy.
# Caller has already decided SSO should be enabled.
apply_enterprise_sso_config() {
    local env_file="${1:-.env}"
    local hostname provider admin_g operator_g reviewer_g analyst_g

    prompt_input "Public hostname users browse to (e.g. cti.example.com):" "cti.example.com" "hostname"
    prompt_input "OAuth provider [github | google | oidc]:" "github" "provider"
    print_status "Map IdP groups to app roles (blank = skip; GitHub teams look like 'org:team')."
    prompt_input "  Group -> ADMIN:" "" "admin_g"
    prompt_input "  Group -> OPERATOR:" "" "operator_g"
    prompt_input "  Group -> RULE_REVIEWER:" "" "reviewer_g"
    prompt_input "  Group -> ANALYST:" "" "analyst_g"

    local make_prod="false"
    if prompt_yes_no "Apply production hardening (APP_ENV=production, fail-closed startup checks)?" "yes"; then
        make_prod="true"
    fi

    # App-side trusted-header configuration.
    startup_set_env_key "$env_file" "AUTH_MODE" "trusted_header"
    startup_set_env_key "$env_file" "CSRF_ENABLED" "auto"
    startup_set_env_key "$env_file" "TRUSTED_HOSTS" "$hostname"
    startup_set_env_key "$env_file" "CORS_ALLOWED_ORIGINS" "https://$hostname"
    startup_set_env_key "$env_file" "AUTH_TRUSTED_PROXY_HEADER" "X-Huntable-Verified"
    startup_set_env_key "$env_file" "AUTH_TRUSTED_PROXY_VALUE" "true"
    [[ -n "$admin_g" ]] && startup_set_env_key "$env_file" "AUTH_ADMIN_GROUPS" "$admin_g"
    [[ -n "$operator_g" ]] && startup_set_env_key "$env_file" "AUTH_OPERATOR_GROUPS" "$operator_g"
    [[ -n "$reviewer_g" ]] && startup_set_env_key "$env_file" "AUTH_REVIEWER_GROUPS" "$reviewer_g"
    [[ -n "$analyst_g" ]] && startup_set_env_key "$env_file" "AUTH_ANALYST_GROUPS" "$analyst_g"
    [[ "$make_prod" == "true" ]] && startup_set_env_key "$env_file" "APP_ENV" "production"

    scaffold_sso_proxy "$hostname" "$provider"

    print_status "Enterprise SSO configured (AUTH_MODE=trusted_header)."
    print_warning "Finish SSO setup (see deploy/sso/README.md):"
    print_warning "  1. Fill OAuth client id/secret in deploy/sso/oauth2-proxy.env"
    print_warning "  2. Add a TLS cert at deploy/sso/tls/{fullchain,privkey}.pem"
    print_warning "  3. Remove the web 'ports: 8001:8001' mapping in docker-compose.yml (block direct access)"
    print_warning "  4. docker compose -f docker-compose.yml -f deploy/sso/docker-compose.sso.yml up -d"
}

# setup.sh entry point: opt-in gate, then apply. Non-interactive installs stay local.
configure_enterprise_auth() {
    local env_file="${1:-.env}"

    if [[ "${NON_INTERACTIVE:-false}" == "true" ]]; then
        startup_set_env_key "$env_file" "AUTH_MODE" "disabled"
        return 0
    fi

    print_header "Enterprise SSO (optional)"
    print_status "Leave off for local/dev use (AUTH_MODE=disabled, no login required)."
    print_status "Enable to run behind an OAuth reverse proxy (Google / GitHub / Microsoft)."
    if ! prompt_yes_no "Enable enterprise SSO via a trusted-header reverse proxy?" "no"; then
        startup_set_env_key "$env_file" "AUTH_MODE" "disabled"
        print_status "Enterprise SSO disabled (local mode)."
        return 0
    fi

    apply_enterprise_sso_config "$env_file"
}
