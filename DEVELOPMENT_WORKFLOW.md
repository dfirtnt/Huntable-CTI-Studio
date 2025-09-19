# Development-to-AWS Workflow Guide

## Overview

Yes, the CTIScraper codebase is **highly modular** and perfectly suited for your development workflow! You can develop on macOS/Docker locally and seamlessly deploy changes to AWS. Here's how:

## 🏗️ **Modular Architecture Analysis**

### **UI Components** (Easy to modify)
```
src/web/
├── templates/           # HTML templates (Jinja2)
│   ├── base.html       # Base template
│   ├── dashboard.html  # Main dashboard
│   ├── articles.html   # Article listing
│   ├── article_detail.html  # Article detail page
│   └── sources.html    # Source management
├── static/
│   └── js/
│       └── annotation-manager.js  # Frontend JavaScript
└── modern_main.py      # FastAPI routes and endpoints
```

### **Scoring Logic** (Well-isolated)
```
src/utils/content.py
├── QualityScorer       # General content quality scoring
└── ThreatHuntingScorer # Threat hunting specific scoring

src/core/processor.py
└── ContentProcessor   # Main processing pipeline with scoring
```

### **Core Business Logic** (Modular)
```
src/core/
├── rss_parser.py      # RSS feed processing
├── modern_scraper.py  # Web scraping logic
├── processor.py       # Content processing & scoring
└── fetcher.py         # Content fetching orchestration
```

## 🔄 **Development Workflow**

### **1. Local Development (macOS/Docker)**

```bash
# Start local development environment
cd CTIScraper
./start.sh

# Make your changes to:
# - UI: src/web/templates/*.html
# - Frontend JS: src/web/static/js/*.js
# - Scoring: src/utils/content.py
# - Backend: src/web/modern_main.py

# Test locally
./run_tests.py
```

### **2. Git Workflow**

```bash
# Commit your changes
git add .
git commit -m "Update UI scoring logic and threat hunting algorithm"

# Push to your repository
git push origin main
```

### **3. AWS Deployment**

The AWS infrastructure I created supports **automatic deployment** via CI/CD:

```bash
# Option A: Automatic CI/CD (Recommended)
# Just push to git - CodePipeline will automatically:
# 1. Build new Docker images
# 2. Deploy to ECS
# 3. Update services

# Option B: Manual deployment
cd terraform
terraform apply  # Updates infrastructure if needed
./deploy-aws.sh  # Rebuilds and deploys containers
```

## 🎯 **Specific Areas You Can Modify**

### **UI Changes**
- **Templates**: Modify `src/web/templates/*.html` for layout, styling, functionality
- **JavaScript**: Update `src/web/static/js/*.js` for interactive features
- **Styling**: Add CSS classes (uses Tailwind CSS framework)
- **API Endpoints**: Modify routes in `src/web/modern_main.py`

### **Scoring Logic Changes**
- **Quality Scoring**: Modify `QualityScorer.score_article()` in `src/utils/content.py`
- **Threat Hunting Scoring**: Update `ThreatHuntingScorer.score_threat_hunting_content()`
- **Processing Pipeline**: Adjust `ContentProcessor` in `src/core/processor.py`
- **Scoring Weights**: Change scoring parameters and thresholds

### **Business Logic Changes**
- **Scraping Rules**: Modify `src/core/modern_scraper.py`
- **Content Processing**: Update `src/core/processor.py`
- **Data Models**: Extend `src/models/*.py` for new fields
- **Database Schema**: Update `src/database/models.py`

## 🚀 **Deployment Pipeline Configuration**

### **CI/CD Pipeline** (Already configured)
The Terraform creates a CodePipeline that:
1. **Monitors** your git repository
2. **Builds** Docker images when changes are pushed
3. **Deploys** automatically to ECS
4. **Updates** services with zero downtime

### **Environment Separation**
```bash
# Development environment
ENVIRONMENT=dev
# - Smaller instances
# - Debug logging
# - Single AZ

# Production environment  
ENVIRONMENT=prod
# - Larger instances
# - Multi-AZ
# - Production logging
```

## 📋 **Step-by-Step Workflow Example**

### **Scenario: Update Threat Hunting Scoring Algorithm**

1. **Local Development**:
```bash
# Edit scoring logic
vim src/utils/content.py
# Modify ThreatHuntingScorer.score_threat_hunting_content()

# Test locally
./run_tests.py
docker-compose up --build
```

2. **Commit Changes**:
```bash
git add src/utils/content.py
git commit -m "Improve threat hunting scoring algorithm"
git push origin main
```

3. **Automatic Deployment**:
- CodePipeline detects the push
- Builds new Docker image with your changes
- Deploys to ECS automatically
- Your AWS environment now has the updated scoring!

### **Scenario: Update UI Dashboard**

1. **Local Development**:
```bash
# Edit dashboard template
vim src/web/templates/dashboard.html
# Add new metrics, charts, or functionality

# Test locally
docker-compose up --build
# Visit http://localhost:8000
```

2. **Commit & Deploy**:
```bash
git add src/web/templates/dashboard.html
git commit -m "Add new threat intelligence metrics to dashboard"
git push origin main
# AWS automatically updates!
```

## 🔧 **Configuration Management**

### **Environment-Specific Settings**
```bash
# Local development
.env.local

# AWS development
env.aws (already created)

# Production
terraform/variables.tf
```

### **Secrets Management**
- **Local**: `.env` file
- **AWS**: AWS Secrets Manager (automatically configured)
- **Database passwords, API keys**: Stored securely in AWS

## 📊 **Monitoring Your Changes**

### **Local Monitoring**
```bash
# View logs
docker-compose logs -f web
docker-compose logs -f worker

# Check metrics
curl http://localhost:8000/health
```

### **AWS Monitoring**
- **CloudWatch Logs**: Automatic log aggregation
- **CloudWatch Metrics**: Performance monitoring
- **Health Checks**: Automatic service health monitoring
- **Alarms**: Get notified of issues

## 🛠️ **Development Tools Integration**

### **VS Code Integration**
```json
// .vscode/settings.json
{
    "python.defaultInterpreterPath": "./venv/bin/python",
    "python.linting.enabled": true,
    "python.formatting.provider": "black"
}
```

### **Docker Development**
```bash
# Hot reload for development
docker-compose up --build

# Run specific tests
docker-compose run --rm web pytest tests/test_scoring.py
```

## 🔄 **Database Schema Changes**

If you need to modify the database schema:

1. **Update Models**: Modify `src/database/models.py`
2. **Create Migration**: Use Alembic for schema changes
3. **Test Locally**: Verify changes work
4. **Deploy**: AWS RDS will handle migrations automatically

## 🎯 **Best Practices**

### **Code Organization**
- Keep UI changes in `src/web/`
- Keep scoring logic in `src/utils/content.py`
- Keep business logic in `src/core/`
- Use proper git commit messages

### **Testing**
- Test locally before pushing
- Use the existing test suite
- Add new tests for new functionality

### **Deployment**
- Use feature branches for major changes
- Test in development environment first
- Monitor AWS CloudWatch after deployment

## 🚨 **Troubleshooting**

### **Common Issues**
1. **Build Failures**: Check Docker logs in CodeBuild
2. **Service Won't Start**: Check ECS service events
3. **Database Issues**: Verify RDS connectivity
4. **Scoring Problems**: Check CloudWatch logs

### **Debug Commands**
```bash
# Check AWS service status
aws ecs describe-services --cluster cti-scraper-dev-cluster

# View recent logs
aws logs tail /aws/ecs/cti-scraper-dev-web --follow

# Check deployment status
aws codepipeline get-pipeline-state --name cti-scraper-dev-pipeline
```

## ✅ **Summary**

**Yes, the codebase is perfectly modular for your workflow!**

- ✅ **UI Changes**: Easy to modify templates and JavaScript
- ✅ **Scoring Logic**: Well-isolated in dedicated classes
- ✅ **Git Integration**: Seamless local-to-AWS deployment
- ✅ **CI/CD Pipeline**: Automatic deployment on git push
- ✅ **Environment Separation**: Dev and prod configurations
- ✅ **Monitoring**: Full observability in AWS

You can develop locally on macOS/Docker, commit changes, and they'll automatically deploy to AWS with zero manual intervention!
