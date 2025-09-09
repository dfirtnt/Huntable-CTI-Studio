# Bidirectional Development Workflow: AWS ↔ macOS/Docker

## ✅ **YES - Changes Flow Both Ways!**

The CTIScraper architecture supports **bidirectional development**:

- ✅ **macOS/Docker → AWS**: Local changes deploy to AWS
- ✅ **AWS → macOS/Docker**: AWS changes sync back to local
- ✅ **Any changes**: UI, scoring, business logic, configuration
- ✅ **Git-based sync**: Standard git pull/merge workflow

## 🔄 **Bidirectional Workflow Scenarios**

### **Scenario 1: AWS Testing → Local Development**
```bash
# You're testing in AWS and discover an issue
# Make a quick fix directly in AWS (via CloudShell, ECS exec, etc.)

# Pull changes back to local
git pull origin main

# Continue development locally
./start_development.sh
# Your AWS changes are now in your local environment
```

### **Scenario 2: AWS Configuration Changes → Local**
```bash
# You update configuration in AWS (via Terraform, AWS Console, etc.)
# Pull infrastructure changes
cd terraform
git pull origin main
terraform plan  # See what changed
terraform apply # Apply changes locally

# Pull application changes
git pull origin main
./start_development.sh
```

### **Scenario 3: AWS Database Changes → Local**
```bash
# You modify database schema or data in AWS
# Export changes
aws rds describe-db-instances --db-instance-identifier your-db

# Pull application changes that use the new schema
git pull origin main
./start_development.sh
```

## 🛠️ **Methods to Make Changes in AWS**

### **Method 1: Direct Container Access**
```bash
# Access running ECS container
aws ecs execute-command \
  --cluster cti-scraper-dev-cluster \
  --task <TASK_ID> \
  --container web \
  --interactive \
  --command "/bin/bash"

# Inside container, make changes
vim src/web/templates/dashboard.html
vim src/utils/content.py

# Commit changes from container
git add .
git commit -m "AWS testing changes"
git push origin main
```

### **Method 2: AWS CloudShell**
```bash
# Use AWS CloudShell (browser-based terminal)
# Clone your repository
git clone https://github.com/your-repo/CTIScraper.git
cd CTIScraper

# Make changes
vim src/web/templates/dashboard.html
vim src/utils/content.py

# Commit and push
git add .
git commit -m "AWS CloudShell changes"
git push origin main
```

### **Method 3: ECS Task Definition Updates**
```bash
# Update environment variables or configuration
aws ecs update-service \
  --cluster cti-scraper-dev-cluster \
  --service cti-scraper-dev-web \
  --task-definition cti-scraper-dev-web:NEW_REVISION
```

### **Method 4: Infrastructure Changes**
```bash
# Update Terraform configuration
cd terraform
vim variables.tf  # Change configuration
terraform plan
terraform apply

# Commit infrastructure changes
git add .
git commit -m "AWS infrastructure updates"
git push origin main
```

## 🔄 **Sync Changes Back to Local**

### **Pull Application Changes**
```bash
# Pull latest changes from git
git pull origin main

# Restart local development with new changes
./start_development.sh

# Verify changes are applied
curl http://localhost:8000/health
```

### **Pull Infrastructure Changes**
```bash
# Pull Terraform changes
cd terraform
git pull origin main

# Update local infrastructure (if needed)
terraform plan
terraform apply

# Update local environment variables
cp env.aws .env.local
```

### **Pull Database Changes**
```bash
# If database schema changed in AWS
# Update local database
docker-compose exec postgres psql -U cti_user -d cti_scraper -c "ALTER TABLE..."

# Or restore from AWS backup
aws rds create-db-snapshot --db-instance-identifier your-db --db-snapshot-identifier test-snapshot
```

## 📋 **Specific Change Types That Sync Both Ways**

### **UI Changes**
```bash
# AWS: Edit templates
vim src/web/templates/dashboard.html

# Local: Pull and see changes
git pull origin main
./start_development.sh
# Changes are now in your local environment
```

### **Scoring Logic Changes**
```bash
# AWS: Update scoring algorithm
vim src/utils/content.py
# Modify ThreatHuntingScorer.score_threat_hunting_content()

# Local: Pull and test
git pull origin main
./run_tests.py
# Your AWS scoring changes are now local
```

### **Business Logic Changes**
```bash
# AWS: Update scraping logic
vim src/core/modern_scraper.py
# Modify scraping rules

# Local: Pull and continue development
git pull origin main
./start_development.sh
# AWS changes are now in your local environment
```

### **Configuration Changes**
```bash
# AWS: Update environment variables
aws ecs update-service --task-definition cti-scraper-dev-web:NEW_REVISION

# Local: Update local configuration
cp env.aws .env.local
# Or pull Terraform changes
cd terraform && git pull origin main
```

## 🔧 **Tools for Bidirectional Development**

### **Git Workflow**
```bash
# Standard git commands work both ways
git add .
git commit -m "Changes made in AWS"
git push origin main

# Pull changes to local
git pull origin main
git merge origin/main
```

### **Docker Sync**
```bash
# Local Docker uses same images as AWS
docker pull <ECR_REPO_URL>:latest
docker-compose up --build
```

### **Database Sync**
```bash
# Export from AWS
aws rds create-db-snapshot --db-instance-identifier your-db

# Import to local
docker-compose exec postgres psql -U cti_user -d cti_scraper < backup.sql
```

## 🚀 **Enhanced Workflow Scripts**

I've created scripts to make bidirectional sync easier:

### **Sync from AWS to Local**
```bash
# Pull all AWS changes back to local
./sync-from-aws.sh

# This script:
# 1. Pulls application changes from git
# 2. Updates infrastructure configuration
# 3. Updates environment variables
# 4. Pulls latest Docker images
# 5. Restarts local environment
```

### **Make Changes in AWS**
```bash
# Interactive script to make changes in AWS
./make-changes-in-aws.sh dev

# Options:
# 1. Access ECS container directly
# 2. Use AWS CloudShell
# 3. Update ECS service configuration
# 4. Update infrastructure via Terraform
```

## 📋 **Complete Bidirectional Workflow**

### **Local → AWS → Local Cycle**
```bash
# 1. Start with local development
./start_development.sh

# 2. Make changes locally
vim src/web/templates/dashboard.html
vim src/utils/content.py

# 3. Deploy to AWS
./quick-deploy.sh dev "Local changes"

# 4. Test in AWS, discover issues
# 5. Make quick fixes in AWS
./make-changes-in-aws.sh dev

# 6. Sync AWS changes back to local
./sync-from-aws.sh

# 7. Continue development locally with AWS changes
./start_development.sh
```

## 🎯 **Key Benefits of Bidirectional Workflow**

### **Flexibility**
- ✅ Develop locally for rapid iteration
- ✅ Test in AWS for production-like environment
- ✅ Make quick fixes in AWS when needed
- ✅ Sync changes back seamlessly

### **Consistency**
- ✅ Same codebase everywhere
- ✅ Same Docker images
- ✅ Same configuration management
- ✅ Same git workflow

### **Efficiency**
- ✅ No manual file copying
- ✅ No configuration drift
- ✅ Automatic synchronization
- ✅ Version control for all changes

## 🔍 **Monitoring Bidirectional Changes**

### **Track Changes**
```bash
# See what changed in AWS
git log --oneline origin/main

# See what changed locally
git log --oneline HEAD

# See differences
git diff HEAD origin/main
```

### **Verify Sync**
```bash
# Check if local matches AWS
git status

# Verify local environment
curl http://localhost:8000/health

# Check AWS environment
./check-deployment.sh dev
```

## ✅ **Summary**

**YES!** The workflow absolutely works both ways:

- ✅ **AWS → Local**: Changes made in AWS sync back to macOS/Docker
- ✅ **Any Change Type**: UI, scoring, business logic, configuration
- ✅ **Git-Based**: Standard git pull/merge workflow
- ✅ **Automated Tools**: Scripts to make bidirectional sync easy
- ✅ **Consistent Environment**: Same codebase everywhere

You can develop locally, deploy to AWS, make changes in AWS, and sync them back to local - all seamlessly! 🚀
