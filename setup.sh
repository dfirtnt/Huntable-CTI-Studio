#!/bin/bash

# =============================================================================
# CTI Scraper Interactive Setup Script
# =============================================================================
#
# This script provides an interactive guided setup for CTI Scraper, including:
#
# Features:
# - Interactive LLM configuration (LM Studio)
# - Secure password generation for PostgreSQL and Redis
# - API keys can be configured in .env file after setup
# - Automated backup setup
# - Health verification
#
# Usage:
#   ./setup.sh                    # Interactive guided setup
#   ./setup.sh --non-interactive  # Use default values
#   ./setup.sh --no-backups       # Skip backup configuration
#   ./setup.sh --backup-time 1:30 # Custom backup schedule
#
# =============================================================================

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/startup_common.sh
source "$SCRIPT_DIR/scripts/startup_common.sh"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
}

# Function to show usage
show_usage() {
    echo "Usage: $0 [options]"
    echo ""
    echo "Options:"
    echo "  --no-backups              Skip automated backup setup"
    echo "  --backup-time <time>       Backup time (HH:MM format, default: 2:00)"
    echo "  --non-interactive          Use default values without prompts"
    echo "  --help                    Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                        # Interactive guided setup"
    echo "  $0 --no-backups           # Quick setup without automated backups"
    echo "  $0 --non-interactive      # Use defaults without prompts"
    echo "  $0 --backup-time 1:30     # Quick setup with custom backup time"
}

# Function to prompt for yes/no input
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
            [Yy]* ) return 0 ;;
            [Nn]* ) return 1 ;;
            * ) echo -e "${YELLOW}Please answer yes or no.${NC}" ;;
        esac
    done
}

# Function to prompt for input with default
prompt_input() {
    local prompt="$1"
    local default="$2"
    local var_name="$3"
    local password_mode="${4:-false}"
    
    local input
    
    if [[ "$password_mode" == "true" ]]; then
        if [[ -n "$default" ]]; then
            read -sp "$prompt [default: *****]: " input
            echo
        else
            read -sp "$prompt: " input
            echo
        fi
    else
        read -p "$prompt " input
    fi
    
    eval "$var_name=\"${input:-$default}\""
}

# Function to generate secure random password
generate_password() {
    local length="${1:-32}"
    openssl rand -base64 $length | tr -d "=+/" | cut -c1-$length
}

# Function to prompt for LLM configuration
configure_llm() {
    print_header "LLM Configuration"
    
    echo -e "${CYAN}CTI Scraper supports multiple LLM options:${NC}"
    echo "  1. LM Studio - Desktop LLM manager (recommended for local)"
    echo "  2. OpenAI API - Cloud-based GPT models"
    echo "  3. Anthropic Claude API - Cloud-based Claude models"
    echo ""
    
    # Check if running on Intel Mac (LM Studio requires Apple Silicon)
    IS_INTEL_MAC=false
    if [[ "$(uname)" == "Darwin" ]]; then
        if [[ "$(uname -m)" == "x86_64" ]]; then
            IS_INTEL_MAC=true
        fi
    fi
    
    # Prompt for LM Studio
    if [[ "$IS_INTEL_MAC" == "true" ]]; then
        print_warning "LM Studio is not compatible with Intel-based Macs (requires Apple Silicon)"
        print_warning "Skipping LM Studio configuration. Use OpenAI or Anthropic APIs instead."
        USE_LMSTUDIO=false
    elif prompt_yes_no "Do you have LM Studio installed and want to use it for local LLM? (If you only want cloud providers #2 and #3, select No)" "no"; then
        USE_LMSTUDIO=true
        print_status "LM Studio will be enabled (ensure it's running on port 1234)"
        if [[ "$NON_INTERACTIVE" != "true" ]]; then
            echo -e "${CYAN}LM Studio server URL can change (e.g. different IP). You can set it now or leave blank.${NC}"
            prompt_input "LM Studio server URL (e.g. http://192.168.1.65:1234 or leave blank for default host.docker.internal:1234): " "" "LMSTUDIO_SERVER_URL" "false"
        else
            LMSTUDIO_SERVER_URL=""
        fi
    else
        USE_LMSTUDIO=false
        print_warning "LM Studio will be disabled"
    fi
    
    # Note: API keys can be added to .env file later
    OPENAI_API_KEY=""
    ANTHROPIC_API_KEY=""
    print_status "API keys can be configured later in the .env file if needed"
}

# Function to prompt for database passwords
configure_database() {
    print_header "Database Configuration"
    
    echo -e "${CYAN}Setting up database credentials...${NC}"
    
    # Check if .env exists
    if [[ -f ".env" ]]; then
        print_warning "⚠️  Existing .env file found with default passwords (not secure for production)"
        if ! prompt_yes_no ".env file exists. Overwrite it with new secure passwords?" "no"; then
            print_status "Using existing .env file"
            print_warning "⚠️  Remember to update passwords in .env file for production use"
            SKIP_ENV_CREATION=true
            return 0
        fi
    fi
    
    # PostgreSQL password
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        POSTGRES_PASSWORD=$(generate_password 24)
        print_status "Generated PostgreSQL password"
    else
        if prompt_yes_no "Generate a random PostgreSQL password?" "yes"; then
            POSTGRES_PASSWORD=$(generate_password 24)
            print_status "Generated PostgreSQL password"
        else
            prompt_input "Enter PostgreSQL password: " "" "POSTGRES_PASSWORD" "true"
        fi
    fi
    
    # Redis password
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        REDIS_PASSWORD=$(generate_password 24)
        print_status "Generated Redis password"
    else
        if prompt_yes_no "Generate a random Redis password?" "yes"; then
            REDIS_PASSWORD=$(generate_password 24)
            print_status "Generated Redis password"
        else
            prompt_input "Enter Redis password: " "" "REDIS_PASSWORD" "true"
        fi
    fi
    
    # Generate SECRET_KEY
    SECRET_KEY=$(generate_password 32)
    print_status "Generated application secret key"
}

# Function to create .env file from template
create_env_file() {
    print_header "Creating Environment Configuration"
    
    if [[ ! -f ".env.example" ]] && [[ ! -f "env.example" ]]; then
        print_error ".env.example or env.example not found!"
        return 1
    fi
    
    # Copy template (prefer .env.example, fallback to env.example)
    if [[ -f ".env.example" ]]; then
        cp .env.example .env
    else
        cp env.example .env
    fi
    
    # Replace passwords
    if [[ "$(uname)" == "Darwin" ]]; then
        # macOS
        sed -i '' "s|your_secure_postgres_password_change_this|$POSTGRES_PASSWORD|g" .env
        sed -i '' "s|your_secure_redis_password_change_this|$REDIS_PASSWORD|g" .env
        sed -i '' "s|your-super-secret-key-change-this-in-production|$SECRET_KEY|g" .env
        sed -i '' "s|your_openai_api_key_here|$OPENAI_API_KEY|g" .env
        sed -i '' "s|your_anthropic_api_key_here|$ANTHROPIC_API_KEY|g" .env
    else
        # Linux
        sed -i "s|your_secure_postgres_password_change_this|$POSTGRES_PASSWORD|g" .env
        sed -i "s|your_secure_redis_password_change_this|$REDIS_PASSWORD|g" .env
        sed -i "s|your-super-secret-key-change-this-in-production|$SECRET_KEY|g" .env
        sed -i "s|your_openai_api_key_here|$OPENAI_API_KEY|g" .env
        sed -i "s|your_anthropic_api_key_here|$ANTHROPIC_API_KEY|g" .env
    fi
    
    # Update LM Studio URLs based on LLM choice (and optional server URL)
    if [[ "$USE_LMSTUDIO" == "true" ]]; then
        local base_url
        if [[ -n "${LMSTUDIO_SERVER_URL:-}" ]]; then
            base_url="${LMSTUDIO_SERVER_URL%/}"
            [[ "$base_url" != *"/v1" ]] && base_url="${base_url}/v1"
        else
            base_url="http://host.docker.internal:1234/v1"
        fi
        local embed_url="${base_url%/v1}/v1/embeddings"
        startup_set_env_key ".env" "LMSTUDIO_API_URL" "${base_url}"
        startup_set_env_key ".env" "LMSTUDIO_EMBEDDING_URL" "${embed_url}"
    else
        # User chose not to use LMStudio: persist so Settings hides LMStudio UI
        startup_disable_lmstudio ".env"
    fi
    
    print_status ".env file created with your configuration"
}

# Function to check if we're in the right directory
check_directory() {
    startup_check_directory
}

# Function to check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"

    startup_check_prerequisites
    print_status "All prerequisites satisfied!"
}

# Function to setup environment
setup_environment() {
    print_header "Setting Up Environment"

    startup_ensure_runtime_directories

    # Set permissions
    chmod +x scripts/*.sh 2>/dev/null || true

    print_status "Environment setup complete!"
}

# Function to start services
start_services() {
    print_header "Starting Services"

    startup_apply_platform_compatibility ".env" "$NON_INTERACTIVE"
    startup_start_services

    # Enable pgvector extension in postgres for compatibility with existing setup flow.
    print_status "Enabling pgvector extension..."
    $DOCKER_CMD exec cti_postgres psql -U cti_user -d cti_scraper -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1 | grep -v "already exists" || true

    print_status "Services started successfully!"
}

# Function to setup automated backups
setup_automated_backups() {
    local backup_time=$1
    
    print_header "Setting Up Automated Backups"
    
    # Check if setup script exists
    if [ ! -f "scripts/setup_automated_backups.sh" ]; then
        print_error "Backup setup script not found!"
        return 1
    fi
    
    # Run backup setup
    print_status "Configuring automated daily backups at $backup_time..."
    ./scripts/setup_automated_backups.sh --backup-time "$backup_time"
    
    print_status "Automated backups configured successfully!"
}

# Recover from DB password mismatch between .env and existing Docker volume.
# This commonly happens after fresh clone/setup when old volumes still exist.
recover_from_postgres_password_mismatch() {
    print_warning "Detected PostgreSQL credential mismatch with existing Docker volume."

    local should_reset=false
    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        should_reset=true
    else
        if prompt_yes_no "Reset Docker volumes to reinitialize DB with current .env credentials?" "yes"; then
            should_reset=true
        fi
    fi

    if [[ "$should_reset" != "true" ]]; then
        print_error "Skipping volume reset; setup cannot make web service healthy with mismatched DB credentials."
        return 1
    fi

    print_warning "Resetting Docker volumes (this removes existing local DB/Redis data)..."
    $DOCKER_COMPOSE_CMD down -v

    print_status "Recreating services with fresh volumes..."
    $DOCKER_COMPOSE_CMD up -d

    print_status "Waiting for PostgreSQL to be ready after reset..."
    sleep 10
    for i in {1..60}; do
        if $DOCKER_CMD exec cti_postgres pg_isready -U cti_user -d cti_scraper >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done

    print_status "Enabling pgvector extension after reset..."
    $DOCKER_CMD exec cti_postgres psql -U cti_user -d cti_scraper -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1 | grep -v "already exists" || true

    print_status "Restarting application containers after reset..."
    $DOCKER_COMPOSE_CMD restart web worker scheduler
    sleep 15
}

# Function to verify installation
verify_installation() {
    print_header "Verifying Installation"

    local verification_failed=false

    if ! startup_verify_core_services; then
        # Auto-recover common first-run failure: DB auth mismatch from stale volumes
        if $DOCKER_CMD logs cti_web 2>&1 | grep -Eiq "InvalidPasswordError|password authentication failed for user"; then
            print_warning "Web startup failed due to PostgreSQL authentication mismatch."
            if recover_from_postgres_password_mismatch; then
                print_status "Re-checking service health after DB volume reset..."
                if ! startup_verify_core_services; then
                    verification_failed=true
                fi
            else
                verification_failed=true
            fi
        else
            verification_failed=true
        fi
    fi
    
    # Check worker containers for crash/restart loops
    print_status "Checking worker containers..."
    local worker_containers=("cti_worker" "cti_workflow_worker" "cti_scheduler")
    for container in "${worker_containers[@]}"; do
        local status=$($DOCKER_CMD inspect --format='{{.State.Status}}' "$container" 2>/dev/null)
        local restart_count=$($DOCKER_CMD inspect --format='{{.RestartCount}}' "$container" 2>/dev/null)
        
        if [[ "$status" == "running" ]]; then
            if [[ "$restart_count" -gt 5 ]]; then
                print_error "❌ $container is restarting repeatedly (restart count: $restart_count)"
                print_status "Check logs with: $DOCKER_CMD logs $container"
                verification_failed=true
            else
                print_status "✅ $container is running"
            fi
        elif [[ "$status" == "restarting" ]]; then
            print_error "❌ $container is in restart loop"
            print_status "Check logs with: $DOCKER_CMD logs $container"
            verification_failed=true
        elif [[ -z "$status" ]]; then
            print_warning "⚠️  $container not found (may not be started yet)"
        else
            print_warning "⚠️  $container status: $status"
        fi
    done
    
    if [ "$verification_failed" = true ]; then
        print_error "Installation verification failed. Some services are not healthy."
        return 1
    else
        print_status "Installation verification complete!"
        return 0
    fi
}

# Function to ensure Sigma rules repo exists for PR submission (../Huntable-SIGMA-Rules)
handle_sigma_repo_setup() {
    local sigma_repo_dir="../Huntable-SIGMA-Rules"
    local default_repo="your-username/Huntable-SIGMA-Rules"

    if [[ -d "$sigma_repo_dir" ]] && [[ -d "$sigma_repo_dir/.git" ]]; then
        print_status "Sigma rules repo already exists at $sigma_repo_dir"
        return 0
    fi

    if [[ "$NON_INTERACTIVE" == "true" ]]; then
        if [[ -n "${SIGMA_GITHUB_REPO:-}" ]]; then
            print_status "Cloning Sigma repo: $SIGMA_GITHUB_REPO"
            if git clone "https://github.com/${SIGMA_GITHUB_REPO}.git" "$sigma_repo_dir" 2>/dev/null; then
                print_status "✅ Sigma rules repo cloned"
            else
                print_warning "Sigma repo clone failed (create $sigma_repo_dir manually)"
            fi
        else
            print_warning "Skipping Sigma repo setup (set SIGMA_GITHUB_REPO to clone, or create $sigma_repo_dir manually)"
        fi
        return 0
    fi

    echo ""
    print_header "Sigma Rules Repo (PR Submission)"
    echo -e "${CYAN}The app submits approved SIGMA rules via GitHub PRs.${NC}"
    echo "Docker mounts ../Huntable-SIGMA-Rules at /app/sigma-repo."
    echo ""
    echo "If you don't have a repo yet: create one at https://github.com/new (e.g. Huntable-SIGMA-Rules)."
    echo ""
    if ! prompt_yes_no "Set up Sigma rules repo now?" "yes"; then
        print_warning "Skipping. Create $sigma_repo_dir and clone your repo manually. Configure Settings → GitHub."
        return 0
    fi

    echo ""
    echo "Enter your GitHub repo as owner/repo (e.g. dfirtnt/Huntable-SIGMA-Rules):"
    local repo_input=""
    prompt_input "GitHub repo [$default_repo]: " "$default_repo" "repo_input"
    repo_input="${repo_input:-$default_repo}"
    repo_input="${repo_input#https://github.com/}"
    repo_input="${repo_input%.git}"
    repo_input="${repo_input%/}"

    print_status "Cloning https://github.com/${repo_input}.git ..."
    if git clone "https://github.com/${repo_input}.git" "$sigma_repo_dir" 2>/dev/null; then
        print_status "✅ Sigma rules repo cloned"
    else
        print_warning "Clone failed (repo may not exist or be private). Creating local repo with rules structure..."
        mkdir -p "$sigma_repo_dir"
        (cd "$sigma_repo_dir" && git init && mkdir -p rules/windows rules/linux rules/macos rules/network rules/cloud)
        for d in windows linux macos network cloud; do
            touch "$sigma_repo_dir/rules/$d/.gitkeep"
        done
        (cd "$sigma_repo_dir" && git add rules/ && git commit -m "Add rules directory structure" 2>/dev/null || true)
        if [[ "$repo_input" != "your-username/Huntable-SIGMA-Rules" ]]; then
            (cd "$sigma_repo_dir" && git remote add origin "https://github.com/${repo_input}.git" 2>/dev/null || true)
            print_status "Created $sigma_repo_dir with rules structure. Create repo on GitHub, then: cd $sigma_repo_dir && git push -u origin main"
        else
            print_status "Created $sigma_repo_dir with rules structure. Create repo on GitHub, then: cd $sigma_repo_dir && git remote add origin https://github.com/YOUR_USER/Huntable-SIGMA-Rules.git && git push -u origin main"
        fi
    fi

    # Ensure rules structure exists
    if [[ -d "$sigma_repo_dir" ]] && [[ ! -d "$sigma_repo_dir/rules" ]]; then
        print_status "Adding rules directory structure..."
        mkdir -p "$sigma_repo_dir/rules"/{windows,linux,macos,network,cloud}
        for d in windows linux macos network cloud; do
            touch "$sigma_repo_dir/rules/$d/.gitkeep"
        done
        (cd "$sigma_repo_dir" && git add rules/ 2>/dev/null && git commit -m "Add rules directory structure" 2>/dev/null || true)
    fi

    # Update .env GITHUB_REPO if different from default
    if [[ -f ".env" ]] && [[ "$repo_input" != "$default_repo" ]]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|GITHUB_REPO=.*|GITHUB_REPO=$repo_input|g" .env
        else
            sed -i "s|GITHUB_REPO=.*|GITHUB_REPO=$repo_input|g" .env
        fi
        print_status "Updated .env GITHUB_REPO=$repo_input"
    fi
}

# Function to handle Sigma sync and index
handle_sigma_sync_and_index() {
    startup_sigma_sync_and_index
}

# Function to seed eval articles from static files into DB
seed_eval_articles() {
    startup_seed_eval_articles
}

# Build MkDocs site and start dev server so docs are ready and running
build_and_serve_mkdocs() {
    startup_build_and_serve_mkdocs
}

# Function to show post-installation information
show_post_install_info() {
    local setup_success=$1
    
    print_header "Setup Complete!"
    
    echo ""
    if [ "$setup_success" = true ]; then
        echo "🎉 CTI Scraper has been successfully set up!"
    else
        echo "⚠️  CTI Scraper setup completed with warnings/errors."
        echo "   Please review the verification output above and check container logs."
    fi
    echo ""
    echo "📋 Service Information:"
    echo "   • Web Interface: http://localhost:8001"
    echo "   • Docs: http://localhost:8000 (MkDocs; logs: logs/mkdocs.log)"
    echo "   • Database: PostgreSQL on port 5432"
    echo "   • Redis: Redis on port 6379"
    
    
    if [[ "$USE_LMSTUDIO" == "true" ]]; then
        echo "   • LM Studio: Connect to http://host.docker.internal:1234"
    fi
    
    echo "   • API Keys: Can be added to .env file later (OpenAI, Anthropic)"
    
    echo ""
    echo "🔧 Management Commands:"
    echo "   • Start services: docker-compose up -d"
    echo "   • Stop services: docker-compose down"
    echo "   • View logs: docker-compose logs -f"
    echo "   • Check status: docker-compose ps"
    echo ""
    
    echo "💾 Backup Commands:"
    echo "   • Create backup: ./scripts/backup_restore.sh create"
    echo "   • List backups: ./scripts/backup_restore.sh list"
    echo "   • Check backup status: ./scripts/setup_automated_backups.sh --status"
    echo ""
    echo "⚠️  Next Steps:"
    
    if [[ "$USE_LMSTUDIO" == "true" ]]; then
        echo "   1. Start LM Studio and load a model"
        echo "   2. Access web interface: http://localhost:8001"
    else
        echo "   1. Access web interface: http://localhost:8001"
    fi
    
    echo "   2. Configure API keys in .env file if needed (OpenAI, Anthropic)"
    echo "   3. Verify automated backups are working"
    echo "   4. Configure your sources in config/sources.yaml"
    if [[ -d "../Huntable-SIGMA-Rules" ]]; then
        echo "   5. Sigma PRs: Add your GitHub Personal Access Token (PAT) in Settings → GitHub"
        echo "      Create token at https://github.com/settings/tokens (repo scope required)"
    fi
    echo ""
}

# Main script logic
main() {
    # Default values
    local no_backups=false
    local backup_time="2:00"
    local help=false
    NON_INTERACTIVE=false

    # Initialize LLM configuration defaults
    USE_LMSTUDIO=false
    OPENAI_API_KEY=""
    ANTHROPIC_API_KEY=""

    # Initialize Sigma index skip flag (set based on environment compatibility)
    SKIP_SIGMA_INDEX=""
    
    # Parse command line arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-backups)
                no_backups=true
                shift
                ;;
            --backup-time)
                backup_time="$2"
                shift 2
                ;;
            --non-interactive)
                NON_INTERACTIVE=true
                shift
                ;;
            --help)
                help=true
                shift
                ;;
            *)
                print_error "Unknown option: $1"
                show_usage
                exit 1
                ;;
        esac
    done
    
    # Handle help
    if [ "$help" = true ]; then
        show_usage
        exit 0
    fi
    
    # Check directory
    check_directory
    
    # Start setup
    print_header "CTI Scraper Interactive Setup"
    
    # Check prerequisites
    check_prerequisites
    
    # Initialize SKIP_ENV_CREATION flag
    SKIP_ENV_CREATION=false
    
    # Interactive configuration (unless --non-interactive)
    if [[ "$NON_INTERACTIVE" == "false" ]]; then
        echo ""
        configure_llm
        echo ""
        configure_database
        echo ""
    else
        print_status "Running in non-interactive mode with defaults"
        POSTGRES_PASSWORD=$(generate_password 24)
        REDIS_PASSWORD=$(generate_password 24)
        SECRET_KEY=$(generate_password 32)
    fi
    
    # Create .env file from configuration (unless user chose to keep existing)
    if [[ "$SKIP_ENV_CREATION" != "true" ]]; then
        create_env_file
    fi
    
    # Setup environment
    setup_environment

    # Sigma rules repo for PR submission (must exist before Docker mount)
    handle_sigma_repo_setup
    
    # Start services
    start_services
    
    # Setup automated backups (unless disabled)
    if [ "$no_backups" = false ]; then
        setup_automated_backups "$backup_time"
    else
        print_warning "Skipping automated backup setup"
    fi
    
    # Refresh LLM provider model catalog so users see current models immediately (no 24h wait)
    startup_refresh_provider_model_catalog

    # Verify installation
    local setup_success=false
    if verify_installation; then
        setup_success=true

        # Align with start.sh startup path: validate pgvector index shape first.
        startup_migrate_pgvector_indexes

        # Prompt: embeddings now or later? (only when not already in limited-env mode)
        if [[ -z "$SKIP_SIGMA_INDEX" ]] && [[ "$NON_INTERACTIVE" != "true" ]]; then
            echo ""
            if ! prompt_yes_no "Generate Sigma rule embeddings now? (takes several minutes; you can run \"./run_cli.sh sigma index-embeddings\" later)" "yes"; then
                SKIP_SIGMA_INDEX=1
                print_status "Skipping embeddings. Run \"./run_cli.sh sigma index-embeddings\" when ready."
            fi
        fi

        # Handle Sigma sync and index
        echo ""
        handle_sigma_sync_and_index

        # Capability-driven warnings
        startup_show_capability_warnings

        # Seed eval articles
        echo ""
        seed_eval_articles

        # Build and serve MkDocs
        echo ""
        build_and_serve_mkdocs
    else
        setup_success=false
    fi
    
    # Show post-installation information
    show_post_install_info "$setup_success"
    
    # Exit with appropriate code
    if [ "$setup_success" = false ]; then
        exit 1
    fi
}

# Run main function
main "$@"
