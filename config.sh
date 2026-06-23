#!/bin/bash
# =============================================================================
# config.sh -- change Huntable CTI Studio app/auth configuration WITHOUT
# re-running the full installer (setup.sh).
#
# Edits .env idempotently. NEVER regenerates passwords, resets DB volumes, or
# runs docker compose. Apply changes with a container restart (printed after
# each command). For the initial install, use ./setup.sh.
#
# Usage:
#   ./config.sh sso              Configure enterprise SSO + scaffold deploy/sso
#   ./config.sh sso --disable    Turn SSO off (AUTH_MODE=disabled)
#   ./config.sh rotate-secret    Generate a new SECRET_KEY
#   ./config.sh set KEY VALUE    Set any .env key (idempotent)
#   ./config.sh show             Print current auth config (SECRET_KEY redacted)
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" # operate on the repo-root .env and deploy/sso

ENV_FILE=".env"

# Colors / logging (standalone; mirrors setup.sh).
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_status() { echo -e "${GREEN}[INFO]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
}

generate_password() {
    local length="${1:-32}"
    openssl rand -base64 "$length" | tr -d "=+/" | cut -c1-"$length"
}

prompt_yes_no() {
    local prompt="$1"
    local default="${2:-no}"
    local answer
    while true; do
        if [[ "$default" == "yes" ]]; then
            read -p "$prompt [Y/n]: " answer
            answer=${answer:-Y}
        else
            read -p "$prompt [y/N]: " answer
            answer=${answer:-N}
        fi
        case ${answer:0:1} in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
            *) echo -e "${YELLOW}Please answer yes or no.${NC}" ;;
        esac
    done
}

prompt_input() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local input
    read -p "$prompt " input
    eval "$var_name=\"${input:-$default}\""
}

# config.sh is always interactive; the SSO flow must prompt.
NON_INTERACTIVE=false

# shellcheck source=scripts/startup_common.sh
source "$SCRIPT_DIR/scripts/startup_common.sh"   # startup_set_env_key
# shellcheck source=scripts/configure_auth.sh
source "$SCRIPT_DIR/scripts/configure_auth.sh"   # apply_enterprise_sso_config, scaffold_sso_proxy

require_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        print_error "$ENV_FILE not found. Run ./setup.sh first."
        exit 1
    fi
}

restart_reminder() {
    print_warning "Config is read at process start. Apply changes with a restart:"
    print_warning "  docker restart cti_web cti_worker cti_workflow_worker cti_scheduler"
}

cmd_sso() {
    require_env
    if [[ "${1:-}" == "--disable" ]]; then
        startup_set_env_key "$ENV_FILE" "AUTH_MODE" "disabled"
        print_status "AUTH_MODE=disabled (enterprise SSO off; local mode)."
        restart_reminder
        return 0
    fi
    print_header "Configure Enterprise SSO"
    apply_enterprise_sso_config "$ENV_FILE"
    restart_reminder
}

cmd_rotate_secret() {
    require_env
    startup_set_env_key "$ENV_FILE" "SECRET_KEY" "$(generate_password 48)"
    print_status "Rotated SECRET_KEY."
    print_warning "This invalidates issued CSRF tokens; open browser sessions must reload the page."
    restart_reminder
}

cmd_set() {
    require_env
    local key="${1:-}"
    local value="${2:-}"
    if [[ -z "$key" ]]; then
        print_error "usage: ./config.sh set KEY VALUE"
        exit 1
    fi
    startup_set_env_key "$ENV_FILE" "$key" "$value"
    print_status "Set ${key}."
    restart_reminder
}

cmd_show() {
    require_env
    print_header "Auth configuration ($ENV_FILE)"
    local keys=(
        APP_ENV AUTH_MODE CSRF_ENABLED SECRET_KEY
        TRUSTED_HOSTS CORS_ALLOWED_ORIGINS
        AUTH_TRUSTED_PROXY_HEADER AUTH_TRUSTED_PROXY_VALUE AUTH_TRUSTED_PROXY_IPS
        AUTH_ADMIN_GROUPS AUTH_OPERATOR_GROUPS AUTH_REVIEWER_GROUPS AUTH_ANALYST_GROUPS
        AUDIT_RETENTION_DAYS
    )
    local k v
    for k in "${keys[@]}"; do
        v=$(grep -E "^${k}=" "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- || true)
        if [[ "$k" == "SECRET_KEY" ]]; then
            if [[ -n "$v" ]]; then v="<set, ${#v} chars>"; else v="<empty>"; fi
        fi
        printf '  %-28s %s\n' "$k" "${v:-<unset>}"
    done
}

usage() {
    cat <<'EOF'
config.sh -- change app/auth config without re-running setup.sh

Usage: ./config.sh <command> [args]

Commands:
  sso                 Configure enterprise SSO (trusted-header proxy) + scaffold deploy/sso
  sso --disable       Turn SSO off (AUTH_MODE=disabled)
  rotate-secret       Generate a new SECRET_KEY
  set KEY VALUE       Set any .env key (idempotent)
  show                Print current auth config (SECRET_KEY redacted)

Changes never touch passwords, DB volumes, or run docker compose. Apply with a
restart: docker restart cti_web cti_worker cti_workflow_worker cti_scheduler
For the initial install, use ./setup.sh.
EOF
}

main() {
    local cmd="${1:-}"
    shift || true
    case "$cmd" in
        sso) cmd_sso "$@" ;;
        rotate-secret) cmd_rotate_secret ;;
        set) cmd_set "$@" ;;
        show) cmd_show ;;
        "" | -h | --help | help) usage ;;
        *)
            print_error "Unknown command: $cmd"
            echo ""
            usage
            exit 1
            ;;
    esac
}

main "$@"
