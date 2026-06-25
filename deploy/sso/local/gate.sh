#!/bin/bash
# =============================================================================
# gate.sh -- toggle the local Entra login gate and block/restore direct :8001.
#
#   gate.sh up       Require Entra login for ALL access (close direct :8001)
#   gate.sh down     Stop requiring login (restore direct :8001)
#   gate.sh status   Show the live posture (read-only)
#
# This is the local "force everyone to log in with Entra" switch. It is a LOGIN
# GATE: it authenticates but does NOT authorize -- every user who completes an
# Entra-tenant login lands with the app's default (admin) access. For per-user
# roles, move to the trusted-header RBAC scaffold (see ../README.md and
# ../../../docs/guides/enterprise-sso.md).
#
# Design notes (why it is shaped this way):
#  * Self-locating: it reads the deployed compose project, working dir, and the
#    EXACT compose file set from the RUNNING cti_web container labels, so every
#    `docker compose` call targets the real app stack no matter which checkout
#    this script is launched from. container_name cti_web is unique, so the
#    lookup is unambiguous.
#  * Lockout-safe: the gate is started and an interactive login is confirmed
#    BEFORE the port is dropped; after the drop the app must come back healthy
#    AND the gate must respond or the port is auto-restored; `down` restores the
#    port before stopping the gate; a manual reopen escape hatch is printed.
#  * No false security: "closed/gated" is only ever reported when cti_web is
#    actually running and the host port is genuinely absent -- a stopped or
#    booting container is never mislabeled as gated.
#  * No stored state: posture is the live container/overlay reality, not a marker.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GATE_COMPOSE="$SCRIPT_DIR/docker-compose.entra-gate.yml"
ISOLATE_OVERLAY="$SCRIPT_DIR/docker-compose.entra-isolate.yml"
CRED_FILE="$SCRIPT_DIR/oauth2-proxy.env"
APP_CONTAINER="cti_web"
GATE_CONTAINER="cti_oauth2_local"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()  { echo -e "${CYAN}[gate]${NC} $1"; }
ok()    { echo -e "${GREEN}[gate]${NC} $1"; }
warn()  { echo -e "${YELLOW}[gate]${NC} $1"; }
fail()  { echo -e "${RED}[gate]${NC} $1" >&2; exit 1; }

# ----- self-location from the running app container --------------------------
PROJ=""; WORKDIR=""; APP_COMPOSE_FILES=()
resolve_app() {
    PROJ="$(docker inspect "$APP_CONTAINER" --format '{{ index .Config.Labels "com.docker.compose.project" }}' 2>/dev/null || true)"
    WORKDIR="$(docker inspect "$APP_CONTAINER" --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}' 2>/dev/null || true)"
    if [[ -z "$PROJ" || -z "$WORKDIR" ]]; then
        fail "No '$APP_CONTAINER' container found. Start the app first (docker compose up -d)."
    fi
    # Use the EXACT compose file set the stack was brought up with, not an assumed name.
    local cfg
    cfg="$(docker inspect "$APP_CONTAINER" --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}' 2>/dev/null || true)"
    APP_COMPOSE_FILES=()
    if [[ -n "$cfg" ]]; then
        local f; local -a parts
        IFS=',' read -ra parts <<< "$cfg"
        for f in "${parts[@]}"; do
            [[ -n "$f" ]] && APP_COMPOSE_FILES+=( -f "$f" )
        done
    fi
    if [[ ${#APP_COMPOSE_FILES[@]} -eq 0 ]]; then
        [[ -f "$WORKDIR/docker-compose.yml" ]] || fail "Deployed compose file not found: $WORKDIR/docker-compose.yml"
        APP_COMPOSE_FILES=( -f "$WORKDIR/docker-compose.yml" )
    fi
}

# Compose invocation pinned to the deployed app stack (never relies on cwd).
# Guard the array expansion: bash 3.2 (macOS /bin/bash) treats an empty "${a[@]}"
# under `set -u` as a fatal unbound-variable error. resolve_app always fills it
# first; this turns a broken call order into a clear message, not a crash.
app_compose() {
    [[ ${#APP_COMPOSE_FILES[@]} -gt 0 ]] || fail "internal error: resolve_app did not run before app_compose"
    docker compose --project-directory "$WORKDIR" -p "$PROJ" "${APP_COMPOSE_FILES[@]}" "$@"
}

# ----- predicates (all read-only) -------------------------------------------
web_running() { [[ "$(docker inspect "$APP_CONTAINER" --format '{{.State.Status}}' 2>/dev/null || true)" == "running" ]]; }
web_healthy() {
    local s
    s="$(docker inspect "$APP_CONTAINER" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' 2>/dev/null || true)"
    [[ "$s" == "healthy" || "$s" == "running" ]]
}
# True when cti_web has at least one host port binding ("HostPort" only appears
# for a published port). Authoritative ONLY when the container is running.
web_has_host_port() {
    docker inspect "$APP_CONTAINER" --format '{{json .NetworkSettings.Ports}}' 2>/dev/null | grep -q '"HostPort"'
}
web_8001_reachable() {
    curl -sS --max-time 3 -o /dev/null "http://127.0.0.1:8001/" >/dev/null 2>&1 \
        || curl -sS --max-time 3 -o /dev/null "http://[::1]:8001/" >/dev/null 2>&1
}
gate_running()  { [[ "$(docker inspect "$GATE_CONTAINER" --format '{{.State.Status}}' 2>/dev/null || true)" == "running" ]]; }
gate_responds() { [[ "$(curl -sS -o /dev/null -w '%{http_code}' --max-time 5 "http://127.0.0.1:4180/" 2>/dev/null || true)" =~ ^30 ]]; }

preflight_creds() {
    [[ -f "$CRED_FILE" ]] || fail "Missing $CRED_FILE. Copy oauth2-proxy.env.example, fill it, then retry (see README.md)."
    local k v
    for k in OAUTH2_PROXY_CLIENT_ID OAUTH2_PROXY_CLIENT_SECRET OAUTH2_PROXY_COOKIE_SECRET OAUTH2_PROXY_OIDC_ISSUER_URL; do
        # awk: first matching key, value after the first '=', then stop. No pipe to
        # head (avoids a SIGPIPE/pipefail abort); portable to BSD/macOS awk.
        v="$(awk -F= -v k="$k" '$1==k{sub(/^[^=]*=/,""); print; exit}' "$CRED_FILE")"
        [[ -n "$v" ]] || fail "$k is empty in $CRED_FILE."
        case "$v" in
            *__TENANT_ID__*|*"<"*|*">"*) fail "$k still holds a placeholder in $CRED_FILE." ;;
        esac
    done
}

# Gate lifecycle. Start declaratively via compose (run from SCRIPT_DIR so the
# relative env_file in the gate compose resolves). Stop by the unique container
# name so teardown works regardless of which project the gate was started under.
gate_start() { ( cd "$SCRIPT_DIR" && docker compose -f "$GATE_COMPOSE" up -d ); }
gate_stop()  { docker rm -f "$GATE_CONTAINER" >/dev/null 2>&1 || true; }

print_reopen_hatch() {
    warn "If the gate ever fails while engaged, force-reopen direct access with:"
    echo  "    docker compose --project-directory \"$WORKDIR\" -p \"$PROJ\" ${APP_COMPOSE_FILES[*]} up -d --no-deps web"
}
print_authn_only_note() {
    warn "Note: this is a LOGIN GATE (authentication only). Every Entra user who logs in"
    warn "gets the app's default admin access; there are no per-user roles yet (that is RBAC)."
}

# ----- commands -------------------------------------------------------------
cmd_up() {
    resolve_app
    if web_running && ! web_has_host_port; then
        if gate_running; then
            ok "Already gated: '$APP_CONTAINER' has no host port and the gate is running."
            info "Entry point: http://localhost:4180"
            return 0
        fi
        warn "'$APP_CONTAINER' has no host port but the gate is NOT running -- reopening for safety."
        app_compose up -d --no-deps web
    elif ! web_running; then
        warn "'$APP_CONTAINER' is not running -- starting it (with its host port) before gating."
        app_compose up -d --no-deps web
    fi

    preflight_creds

    info "Starting the Entra login gate..."
    gate_start
    local i
    for i in $(seq 1 15); do
        if gate_responds; then break; fi
        sleep 1
    done
    gate_responds || fail "Gate did not respond on :4180 (check 'docker logs $GATE_CONTAINER'). Direct :8001 left OPEN."

    echo ""
    echo "  The gate is up. BEFORE direct :8001 is closed, confirm a real login works:"
    echo "    1. Open  http://localhost:4180"
    echo "    2. Complete the Microsoft (Entra) sign-in and confirm the app loads."
    echo "  (A 302 only proves the proxy booted; only a real login proves your creds and"
    echo "   redirect URI are correct. This step is what prevents locking yourself out.)"
    echo ""
    local ans=""
    read -r -p "  Did the Entra login succeed and the app load? Type 'yes' to close :8001: " ans || true
    if [[ "$ans" != "yes" ]]; then
        warn "Not confirmed. Leaving :8001 OPEN and the gate running. Re-run 'up' once login works."
        return 1
    fi

    info "Closing direct access to '$APP_CONTAINER' (recreating container; brief blip)..."
    app_compose -f "$ISOLATE_OVERLAY" up -d --no-deps web

    # Fail closed: if the port did not actually drop, revert and abort.
    sleep 1
    if web_has_host_port || web_8001_reachable; then
        warn "Isolation did NOT engage -- :8001 still reachable. Reverting."
        app_compose up -d --no-deps web
        print_reopen_hatch
        fail "Reverted: direct :8001 is back OPEN. Investigate before retrying."
    fi

    # Lockout guard: the port is gone, so there MUST be a working way in. Require the
    # app to come back healthy AND the gate to respond; a bare proxy 302 is not enough
    # (SKIP_PROVIDER_BUTTON returns 302 even with the upstream down). If neither holds
    # within the window, reopen the port and abort -- never claim success with no path.
    local healthy=1
    for i in $(seq 1 30); do
        if web_healthy && gate_responds; then healthy=0; break; fi
        sleep 2
    done
    if [[ $healthy -ne 0 ]]; then
        warn "After closing :8001 the app did not come back reachable through the gate (~60s)."
        app_compose up -d --no-deps web
        print_reopen_hatch
        fail "Reverted: direct :8001 is OPEN again. Fix the gate/app and retry."
    fi

    ok "Entra gate ENGAGED. Direct :8001 is closed; the only way in is http://localhost:4180."
    print_authn_only_note
    print_reopen_hatch
}

cmd_down() {
    resolve_app
    info "Reopening direct access to '$APP_CONTAINER' (recreating container; brief blip)..."
    app_compose up -d --no-deps web
    sleep 1
    if ! web_has_host_port; then
        warn "Reopen did not restore a host port. Try manually:"
        echo  "    docker compose --project-directory \"$WORKDIR\" -p \"$PROJ\" ${APP_COMPOSE_FILES[*]} up -d --no-deps web"
        if gate_running; then
            warn "The gate is still running, so you can still reach the app via http://localhost:4180."
        fi
        fail "Direct :8001 is still closed."
    fi
    if gate_running; then
        info "Stopping the Entra login gate..."
        gate_stop
        if gate_running; then
            warn "Gate container still present; remove manually: docker rm -f $GATE_CONTAINER"
        fi
    fi
    ok "Entra gate DISENGAGED. Direct access restored: http://localhost:8001"
}

cmd_status() {
    resolve_app
    local app_state
    app_state="$(docker inspect "$APP_CONTAINER" --format '{{.State.Status}}' 2>/dev/null || echo absent)"
    echo "Entra login gate status (project: $PROJ)"
    echo "  app state      : $app_state"

    if [[ "$app_state" != "running" ]]; then
        echo "  direct :8001   : UNKNOWN (app not running; a normal restart republishes the port)"
    elif web_has_host_port; then
        echo "  direct :8001   : OPEN (host port published)"
    else
        echo "  direct :8001   : CLOSED (no host port)"
    fi

    if gate_running; then
        if gate_responds; then echo "  gate (:4180)   : running, responds"; else echo "  gate (:4180)   : running, NOT responding"; fi
    else
        echo "  gate (:4180)   : stopped"
    fi

    if [[ "$app_state" != "running" ]]; then
        echo "  posture        : APP DOWN -- not gated; a restart will reopen :8001"
    elif ! web_has_host_port && gate_running; then
        echo "  posture        : GATED (login required)"
    elif web_has_host_port && ! gate_running; then
        echo "  posture        : OPEN (no login required)"
    else
        echo "  posture        : MIXED -- run 'up' or 'down' to reconcile"
    fi

    local strays dups
    strays="$(docker network ls --format '{{.Name}}' | grep '_cti_network$' | grep -vx 'huntable-cti-studio_cti_network' || true)"
    if [[ -n "$strays" ]]; then
        warn "stray cti networks from old worktree projects (safe to prune if unused):"
        echo "$strays" | sed 's/^/      - /'
    fi
    dups="$(docker ps -a --filter 'name=cti_web' --format '{{.Names}}' | grep -vx 'cti_web' || true)"
    if [[ -n "$dups" ]]; then
        warn "extra cti_web-like containers present: $dups"
    fi
    return 0
}

usage() {
    cat <<EOF
gate.sh -- force everyone to log in with Entra (toggle direct :8001)

Usage: $(basename "$0") <up|down|status>

  up       Require an Entra login for all access (closes direct :8001).
           Starts the gate, makes you confirm a real login, then closes the port.
  down     Stop requiring login (restores direct :8001) and stops the gate.
  status   Show the live posture (read-only).

This is a login gate (authentication only, no per-user roles). For RBAC, see
../../../docs/guides/enterprise-sso.md.
EOF
}

main() {
    local cmd="${1:-}"
    case "$cmd" in
        up)     cmd_up ;;
        down)   cmd_down ;;
        status) cmd_status ;;
        ""|-h|--help|help) usage ;;
        *) echo "Unknown command: $cmd" >&2; echo "" >&2; usage >&2; exit 1 ;;
    esac
}

main "$@"
