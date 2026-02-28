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
    elif prompt_yes_no "Do you want to use LM Studio for local LLM?" "no"; then
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
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' "s|LMSTUDIO_API_URL=.*|LMSTUDIO_API_URL=${base_url}|g" .env
            sed -i '' "s|LMSTUDIO_EMBEDDING_URL=.*|LMSTUDIO_EMBEDDING_URL=${embed_url}|g" .env
        else
            sed -i "s|LMSTUDIO_API_URL=.*|LMSTUDIO_API_URL=${base_url}|g" .env
            sed -i "s|LMSTUDIO_EMBEDDING_URL=.*|LMSTUDIO_EMBEDDING_URL=${embed_url}|g" .env
        fi
    fi
    
    print_status ".env file created with your configuration"
}

# Function to check if we're in the right directory
check_directory() {
    if [ ! -f "docker-compose.yml" ]; then
        print_error "Please run this script from the CTI Scraper root directory"
        exit 1
    fi
}

# Function to check prerequisites
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    # Check Docker - try PATH first, then common macOS Docker Desktop locations
    DOCKER_CMD=""
    if command -v docker &> /dev/null; then
        DOCKER_CMD="docker"
    elif [ -f "/Applications/Docker.app/Contents/Resources/bin/docker" ]; then
        DOCKER_CMD="/Applications/Docker.app/Contents/Resources/bin/docker"
        export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
        print_status "Found Docker at /Applications/Docker.app/Contents/Resources/bin/docker"
    else
        print_error "Docker executable not found in PATH."
        print_error "Please ensure Docker Desktop is installed and the Docker executable is in your PATH."
        print_error "Verify Docker is accessible by running: docker --version"
        exit 1
    fi
    
    # Check Docker Compose (support both v1 and v2)
    if command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE_CMD="docker-compose"
    elif $DOCKER_CMD compose version &> /dev/null; then
        DOCKER_COMPOSE_CMD="$DOCKER_CMD compose"
    else
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if Docker is running
    if ! $DOCKER_CMD info &> /dev/null; then
        print_error "Docker is not running. Please start Docker Desktop first."
        exit 1
    fi
    
    print_status "All prerequisites satisfied!"
}

# Function to setup environment
setup_environment() {
    print_header "Setting Up Environment"
    
    # Create necessary directories
    print_status "Creating necessary directories"
    mkdir -p logs backups models outputs
    
    # Set permissions
    chmod +x scripts/*.sh 2>/dev/null || true
    chmod +x scripts/*.py 2>/dev/null || true
    
    print_status "Environment setup complete!"
}

# Function to start services
start_services() {
    print_header "Starting Services"
    
    # Load environment variables from .env file
    if [ -f ".env" ]; then
        print_status "Loading environment variables from .env file..."
        # Export variables line by line, skipping comments and problematic lines
        while IFS= read -r line || [ -n "$line" ]; do
            # Skip comments and empty lines
            [[ "$line" =~ ^#.*$ ]] && continue
            [[ -z "$line" ]] && continue
            
            # Skip lines with complex data structures
            [[ "$line" =~ CORS_ORIGINS= ]] && continue
            [[ "$line" =~ TRUSTED_HOSTS= ]] && continue
            [[ "$line" =~ BACKUP_SCHEDULE= ]] && continue
            [[ "$line" =~ DATABASE_URL= ]] && continue
            [[ "$line" =~ REDIS_URL= ]] && continue
            
            # Export the variable
            export "$line"
        done < .env
    fi
    
    # Build and start Docker services
    print_status "Building Docker images..."
    $DOCKER_COMPOSE_CMD build
    
    # Start services
    print_status "Starting services..."
    $DOCKER_COMPOSE_CMD up -d
    
    # Wait for postgres to be healthy
    print_status "Waiting for PostgreSQL to be ready..."
    sleep 10
    for i in {1..30}; do
        if $DOCKER_CMD exec cti_postgres pg_isready -U cti_user -d cti_scraper >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # Enable pgvector extension in postgres
    print_status "Enabling pgvector extension..."
    $DOCKER_CMD exec cti_postgres psql -U cti_user -d cti_scraper -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1 | grep -v "already exists" || true
    
    # Restart app containers to ensure they connect properly
    print_status "Restarting application containers..."
    $DOCKER_COMPOSE_CMD restart web worker scheduler
    
    # Wait for services to be fully healthy
    print_status "Waiting for services to be healthy..."
    sleep 15
    
    # Check service status
    print_status "Service status:"
    $DOCKER_COMPOSE_CMD ps
    
    print_status "Services started successfully!"
    
    # Show LLM-specific instructions
    if [[ "$USE_LMSTUDIO" == "true" ]]; then
        echo ""
        echo -e "${YELLOW}⚠️  LM Studio Setup:${NC}"
        echo "   1. Start LM Studio application"
        echo "   2. Ensure API Server is running on port 1234"
        echo "   3. Load your preferred model in LM Studio"
    fi
    
    if [[ "$USE_LMSTUDIO" == "false" ]]; then
        echo ""
        echo -e "${YELLOW}⚠️  No LLM Configured:${NC}"
        echo "   Services will start without LLM support."
        echo "   Configure LM Studio or API keys in .env to enable LLM features."
    fi
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

# Function to verify installation
verify_installation() {
    print_header "Verifying Installation"
    
    local verification_failed=false
    
    # Check if services are running
    print_status "Checking service health..."
    
    # Check PostgreSQL
    if $DOCKER_CMD exec cti_postgres pg_isready -U cti_user -d cti_scraper &> /dev/null; then
        print_status "✅ PostgreSQL is healthy"
    else
        print_error "❌ PostgreSQL is not ready"
        verification_failed=true
    fi
    
    # Check Redis
    if $DOCKER_CMD exec cti_redis redis-cli ping &> /dev/null; then
        print_status "✅ Redis is healthy"
    else
        print_error "❌ Redis is not ready"
        verification_failed=true
    fi
    
    # Check Web service with retries
    print_status "Waiting for web service to be ready..."
    local web_ready=false
    for i in {1..30}; do
        if curl -s http://localhost:8001/health &> /dev/null; then
            web_ready=true
            break
        fi
        sleep 2
    done
    
    if [ "$web_ready" = true ]; then
        print_status "✅ Web service is healthy"
    else
        print_error "❌ Web service is not ready"
        print_status "Check logs with: $DOCKER_CMD logs cti_web"
        verification_failed=true
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

# Build MkDocs site and start dev server so docs are ready and running
build_and_serve_mkdocs() {
    if [ ! -f "mkdocs.yml" ]; then
        return 0
    fi
    print_status "Building docs (MkDocs)..."
    if [ ! -d ".venv" ]; then
        python3 -m venv .venv
    fi
    local py=".venv/bin/python3"
    "$py" -m pip install -q mkdocs mkdocs-material
    if ! "$py" -m mkdocs build --strict 2>/dev/null; then
        "$py" -m mkdocs build
    fi
    print_status "Starting MkDocs server in background..."
    mkdir -p logs
    nohup "$py" -m mkdocs serve >> logs/mkdocs.log 2>&1 </dev/null &
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
    
    # Start services
    start_services
    
    # Setup automated backups (unless disabled)
    if [ "$no_backups" = false ]; then
        setup_automated_backups "$backup_time"
    else
        print_warning "Skipping automated backup setup"
    fi
    
    # Refresh LLM provider model catalog so users see current models immediately (no 24h wait)
    print_status "Refreshing LLM provider model catalog..."
    if $DOCKER_COMPOSE_CMD run --rm cli python3 scripts/maintenance/update_provider_model_catalogs.py --write 2>/dev/null; then
        print_status "Provider model catalog updated"
    else
        print_warning "Provider model catalog refresh skipped (set OPENAI_API_KEY/ANTHROPIC_API_KEY in .env to refresh from APIs)"
    fi

    # Verify installation
    local setup_success=false
    if verify_installation; then
        setup_success=true
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