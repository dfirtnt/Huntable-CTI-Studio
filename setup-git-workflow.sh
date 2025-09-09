#!/bin/bash

# Git-to-AWS Deployment Setup Script
# This script configures your repository for automatic AWS deployment

set -e

# Colors for output
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
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

# Function to check if we're in a git repository
check_git_repo() {
    if [ ! -d ".git" ]; then
        print_warning "Not in a git repository. Initializing..."
        git init
        print_success "Git repository initialized"
    else
        print_success "Git repository found"
    fi
}

# Function to create .gitignore additions for AWS deployment
setup_gitignore() {
    print_status "Setting up .gitignore for AWS deployment..."
    
    # Add AWS-specific entries to .gitignore
    cat >> .gitignore << 'EOF'

# AWS Deployment Files
terraform.tfvars
terraform.tfstate*
terraform.tfplan
.terraform/
.terraform.lock.hcl

# AWS CLI and credentials
.aws/
aws-credentials

# Environment files
.env.local
.env.production
.env.aws.local

# Docker build cache
.dockerignore

# IDE files
.vscode/
.idea/
*.swp
*.swo

# OS files
.DS_Store
Thumbs.db

# Logs
logs/
*.log

# Temporary files
tmp/
temp/
EOF

    print_success ".gitignore updated for AWS deployment"
}

# Function to create deployment configuration
create_deployment_config() {
    print_status "Creating deployment configuration..."
    
    # Create deployment configuration file
    cat > deployment-config.yml << 'EOF'
# CTIScraper AWS Deployment Configuration
# This file configures automatic deployment from git to AWS

deployment:
  # Git repository configuration
  git:
    branch: main
    remote: origin
    
  # AWS deployment settings
  aws:
    region: us-east-1
    environment: dev
    
  # CI/CD pipeline settings
  pipeline:
    auto_deploy: true
    build_timeout: 30
    test_before_deploy: true
    
  # Docker settings
  docker:
    registry: ecr
    tag_strategy: git_commit
    
  # ECS service settings
  ecs:
    web_service: true
    worker_service: true
    scheduler_service: true
    ollama_service: false
    
  # Monitoring
  monitoring:
    enable_logs: true
    enable_metrics: true
    enable_alerts: true
EOF

    print_success "Deployment configuration created"
}

# Function to create git hooks for deployment
setup_git_hooks() {
    print_status "Setting up git hooks for deployment..."
    
    # Create pre-push hook
    cat > .git/hooks/pre-push << 'EOF'
#!/bin/bash

# Pre-push hook for CTIScraper AWS deployment
echo "🚀 Preparing for AWS deployment..."

# Run tests before pushing
echo "Running tests..."
if [ -f "run_tests.py" ]; then
    python run_tests.py
    if [ $? -ne 0 ]; then
        echo "❌ Tests failed. Push aborted."
        exit 1
    fi
fi

echo "✅ Tests passed. Ready for AWS deployment!"
EOF

    chmod +x .git/hooks/pre-push
    
    print_success "Git hooks configured"
}

# Function to create deployment status script
create_deployment_status() {
    print_status "Creating deployment status script..."
    
    cat > check-deployment.sh << 'EOF'
#!/bin/bash

# Check AWS deployment status
# Usage: ./check-deployment.sh

set -e

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

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

# Check if AWS CLI is configured
if ! aws sts get-caller-identity >/dev/null 2>&1; then
    print_error "AWS CLI not configured. Run 'aws configure' first."
    exit 1
fi

# Get environment from terraform output or default
ENVIRONMENT=${1:-dev}
CLUSTER_NAME="cti-scraper-${ENVIRONMENT}-cluster"

print_status "Checking deployment status for environment: $ENVIRONMENT"

# Check ECS cluster status
print_status "Checking ECS cluster..."
if aws ecs describe-clusters --clusters $CLUSTER_NAME >/dev/null 2>&1; then
    print_success "ECS cluster '$CLUSTER_NAME' is running"
    
    # Check services
    SERVICES=$(aws ecs list-services --cluster $CLUSTER_NAME --query 'serviceArns[]' --output text)
    
    for service in $SERVICES; do
        SERVICE_NAME=$(basename $service)
        print_status "Checking service: $SERVICE_NAME"
        
        # Get service status
        STATUS=$(aws ecs describe-services --cluster $CLUSTER_NAME --services $service --query 'services[0].status' --output text)
        RUNNING=$(aws ecs describe-services --cluster $CLUSTER_NAME --services $service --query 'services[0].runningCount' --output text)
        DESIRED=$(aws ecs describe-services --cluster $CLUSTER_NAME --services $service --query 'services[0].desiredCount' --output text)
        
        if [ "$STATUS" = "ACTIVE" ] && [ "$RUNNING" = "$DESIRED" ]; then
            print_success "Service $SERVICE_NAME: $RUNNING/$DESIRED tasks running"
        else
            print_warning "Service $SERVICE_NAME: $STATUS ($RUNNING/$DESIRED tasks)"
        fi
    done
else
    print_error "ECS cluster '$CLUSTER_NAME' not found"
fi

# Check ALB status
print_status "Checking Application Load Balancer..."
ALB_ARN=$(aws elbv2 describe-load-balancers --query "LoadBalancers[?contains(LoadBalancerName, 'cti-scraper-$ENVIRONMENT')].LoadBalancerArn" --output text)
if [ -n "$ALB_ARN" ]; then
    ALB_DNS=$(aws elbv2 describe-load-balancers --load-balancer-arns $ALB_ARN --query 'LoadBalancers[0].DNSName' --output text)
    print_success "ALB is running at: $ALB_DNS"
    print_status "Web application: http://$ALB_DNS"
    print_status "Health check: http://$ALB_DNS/health"
else
    print_warning "Application Load Balancer not found"
fi

# Check recent deployments
print_status "Checking recent deployments..."
if [ -f "terraform/terraform.tfstate" ]; then
    PIPELINE_NAME="cti-scraper-${ENVIRONMENT}-pipeline"
    if aws codepipeline get-pipeline-state --name $PIPELINE_NAME >/dev/null 2>&1; then
        print_success "CI/CD pipeline '$PIPELINE_NAME' is configured"
    else
        print_warning "CI/CD pipeline not found"
    fi
fi

print_success "Deployment status check completed!"
EOF

    chmod +x check-deployment.sh
    
    print_success "Deployment status script created"
}

# Function to create quick deployment script
create_quick_deploy() {
    print_status "Creating quick deployment script..."
    
    cat > quick-deploy.sh << 'EOF'
#!/bin/bash

# Quick deployment script for CTIScraper
# Usage: ./quick-deploy.sh [environment] [message]

set -e

ENVIRONMENT=${1:-dev}
COMMIT_MESSAGE=${2:-"Deploy to $ENVIRONMENT"}

# Colors
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_status "Starting quick deployment to $ENVIRONMENT..."

# Check if there are changes to commit
if [ -z "$(git status --porcelain)" ]; then
    print_status "No changes to commit"
    exit 0
fi

# Add all changes
print_status "Adding changes..."
git add .

# Commit changes
print_status "Committing changes..."
git commit -m "$COMMIT_MESSAGE"

# Push to trigger deployment
print_status "Pushing to trigger AWS deployment..."
git push origin main

print_success "Deployment triggered! Check status with: ./check-deployment.sh $ENVIRONMENT"
EOF

    chmod +x quick-deploy.sh
    
    print_success "Quick deployment script created"
}

# Function to create development workflow documentation
create_workflow_docs() {
    print_status "Creating workflow documentation..."
    
    cat > WORKFLOW_QUICK_START.md << 'EOF'
# Quick Start: Development to AWS Workflow

## 🚀 One-Time Setup

1. **Configure AWS**:
   ```bash
   aws configure
   ```

2. **Deploy Infrastructure**:
   ```bash
   ./deploy-aws.sh
   ```

3. **Setup Git Workflow**:
   ```bash
   ./setup-git-workflow.sh
   ```

## 🔄 Daily Development Workflow

### Make Changes Locally
```bash
# Start local development
./start_development.sh

# Edit files:
# - UI: src/web/templates/*.html
# - Scoring: src/utils/content.py
# - Backend: src/web/modern_main.py

# Test locally
./run_tests.py
```

### Deploy to AWS
```bash
# Quick deployment (commits and pushes)
./quick-deploy.sh dev "Update threat hunting scoring"

# Or manual:
git add .
git commit -m "Your changes"
git push origin main
```

### Check Deployment Status
```bash
# Check if deployment succeeded
./check-deployment.sh dev
```

## 📁 Key Files to Modify

### UI Changes
- `src/web/templates/dashboard.html` - Main dashboard
- `src/web/templates/articles.html` - Article listing
- `src/web/templates/article_detail.html` - Article details
- `src/web/static/js/annotation-manager.js` - Frontend JavaScript

### Scoring Logic
- `src/utils/content.py` - QualityScorer, ThreatHuntingScorer
- `src/core/processor.py` - ContentProcessor

### Backend Logic
- `src/web/modern_main.py` - API endpoints
- `src/core/modern_scraper.py` - Web scraping
- `src/core/rss_parser.py` - RSS processing

## 🔍 Monitoring

### Local Development
```bash
# View logs
docker-compose logs -f web

# Check health
curl http://localhost:8000/health
```

### AWS Production
```bash
# Check service status
./check-deployment.sh prod

# View logs
aws logs tail /aws/ecs/cti-scraper-prod-web --follow
```

## 🆘 Troubleshooting

### Deployment Failed
```bash
# Check pipeline status
aws codepipeline get-pipeline-state --name cti-scraper-dev-pipeline

# Check ECS service events
aws ecs describe-services --cluster cti-scraper-dev-cluster
```

### Service Won't Start
```bash
# Check task logs
aws logs get-log-events --log-group-name /aws/ecs/cti-scraper-dev-web
```

## ✅ Success!

Your changes are now live on AWS! 🎉
EOF

    print_success "Workflow documentation created"
}

# Main setup function
main() {
    print_status "Setting up Git-to-AWS deployment workflow..."
    
    # Check prerequisites
    if ! command -v git >/dev/null 2>&1; then
        print_error "Git is required but not installed"
        exit 1
    fi
    
    if ! command -v aws >/dev/null 2>&1; then
        print_warning "AWS CLI not found. Please install and configure it."
    fi
    
    # Setup steps
    check_git_repo
    setup_gitignore
    create_deployment_config
    setup_git_hooks
    create_deployment_status
    create_quick_deploy
    create_workflow_docs
    
    print_success "Git-to-AWS workflow setup completed!"
    echo
    print_status "Next steps:"
    echo "1. Configure AWS CLI: aws configure"
    echo "2. Deploy infrastructure: ./deploy-aws.sh"
    echo "3. Start developing: ./start_development.sh"
    echo "4. Deploy changes: ./quick-deploy.sh dev 'Your changes'"
    echo "5. Check status: ./check-deployment.sh dev"
    echo
    print_status "See WORKFLOW_QUICK_START.md for detailed instructions"
}

# Run main function
main "$@"
