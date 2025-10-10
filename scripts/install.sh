#!/bin/bash

# CTI Scraper Installation Script
# This script sets up the CTI Scraper with automated backups enabled by default

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
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
    echo "  --backup-time <time>      Backup time (HH:MM format, default: 2:00)"
    echo "  --backup-dir <dir>        Backup directory (default: backups)"
    echo "  --help                    Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0                        # Full installation with automated backups"
    echo "  $0 --no-backups           # Installation without automated backups"
    echo "  $0 --backup-time 1:30     # Installation with custom backup time"
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
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 is not installed. Please install Python 3 first."
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
    
    # Create .env file if it doesn't exist
    if [ ! -f ".env" ]; then
        if [ -f "env.example" ]; then
            print_status "Creating .env file from env.example"
            cp env.example .env
            print_warning "Please edit .env file with your configuration before starting services"
        else
            print_warning "No env.example found. Please create .env file manually"
        fi
    else
        print_status ".env file already exists"
    fi
    
    # Create necessary directories
    print_status "Creating necessary directories"
    mkdir -p logs backups models outputs
    
    # Set permissions
    chmod +x scripts/*.sh
    chmod +x scripts/*.py
    
    print_status "Environment setup complete!"
}

# Function to build and start services
start_services() {
    print_header "Starting Services"
    
    # Build and start Docker services
    print_status "Building Docker images..."
    docker-compose build
    
    print_status "Starting services..."
    docker-compose up -d
    
    # Wait for services to be healthy
    print_status "Waiting for services to be healthy..."
    sleep 10
    
    # Check service status
    print_status "Service status:"
    docker-compose ps
    
    print_status "Services started successfully!"
}

# Function to setup automated backups
setup_automated_backups() {
    local backup_time=$1
    local backup_dir=$2
    
    print_header "Setting Up Automated Backups"
    
    # Check if setup script exists
    if [ ! -f "scripts/setup_automated_backups.sh" ]; then
        print_error "Backup setup script not found!"
        return 1
    fi
    
    # Run backup setup
    print_status "Configuring automated daily backups..."
    ./scripts/setup_automated_backups.sh --backup-time "$backup_time" --backup-dir "$backup_dir"
    
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
    
    # Check Web service
    if curl -s http://localhost:8001/health &> /dev/null; then
        print_status "✅ Web service is healthy"
    else
        print_warning "⚠️  Web service is not ready yet"
    fi
    
    # Check backup system
    if [ -f "scripts/backup_system.py" ]; then
        print_status "✅ Backup system is available"
    else
        print_warning "⚠️  Backup system not found"
    fi
    
    print_status "Installation verification complete!"
}

# Function to show post-installation information
show_post_install_info() {
    print_header "Installation Complete!"
    
    echo ""
    echo "🎉 CTI Scraper has been successfully installed!"
    echo ""
    echo "📋 Service Information:"
    echo "   • Web Interface: http://localhost:8001"
    echo "   • Database: PostgreSQL on port 5432"
    echo "   • Redis: Redis on port 6379"
    echo "   • Ollama: Ollama on port 11434"
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
    echo "   • Restore backup: ./scripts/backup_restore.sh restore <backup_name>"
    echo "   • Check backup status: ./scripts/setup_automated_backups.sh --status"
    echo ""
    echo "📚 Documentation:"
    echo "   • Backup System: docs/development/BACKUP_SYSTEM.md"
    echo "   • Database Backup: docs/DATABASE_BACKUP_RESTORE.md"
    echo "   • API Documentation: docs/API_ENDPOINTS.md"
    echo ""
    echo "⚠️  Next Steps:"
    echo "   1. Edit .env file with your configuration"
    echo "   2. Restart services: docker-compose restart"
    echo "   3. Access web interface: http://localhost:8001"
    echo "   4. Verify automated backups are working"
    echo ""
    echo "🆘 Support:"
    echo "   • Check logs: docker-compose logs"
    echo "   • Backup status: ./scripts/setup_automated_backups.sh --status"
    echo "   • Troubleshooting: docs/development/"
    echo ""
}

# Main script logic
main() {
    # Default values
    local no_backups=false
    local backup_time="2:00"
    local backup_dir="backups"
    local help=false
    
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
            --backup-dir)
                backup_dir="$2"
                shift 2
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
    
    # Start installation
    print_header "CTI Scraper Installation"
    
    # Check prerequisites
    check_prerequisites
    
    # Setup environment
    setup_environment
    
    # Start services
    start_services
    
    # Setup automated backups (unless disabled)
    if [ "$no_backups" = false ]; then
        setup_automated_backups "$backup_time" "$backup_dir"
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
