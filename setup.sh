#!/bin/bash

# =============================================================================
# CTI Scraper Interactive Setup Script
# =============================================================================
#
# This script provides an interactive guided setup for CTI Scraper, including:
#
# Features:
# - Interactive LLM configuration (LM Studio, OpenAI, Anthropic)
# - Secure password generation for PostgreSQL and Redis
# - Optional API key configuration
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
    
    # Prompt for LM Studio
    if prompt_yes_no "Do you want to use LM Studio for local LLM?" "no"; then
        USE_LMSTUDIO=true
        print_status "LM Studio will be enabled (ensure it's running on port 1234)"
    else
        USE_LMSTUDIO=false
        print_warning "LM Studio will be disabled"
    fi
    
    # Prompt for OpenAI API
    if prompt_yes_no "Do you want to configure OpenAI API?" "no"; then
        OPENAI_API_KEY=""
        prompt_input "Enter OpenAI API key: " "" "OPENAI_API_KEY" "true"
        if [[ -z "$OPENAI_API_KEY" ]]; then
            print_warning "OpenAI API key not provided, API will not be used"
        else
            print_status "OpenAI API configured"
        fi
    fi
    
    # Prompt for Anthropic API
    if prompt_yes_no "Do you want to configure Anthropic Claude API?" "no"; then
        ANTHROPIC_API_KEY=""
        prompt_input "Enter Anthropic API key: " "" "ANTHROPIC_API_KEY" "true"
        if [[ -z "$ANTHROPIC_API_KEY" ]]; then
            print_warning "Anthropic API key not provided, API will not be used"
        else
            print_status "Anthropic API configured"
        fi
    fi
}

# Function to prompt for database passwords
configure_database() {
    print_header "Database Configuration"
    
    echo -e "${CYAN}Setting up database credentials...${NC}"
    
    # Check if .env exists
    if [[ -f ".env" ]]; then
        if ! prompt_yes_no ".env file exists. Overwrite it?" "no"; then
            print_status "Using existing .env file"
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
    
    if [[ ! -f "env.example" ]]; then
        print_error "env.example not found!"
        return 1
    fi
    
    # Copy template
    cp env.example .env
    
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
    
    # Update LLM_API_URL based on LLM choice
    if [[ "$USE_LMSTUDIO" == "true" ]]; then
        if [[ "$(uname)" == "Darwin" ]]; then
            sed -i '' 's|LLM_API_URL=.*|LLM_API_URL=http://host.docker.internal:1234/v1|g' .env
        else
            sed -i 's|LLM_API_URL=.*|LLM_API_URL=http://host.docker.internal:1234/v1|g' .env
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
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose &> /dev/null; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if Docker is running
    if ! docker info &> /dev/null; then
        print_error "Docker is not running. Please start Docker first."
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
    docker-compose build
    
    # Start services
    print_status "Starting services..."
    docker-compose up -d
    
    # Wait for postgres to be healthy
    print_status "Waiting for PostgreSQL to be ready..."
    sleep 10
    for i in {1..30}; do
        if docker exec cti_postgres pg_isready -U cti_user -d cti_scraper >/dev/null 2>&1; then
            break
        fi
        sleep 1
    done
    
    # Enable pgvector extension in postgres
    print_status "Enabling pgvector extension..."
    docker exec cti_postgres psql -U cti_user -d cti_scraper -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>&1 | grep -v "already exists" || true
    
    # Restart app containers to ensure they connect properly
    print_status "Restarting application containers..."
    docker-compose restart web worker scheduler
    
    # Wait for services to be fully healthy
    print_status "Waiting for services to be healthy..."
    sleep 15
    
    # Check service status
    print_status "Service status:"
    docker-compose ps
    
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
    
    # Check if services are running
    print_status "Checking service health..."
    
    # Check PostgreSQL
    if docker exec cti_postgres pg_isready -U cti_user -d cti_scraper &> /dev/null; then
        print_status "✅ PostgreSQL is healthy"
    else
        print_warning "⚠️  PostgreSQL is not ready yet"
    fi
    
    # Check Redis
    if docker exec cti_redis redis-cli ping &> /dev/null; then
        print_status "✅ Redis is healthy"
    else
        print_warning "⚠️  Redis is not ready yet"
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
        print_warning "⚠️  Web service is not ready yet"
        print_status "Check logs with: docker logs cti_web"
    fi
    
    print_status "Installation verification complete!"
}

# Function to show post-installation information
show_post_install_info() {
    print_header "Setup Complete!"
    
    echo ""
    echo "🎉 CTI Scraper has been successfully set up!"
    echo ""
    echo "📋 Service Information:"
    echo "   • Web Interface: http://localhost:8001"
    echo "   • Database: PostgreSQL on port 5432"
    echo "   • Redis: Redis on port 6379"
    
    
    if [[ "$USE_LMSTUDIO" == "true" ]]; then
        echo "   • LM Studio: Connect to http://host.docker.internal:1234"
    fi
    
    if [[ -n "$OPENAI_API_KEY" ]]; then
        echo "   • OpenAI API: Configured"
    fi
    
    if [[ -n "$ANTHROPIC_API_KEY" ]]; then
        echo "   • Anthropic Claude API: Configured"
    fi
    
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
    
    echo "   2. Verify automated backups are working"
    echo "   3. Configure your sources in config/sources.yaml"
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
    
    # Create .env file from configuration
    create_env_file
    
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
    
    # Verify installation
    verify_installation
    
    # Show post-installation information
    show_post_install_info
}

# Run main function
main "$@"