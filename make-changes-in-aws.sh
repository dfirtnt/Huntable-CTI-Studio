#!/bin/bash

# Make Changes in AWS and Sync Back to Local
# This script helps you make changes directly in AWS and sync them back

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

# Function to check AWS CLI
check_aws_cli() {
    if ! command -v aws >/dev/null 2>&1; then
        print_error "AWS CLI not installed. Please install it first."
        exit 1
    fi
    
    if ! aws sts get-caller-identity >/dev/null 2>&1; then
        print_error "AWS CLI not configured. Please run 'aws configure' first."
        exit 1
    fi
}

# Function to get ECS cluster and service info
get_ecs_info() {
    ENVIRONMENT=${1:-dev}
    CLUSTER_NAME="cti-scraper-${ENVIRONMENT}-cluster"
    
    print_status "Getting ECS information for environment: $ENVIRONMENT"
    
    # Check if cluster exists
    if ! aws ecs describe-clusters --clusters $CLUSTER_NAME >/dev/null 2>&1; then
        print_error "ECS cluster '$CLUSTER_NAME' not found"
        exit 1
    fi
    
    # Get running tasks
    TASK_ARNS=$(aws ecs list-tasks --cluster $CLUSTER_NAME --query 'taskArns[]' --output text)
    
    if [ -z "$TASK_ARNS" ]; then
        print_error "No running tasks found in cluster '$CLUSTER_NAME'"
        exit 1
    fi
    
    # Get task details
    TASK_DETAILS=$(aws ecs describe-tasks --cluster $CLUSTER_NAME --tasks $TASK_ARNS --query 'tasks[0]')
    TASK_ID=$(echo $TASK_DETAILS | jq -r '.taskArn | split("/") | .[1]')
    
    print_success "Found running task: $TASK_ID"
    echo "Cluster: $CLUSTER_NAME"
    echo "Task ID: $TASK_ID"
}

# Function to access ECS container
access_ecs_container() {
    ENVIRONMENT=${1:-dev}
    CONTAINER_NAME=${2:-web}
    
    CLUSTER_NAME="cti-scraper-${ENVIRONMENT}-cluster"
    
    print_status "Accessing ECS container: $CONTAINER_NAME"
    
    # Get running tasks
    TASK_ARNS=$(aws ecs list-tasks --cluster $CLUSTER_NAME --query 'taskArns[]' --output text)
    
    if [ -z "$TASK_ARNS" ]; then
        print_error "No running tasks found"
        exit 1
    fi
    
    # Get first task
    TASK_ARN=$(echo $TASK_ARNS | awk '{print $1}')
    
    print_status "Accessing task: $TASK_ARN"
    print_warning "You're now in the AWS container. Make your changes and commit them."
    print_status "Example commands:"
    echo "  vim src/web/templates/dashboard.html"
    echo "  vim src/utils/content.py"
    echo "  git add ."
    echo "  git commit -m 'AWS testing changes'"
    echo "  git push origin main"
    echo
    print_status "Press Enter to continue..."
    read
    
    # Execute command in container
    aws ecs execute-command \
        --cluster $CLUSTER_NAME \
        --task $TASK_ARN \
        --container $CONTAINER_NAME \
        --interactive \
        --command "/bin/bash"
}

# Function to make changes via CloudShell
make_changes_cloudshell() {
    print_status "Instructions for making changes via AWS CloudShell:"
    echo
    print_status "1. Open AWS CloudShell in your browser"
    print_status "2. Clone your repository:"
    echo "   git clone https://github.com/your-username/CTIScraper.git"
    echo "   cd CTIScraper"
    echo
    print_status "3. Make your changes:"
    echo "   vim src/web/templates/dashboard.html"
    echo "   vim src/utils/content.py"
    echo
    print_status "4. Commit and push:"
    echo "   git add ."
    echo "   git commit -m 'AWS CloudShell changes'"
    echo "   git push origin main"
    echo
    print_status "5. Run sync script to pull changes locally:"
    echo "   ./sync-from-aws.sh"
}

# Function to update ECS service configuration
update_ecs_service() {
    ENVIRONMENT=${1:-dev}
    SERVICE_NAME="cti-scraper-${ENVIRONMENT}-web"
    CLUSTER_NAME="cti-scraper-${ENVIRONMENT}-cluster"
    
    print_status "Updating ECS service configuration..."
    
    # Get current task definition
    CURRENT_TASK_DEF=$(aws ecs describe-services --cluster $CLUSTER_NAME --services $SERVICE_NAME --query 'services[0].taskDefinition' --output text)
    
    print_status "Current task definition: $CURRENT_TASK_DEF"
    
    # Force new deployment
    print_status "Forcing new deployment..."
    aws ecs update-service \
        --cluster $CLUSTER_NAME \
        --service $SERVICE_NAME \
        --force-new-deployment
    
    print_success "ECS service update initiated"
}

# Function to update infrastructure
update_infrastructure() {
    print_status "Updating infrastructure via Terraform..."
    
    if [ -d "terraform" ]; then
        cd terraform
        
        # Check current state
        terraform plan
        
        echo
        read -p "Do you want to apply these changes? (y/N): " apply_changes
        
        if [[ $apply_changes =~ ^[Yy]$ ]]; then
            terraform apply
            print_success "Infrastructure updated"
            
            # Commit infrastructure changes
            git add .
            git commit -m "AWS infrastructure updates"
            git push origin main
        else
            print_warning "Infrastructure changes not applied"
        fi
        
        cd ..
    else
        print_error "Terraform directory not found"
    fi
}

# Function to show AWS change options
show_change_options() {
    echo
    print_status "Choose how you want to make changes in AWS:"
    echo
    echo "1. Access ECS container directly (recommended for code changes)"
    echo "2. Use AWS CloudShell (browser-based terminal)"
    echo "3. Update ECS service configuration"
    echo "4. Update infrastructure via Terraform"
    echo "5. Show all options"
    echo
}

# Function to handle user choice
handle_choice() {
    read -p "Enter your choice (1-5): " choice
    
    case $choice in
        1)
            ENVIRONMENT=${1:-dev}
            CONTAINER=${2:-web}
            access_ecs_container $ENVIRONMENT $CONTAINER
            ;;
        2)
            make_changes_cloudshell
            ;;
        3)
            ENVIRONMENT=${1:-dev}
            update_ecs_service $ENVIRONMENT
            ;;
        4)
            update_infrastructure
            ;;
        5)
            show_change_options
            handle_choice $1 $2
            ;;
        *)
            print_error "Invalid choice. Please enter 1-5."
            handle_choice $1 $2
            ;;
    esac
}

# Function to show post-change instructions
show_post_change_instructions() {
    echo
    print_success "Changes made in AWS!"
    echo
    print_status "Next steps to sync changes back to local:"
    echo
    echo "1. Run the sync script:"
    echo "   ./sync-from-aws.sh"
    echo
    echo "2. Or manually pull changes:"
    echo "   git pull origin main"
    echo "   ./start.sh"
    echo
    print_status "Your AWS changes will now be available locally!"
}

# Main function
main() {
    print_status "AWS Change Maker - Make changes in AWS and sync back to local"
    echo
    
    # Check prerequisites
    check_aws_cli
    
    # Get environment
    ENVIRONMENT=${1:-dev}
    print_status "Target environment: $ENVIRONMENT"
    
    # Get ECS info
    get_ecs_info $ENVIRONMENT
    
    # Show options
    show_change_options
    handle_choice $ENVIRONMENT
    
    # Show post-change instructions
    show_post_change_instructions
}

# Run main function
main "$@"
