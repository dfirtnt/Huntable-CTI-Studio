#!/bin/bash

# CTI Scraper Startup Script
# Daily startup wrapper; provisioning is handled by setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/startup_common.sh
source "$SCRIPT_DIR/scripts/startup_common.sh"

validate_env_for_startup() {
    local env_file="${1:-.env}"

    if [ ! -f "$env_file" ]; then
        echo "❌ No .env found. Run ./setup.sh first to provision a secure environment."
        return 1
    fi

    local postgres_password
    postgres_password="$(grep -E '^POSTGRES_PASSWORD=' "$env_file" | head -n1 | cut -d= -f2- || true)"
    if [ -z "$postgres_password" ]; then
        echo "❌ POSTGRES_PASSWORD is missing in .env. Run ./setup.sh to regenerate configuration."
        return 1
    fi
    if [ "$postgres_password" = "your_secure_postgres_password_change_this" ]; then
        echo "❌ POSTGRES_PASSWORD is still a template placeholder. Run ./setup.sh to provision secure credentials."
        return 1
    fi

    local openai_key anthropic_key secret_key
    openai_key="$(grep -E '^OPENAI_API_KEY=' "$env_file" | head -n1 | cut -d= -f2- || true)"
    anthropic_key="$(grep -E '^ANTHROPIC_API_KEY=' "$env_file" | head -n1 | cut -d= -f2- || true)"
    secret_key="$(grep -E '^SECRET_KEY=' "$env_file" | head -n1 | cut -d= -f2- || true)"

    if [ "$openai_key" = "your_openai_api_key_here" ]; then
        echo "❌ OPENAI_API_KEY is still a template placeholder in .env. Clear it or set a real key."
        return 1
    fi
    if [ "$anthropic_key" = "your_anthropic_api_key_here" ]; then
        echo "❌ ANTHROPIC_API_KEY is still a template placeholder in .env. Clear it or set a real key."
        return 1
    fi
    if [ "$secret_key" = "your-super-secret-key-change-this-in-production" ]; then
        echo "❌ SECRET_KEY is still a template placeholder in .env. Run ./setup.sh to regenerate secrets."
        return 1
    fi
}

main() {
    echo "🚀 Starting CTI Scraper..."

    # Check if setup.sh has been run and .env exists
    if [ ! -f "$SCRIPT_DIR/.setup_complete" ]; then
        echo "❌ Setup not complete. Please run ./setup.sh first."
        exit 1
    fi

    if [ ! -f ".env" ]; then
        echo "❌ .env not found. Please run ./setup.sh first."
        exit 1
    fi

    startup_check_directory
    startup_check_prerequisites
    validate_env_for_startup ".env"
    startup_apply_platform_compatibility ".env" "false"
    startup_ensure_runtime_directories
    startup_start_services
    startup_verify_core_services
    startup_migrate_pgvector_indexes
    startup_sigma_sync_and_index
    startup_show_capability_warnings
    startup_seed_eval_articles
    startup_refresh_provider_model_catalog
    startup_build_and_serve_mkdocs
    startup_show_running_stack_summary
}

main "$@"
