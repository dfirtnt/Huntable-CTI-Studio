#!/bin/bash

# CTI Scraper Setup Script
# Automated setup for new users

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker >/dev/null 2>&1; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    # Check Docker Compose
    if ! command -v docker-compose >/dev/null 2>&1; then
        print_error "Docker Compose is not installed. Please install Docker Compose first."
        exit 1
    fi
    
    # Check if Docker is running
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker is not running. Please start Docker Desktop first."
        exit 1
    fi
    
    print_success "Prerequisites check passed"
}

# Function to create .env file
create_env_file() {
    print_status "Setting up environment configuration..."
    
    if [ ! -f ".env" ]; then
        if [ -f "env.example" ]; then
            cp env.example .env
            print_success "Created .env file from env.example"
        else
            print_error "env.example file not found. Cannot create .env file."
            exit 1
        fi
    else
        print_warning ".env file already exists. Skipping creation."
    fi
    
    # Verify critical environment variables
    if ! grep -q "REDIS_PASSWORD=" .env; then
        print_error ".env file is missing REDIS_PASSWORD. Please check your .env file."
        exit 1
    fi
    
    if ! grep -q "POSTGRES_PASSWORD=" .env; then
        print_error ".env file is missing POSTGRES_PASSWORD. Please check your .env file."
        exit 1
    fi
    
    print_success "Environment configuration verified"
}

# Function to create necessary directories
create_directories() {
    print_status "Creating necessary directories..."
    
    mkdir -p logs data nginx/ssl backups
    
    print_success "Directories created"
}

# Function to stop existing containers
cleanup_containers() {
    print_status "Cleaning up existing containers..."
    
    docker-compose down --remove-orphans 2>/dev/null || true
    
    print_success "Container cleanup completed"
}

# Function to start services
start_services() {
    print_status "Starting CTI Scraper services..."
    
    docker-compose up -d
    
    print_success "Services started"
}

# Function to wait for services
wait_for_services() {
    print_status "Waiting for services to be ready..."
    
    # Wait for PostgreSQL
    print_status "Waiting for PostgreSQL..."
    for i in {1..30}; do
        if docker-compose exec -T postgres pg_isready -U cti_user -d cti_scraper >/dev/null 2>&1; then
            print_success "PostgreSQL is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            print_error "PostgreSQL failed to start within 60 seconds"
            docker-compose logs postgres
            exit 1
        fi
        sleep 2
    done
    
    # Wait for Redis
    print_status "Waiting for Redis..."
    for i in {1..30}; do
        if docker-compose exec -T redis redis-cli ping >/dev/null 2>&1; then
            print_success "Redis is ready"
            break
        fi
        if [ $i -eq 30 ]; then
            print_error "Redis failed to start within 60 seconds"
            docker-compose logs redis
            exit 1
        fi
        sleep 2
    done
    
    # Wait for Web service
    print_status "Waiting for Web service..."
    for i in {1..60}; do
        if curl -f http://localhost:8000/health >/dev/null 2>&1; then
            print_success "Web service is ready"
            break
        fi
        if [ $i -eq 60 ]; then
            print_error "Web service failed to start within 120 seconds"
            docker-compose logs web
            exit 1
        fi
        sleep 2
    done
}

# Function to verify installation
verify_installation() {
    print_status "Verifying installation..."
    
    # Check container status
    if ! docker-compose ps | grep -q "Up"; then
        print_error "Some containers are not running"
        docker-compose ps
        exit 1
    fi
    
    # Test web interface
    if ! curl -f http://localhost:8000/health >/dev/null 2>&1; then
        print_error "Web interface is not accessible"
        exit 1
    fi
    
    print_success "Installation verified"
}

# Function to show summary
show_summary() {
    echo
    print_success "🎉 CTI Scraper setup completed successfully!"
    echo
    echo "📊 Services:"
    echo "   • Web Interface: http://localhost:8000"
    echo "   • API Documentation: http://localhost:8000/docs"
    echo "   • Health Check: http://localhost:8000/health"
    echo
    echo "🔧 Management Commands:"
    echo "   • View logs:     docker-compose logs -f [service]"
    echo "   • Stop stack:    docker-compose down"
    echo "   • Restart:       docker-compose restart [service]"
    echo "   • CLI Commands:  ./run_cli.sh <command>"
    echo
    echo "📈 Quick Start:"
    echo "   • Initialize sources: ./run_cli.sh init"
    echo "   • List sources:       ./run_cli.sh sources list"
    echo "   • Collect articles:   ./run_cli.sh collect"
    echo
    echo "🐳 Running containers:"
    docker-compose ps
    echo
    print_success "✨ Setup complete! Your CTI Scraper is ready to use."
}

# Main function
main() {
    echo "🚀 CTI Scraper Setup Script"
    echo "=========================="
    echo
    
    check_prerequisites
    create_env_file
    create_directories
    cleanup_containers
    start_services
    wait_for_services
    verify_installation
    show_summary
}

# Run main function
main "$@"
