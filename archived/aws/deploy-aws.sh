#!/bin/bash

# CTIScraper AWS Deployment Script
# This script automates the deployment of CTIScraper to AWS using Terraform

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
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

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check prerequisites
check_prerequisites() {
    print_status "Checking prerequisites..."
    
    local missing_deps=()
    
    if ! command_exists terraform; then
        missing_deps+=("terraform")
    fi
    
    if ! command_exists aws; then
        missing_deps+=("aws-cli")
    fi
    
    if ! command_exists docker; then
        missing_deps+=("docker")
    fi
    
    if ! command_exists jq; then
        missing_deps+=("jq")
    fi
    
    if [ ${#missing_deps[@]} -ne 0 ]; then
        print_error "Missing dependencies: ${missing_deps[*]}"
        print_error "Please install the missing dependencies and try again."
        exit 1
    fi
    
    print_success "All prerequisites are installed"
}

# Function to validate AWS credentials
validate_aws_credentials() {
    print_status "Validating AWS credentials..."
    
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        print_error "AWS credentials not configured or invalid"
        print_error "Please run 'aws configure' to set up your credentials"
        exit 1
    fi
    
    local account_id=$(aws sts get-caller-identity --query Account --output text)
    local user_arn=$(aws sts get-caller-identity --query Arn --output text)
    
    print_success "AWS credentials validated"
    print_status "Account ID: $account_id"
    print_status "User: $user_arn"
}

# Function to get user input
get_user_input() {
    local prompt="$1"
    local default="$2"
    local value
    
    if [ -n "$default" ]; then
        read -p "$prompt [$default]: " value
        value=${value:-$default}
    else
        read -p "$prompt: " value
    fi
    
    echo "$value"
}

# Function to generate random password
generate_password() {
    openssl rand -base64 32 | tr -d "=+/" | cut -c1-25
}

# Function to create terraform.tfvars
create_tfvars() {
    print_status "Creating terraform.tfvars file..."
    
    local environment
    local aws_region
    local db_password
    local redis_password
    local openai_api_key
    local domain_name
    local enable_ollama
    
    environment=$(get_user_input "Enter environment" "dev")
    aws_region=$(get_user_input "Enter AWS region" "us-east-1")
    db_password=$(get_user_input "Enter database password (or press Enter to generate)" "")
    redis_password=$(get_user_input "Enter Redis password (or press Enter to generate)" "")
    openai_api_key=$(get_user_input "Enter OpenAI API key (optional)" "")
    domain_name=$(get_user_input "Enter domain name (optional)" "")
    enable_ollama=$(get_user_input "Enable Ollama LLM service? (true/false)" "false")
    
    # Generate passwords if not provided
    if [ -z "$db_password" ]; then
        db_password=$(generate_password)
        print_success "Generated database password: $db_password"
    fi
    
    if [ -z "$redis_password" ]; then
        redis_password=$(generate_password)
        print_success "Generated Redis password: $redis_password"
    fi
    
    # Create terraform.tfvars
    cat > terraform/terraform.tfvars << EOF
environment = "$environment"
aws_region = "$aws_region"
db_password = "$db_password"
redis_password = "$redis_password"
openai_api_key = "$openai_api_key"
domain_name = "$domain_name"
enable_ollama = $enable_ollama
EOF
    
    print_success "Created terraform.tfvars"
}

# Function to initialize Terraform
init_terraform() {
    print_status "Initializing Terraform..."
    
    cd terraform
    
    terraform init
    
    print_success "Terraform initialized"
}

# Function to plan Terraform deployment
plan_terraform() {
    print_status "Planning Terraform deployment..."
    
    terraform plan -out=tfplan
    
    print_success "Terraform plan created"
}

# Function to apply Terraform deployment
apply_terraform() {
    print_status "Applying Terraform deployment..."
    
    terraform apply tfplan
    
    print_success "Terraform deployment completed"
}

# Function to build and push Docker images
build_and_push_images() {
    print_status "Building and pushing Docker images..."
    
    # Get ECR repository URLs from Terraform output
    local web_repo=$(terraform output -raw ecr_web_repository_url)
    local worker_repo=$(terraform output -raw ecr_worker_repository_url)
    local scheduler_repo=$(terraform output -raw ecr_scheduler_repository_url)
    
    # Login to ECR
    aws ecr get-login-password --region $(terraform output -raw aws_region) | docker login --username AWS --password-stdin $web_repo
    
    # Build and push web image
    print_status "Building web image..."
    docker build -t cti-scraper-web .
    docker tag cti-scraper-web:latest $web_repo:latest
    docker push $web_repo:latest
    
    # Build and push worker image
    print_status "Building worker image..."
    docker build -t cti-scraper-worker .
    docker tag cti-scraper-worker:latest $worker_repo:latest
    docker push $worker_repo:latest
    
    # Build and push scheduler image
    print_status "Building scheduler image..."
    docker build -t cti-scraper-scheduler .
    docker tag cti-scraper-scheduler:latest $scheduler_repo:latest
    docker push $scheduler_repo:latest
    
    print_success "All Docker images built and pushed"
}

# Function to update ECS services
update_ecs_services() {
    print_status "Updating ECS services..."
    
    local cluster_name=$(terraform output -raw ecs_cluster_name)
    
    # Force new deployment for all services
    aws ecs update-service --cluster $cluster_name --service $(terraform output -raw ecs_web_service_name) --force-new-deployment
    aws ecs update-service --cluster $cluster_name --service $(terraform output -raw ecs_worker_service_name) --force-new-deployment
    aws ecs update-service --cluster $cluster_name --service $(terraform output -raw ecs_scheduler_service_name) --force-new-deployment
    
    print_success "ECS services updated"
}

# Function to wait for services to be stable
wait_for_services() {
    print_status "Waiting for services to be stable..."
    
    local cluster_name=$(terraform output -raw ecs_cluster_name)
    
    aws ecs wait services-stable --cluster $cluster_name --services $(terraform output -raw ecs_web_service_name)
    aws ecs wait services-stable --cluster $cluster_name --services $(terraform output -raw ecs_worker_service_name)
    aws ecs wait services-stable --cluster $cluster_name --services $(terraform output -raw ecs_scheduler_service_name)
    
    print_success "All services are stable"
}

# Function to display deployment information
display_deployment_info() {
    print_success "Deployment completed successfully!"
    echo
    print_status "Deployment Information:"
    echo "  ALB DNS Name: $(terraform output -raw alb_dns_name)"
    echo "  RDS Endpoint: $(terraform output -raw rds_endpoint)"
    echo "  Redis Endpoint: $(terraform output -raw redis_endpoint)"
    echo "  S3 Bucket: $(terraform output -raw s3_bucket_name)"
    echo
    print_status "Access URLs:"
    echo "  Web Application: http://$(terraform output -raw alb_dns_name)"
    echo "  Health Check: http://$(terraform output -raw alb_dns_name)/health"
    echo
    print_status "Next Steps:"
    echo "  1. Configure your domain name (if applicable)"
    echo "  2. Set up SSL certificate for HTTPS"
    echo "  3. Configure monitoring and alerting"
    echo "  4. Test the application functionality"
    echo "  5. Set up backup and disaster recovery procedures"
}

# Function to cleanup on error
cleanup_on_error() {
    print_error "Deployment failed. Cleaning up..."
    
    if [ -f "terraform/tfplan" ]; then
        rm terraform/tfplan
    fi
    
    print_error "Cleanup completed"
}

# Main deployment function
main() {
    print_status "Starting CTIScraper AWS deployment..."
    
    # Set up error handling
    trap cleanup_on_error ERR
    
    # Check prerequisites
    check_prerequisites
    
    # Validate AWS credentials
    validate_aws_credentials
    
    # Get user input and create tfvars
    create_tfvars
    
    # Initialize Terraform
    init_terraform
    
    # Plan deployment
    plan_terraform
    
    # Ask for confirmation
    echo
    print_warning "This will create AWS resources that may incur costs."
    read -p "Do you want to continue? (y/N): " confirm
    
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        print_status "Deployment cancelled by user"
        exit 0
    fi
    
    # Apply Terraform
    apply_terraform
    
    # Build and push Docker images
    build_and_push_images
    
    # Update ECS services
    update_ecs_services
    
    # Wait for services to be stable
    wait_for_services
    
    # Display deployment information
    display_deployment_info
    
    print_success "CTIScraper deployment completed successfully!"
}

# Run main function
main "$@"
