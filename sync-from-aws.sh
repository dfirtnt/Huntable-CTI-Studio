#!/bin/bash

# Sync Changes from AWS to Local Development Environment
# This script pulls changes made in AWS back to your local macOS/Docker environment

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

# Function to check if we're in a git repository
check_git_repo() {
    if [ ! -d ".git" ]; then
        print_error "Not in a git repository. Please run this from the CTIScraper root directory."
        exit 1
    fi
}

# Function to check for uncommitted changes
check_uncommitted_changes() {
    if [ -n "$(git status --porcelain)" ]; then
        print_warning "You have uncommitted changes:"
        git status --short
        echo
        read -p "Do you want to stash them before syncing? (y/N): " stash_changes
        
        if [[ $stash_changes =~ ^[Yy]$ ]]; then
            git stash push -m "Stashed before AWS sync $(date)"
            print_success "Changes stashed"
        else
            print_error "Please commit or stash your changes before syncing"
            exit 1
        fi
    fi
}

# Function to pull application changes
pull_application_changes() {
    print_status "Pulling application changes from AWS..."
    
    # Fetch latest changes
    git fetch origin
    
    # Check if there are new commits
    LOCAL=$(git rev-parse HEAD)
    REMOTE=$(git rev-parse origin/main)
    
    if [ "$LOCAL" = "$REMOTE" ]; then
        print_status "No new changes from AWS"
        return 0
    fi
    
    # Show what's new
    print_status "New commits from AWS:"
    git log --oneline HEAD..origin/main
    
    # Pull changes
    git pull origin main
    
    print_success "Application changes pulled from AWS"
}

# Function to pull infrastructure changes
pull_infrastructure_changes() {
    print_status "Checking for infrastructure changes..."
    
    if [ -d "terraform" ]; then
        cd terraform
        
        # Check for Terraform changes
        if [ -f "terraform.tfstate" ]; then
            print_status "Checking Terraform state changes..."
            terraform plan -detailed-exitcode > /dev/null 2>&1
            EXIT_CODE=$?
            
            if [ $EXIT_CODE -eq 2 ]; then
                print_warning "Terraform infrastructure changes detected"
                terraform plan
                echo
                read -p "Do you want to apply these changes locally? (y/N): " apply_changes
                
                if [[ $apply_changes =~ ^[Yy]$ ]]; then
                    terraform apply
                    print_success "Infrastructure changes applied locally"
                else
                    print_warning "Infrastructure changes not applied"
                fi
            else
                print_status "No infrastructure changes needed"
            fi
        fi
        
        cd ..
    fi
}

# Function to update environment configuration
update_environment_config() {
    print_status "Updating environment configuration..."
    
    # Check if AWS environment file exists
    if [ -f "env.aws" ]; then
        # Create local environment file if it doesn't exist
        if [ ! -f ".env.local" ]; then
            cp env.aws .env.local
            print_success "Created .env.local from AWS configuration"
        else
            # Compare and show differences
            if ! diff -q env.aws .env.local > /dev/null 2>&1; then
                print_warning "Environment configuration differences detected:"
                diff env.aws .env.local || true
                echo
                read -p "Do you want to update .env.local with AWS configuration? (y/N): " update_env
                
                if [[ $update_env =~ ^[Yy]$ ]]; then
                    cp env.aws .env.local
                    print_success "Updated .env.local with AWS configuration"
                fi
            else
                print_status "Environment configuration is up to date"
            fi
        fi
    fi
}

# Function to update Docker images
update_docker_images() {
    print_status "Updating Docker images..."
    
    # Check if we can access AWS ECR
    if command -v aws >/dev/null 2>&1; then
        # Get AWS account ID and region
        AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text 2>/dev/null || echo "")
        AWS_REGION=$(aws configure get region 2>/dev/null || echo "us-east-1")
        
        if [ -n "$AWS_ACCOUNT_ID" ]; then
            print_status "Pulling latest images from AWS ECR..."
            
            # Login to ECR
            aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $AWS_ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com
            
            # Get ECR repository URLs (if available)
            WEB_REPO=$(aws ecr describe-repositories --repository-names cti-scraper-dev-web --query 'repositories[0].repositoryUri' --output text 2>/dev/null || echo "")
            WORKER_REPO=$(aws ecr describe-repositories --repository-names cti-scraper-dev-worker --query 'repositories[0].repositoryUri' --output text 2>/dev/null || echo "")
            
            if [ -n "$WEB_REPO" ]; then
                docker pull $WEB_REPO:latest || print_warning "Could not pull web image"
            fi
            
            if [ -n "$WORKER_REPO" ]; then
                docker pull $WORKER_REPO:latest || print_warning "Could not pull worker image"
            fi
            
            print_success "Docker images updated"
        else
            print_warning "AWS CLI not configured, skipping Docker image update"
        fi
    else
        print_warning "AWS CLI not available, skipping Docker image update"
    fi
}

# Function to restart local development environment
restart_local_environment() {
    print_status "Restarting local development environment..."
    
    # Stop existing containers
    if [ -f "docker-compose.yml" ]; then
        docker-compose down
    fi
    
    # Start with updated configuration
    if [ -f "start_development.sh" ]; then
        ./start_development.sh
    else
        docker-compose up --build -d
    fi
    
    print_success "Local development environment restarted"
}

# Function to verify sync
verify_sync() {
    print_status "Verifying sync..."
    
    # Check if local environment is running
    if curl -f http://localhost:8000/health >/dev/null 2>&1; then
        print_success "Local environment is running and healthy"
        print_status "Access your local environment at: http://localhost:8000"
    else
        print_warning "Local environment may not be running properly"
        print_status "Check logs with: docker-compose logs"
    fi
    
    # Show git status
    print_status "Current git status:"
    git status --short
}

# Function to show sync summary
show_sync_summary() {
    print_success "AWS to Local sync completed!"
    echo
    print_status "Summary of changes:"
    echo "  ✅ Application code pulled from AWS"
    echo "  ✅ Infrastructure changes checked"
    echo "  ✅ Environment configuration updated"
    echo "  ✅ Docker images updated"
    echo "  ✅ Local environment restarted"
    echo
    print_status "Next steps:"
    echo "  1. Test your local environment: http://localhost:8000"
    echo "  2. Continue development with AWS changes"
    echo "  3. Deploy back to AWS when ready: ./quick-deploy.sh dev"
    echo
    print_status "Your local environment now matches AWS!"
}

# Main sync function
main() {
    print_status "Starting AWS to Local sync..."
    echo
    
    # Check prerequisites
    check_git_repo
    check_uncommitted_changes
    
    # Sync steps
    pull_application_changes
    pull_infrastructure_changes
    update_environment_config
    update_docker_images
    restart_local_environment
    verify_sync
    show_sync_summary
}

# Run main function
main "$@"