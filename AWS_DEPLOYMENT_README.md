# CTIScraper AWS Deployment Guide

This guide provides step-by-step instructions for deploying CTIScraper to AWS using Terraform and ECS Fargate.

## Prerequisites

Before starting the deployment, ensure you have the following installed and configured:

### Required Tools
- **AWS CLI** (v2.x) - [Installation Guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html)
- **Terraform** (v1.0+) - [Installation Guide](https://learn.hashicorp.com/tutorials/terraform/install-cli)
- **Docker** - [Installation Guide](https://docs.docker.com/get-docker/)
- **Git** - [Installation Guide](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git)

### AWS Requirements
- AWS Account with appropriate permissions
- AWS CLI configured with credentials
- Domain name (optional, for custom domain)

### Required AWS Permissions
Your AWS user/role needs the following permissions:
- ECS (Full access)
- RDS (Full access)
- ElastiCache (Full access)
- VPC (Full access)
- IAM (Create roles and policies)
- S3 (Full access)
- ECR (Full access)
- CloudWatch (Full access)
- Secrets Manager (Full access)
- CodePipeline (Full access)
- CodeBuild (Full access)

## Quick Start

### 1. Clone and Setup
```bash
# Clone the repository
git clone https://github.com/dfirtnt/CTIScraper.git
cd CTIScraper

# Make deployment script executable
chmod +x deploy-aws.sh
```

### 2. Run Deployment Script
```bash
# Run the automated deployment script
./deploy-aws.sh
```

The script will:
- Check prerequisites
- Validate AWS credentials
- Prompt for configuration values
- Deploy infrastructure with Terraform
- Build and push Docker images
- Deploy ECS services
- Display deployment information

### 3. Access Your Application
After deployment completes, access your application at:
- **Web Application**: `http://<ALB_DNS_NAME>`
- **Health Check**: `http://<ALB_DNS_NAME>/health`
- **API Documentation**: `http://<ALB_DNS_NAME>/docs`

## Manual Deployment

If you prefer to deploy manually or need more control:

### 1. Configure Variables
```bash
cd terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars with your values
```

### 2. Initialize Terraform
```bash
terraform init
```

### 3. Plan Deployment
```bash
terraform plan
```

### 4. Apply Infrastructure
```bash
terraform apply
```

### 5. Build and Push Images
```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <ACCOUNT_ID>.dkr.ecr.us-east-1.amazonaws.com

# Build and push images
docker build -t cti-scraper .
docker tag cti-scraper:latest <ECR_REPO_URL>:latest
docker push <ECR_REPO_URL>:latest
```

### 6. Update ECS Services
```bash
# Force new deployment
aws ecs update-service --cluster <CLUSTER_NAME> --service <SERVICE_NAME> --force-new-deployment
```

## Configuration

### Environment Variables

Key environment variables that can be configured:

| Variable | Description | Default |
|----------|-------------|---------|
| `ENVIRONMENT` | Environment name (dev/staging/prod) | dev |
| `AWS_REGION` | AWS region | us-east-1 |
| `DB_PASSWORD` | Database password | Generated |
| `REDIS_PASSWORD` | Redis password | Generated |
| `OPENAI_API_KEY` | OpenAI API key | Optional |
| `DOMAIN_NAME` | Custom domain name | Optional |
| `ENABLE_OLLAMA` | Enable Ollama LLM service | false |

### Terraform Variables

Edit `terraform/variables.tf` to customize:

- **Compute Resources**: CPU and memory for services
- **Scaling**: Auto-scaling configuration
- **Storage**: Database and cache sizing
- **Security**: WAF, encryption, and access controls

## Architecture Overview

The deployment creates the following AWS resources:

### Compute Layer
- **ECS Cluster**: Container orchestration
- **ECS Services**: Web, Worker, Scheduler, Ollama (optional)
- **Application Load Balancer**: Traffic distribution
- **Auto Scaling**: Dynamic scaling based on metrics

### Data Layer
- **RDS PostgreSQL**: Primary database with Multi-AZ
- **ElastiCache Redis**: Task queue and caching
- **S3 Buckets**: Configuration and backup storage

### Networking
- **VPC**: Isolated network environment
- **Subnets**: Public, private, and database subnets
- **Security Groups**: Network access controls
- **NAT Gateways**: Outbound internet access

### Security
- **IAM Roles**: Service permissions
- **Secrets Manager**: Secure credential storage
- **WAF**: Web application firewall (optional)
- **Encryption**: Data at rest and in transit

### Monitoring
- **CloudWatch**: Logs, metrics, and alarms
- **X-Ray**: Distributed tracing (optional)
- **SNS**: Alert notifications

## Services

### Web Service
- **Purpose**: FastAPI web application and API
- **Resources**: 1 vCPU, 2 GB RAM
- **Scaling**: 2-10 instances based on load
- **Health Check**: `/health` endpoint

### Worker Service
- **Purpose**: Background task processing (Celery)
- **Resources**: 1 vCPU, 2 GB RAM
- **Scaling**: 2-5 instances based on queue depth
- **Tasks**: Content scraping, processing, analysis

### Scheduler Service
- **Purpose**: Periodic task scheduling (Celery Beat)
- **Resources**: 0.5 vCPU, 1 GB RAM
- **Instances**: 1 (single instance for consistency)
- **Tasks**: Source checks, cleanup, reports

### Ollama Service (Optional)
- **Purpose**: Local LLM for content analysis
- **Resources**: 4 vCPU, 16 GB RAM
- **Instances**: 1-2 based on usage
- **Model**: Mistral (configurable)

## Monitoring and Alerting

### CloudWatch Metrics
- **ECS**: CPU, memory, task count
- **RDS**: CPU, connections, storage
- **ElastiCache**: CPU, memory, connections
- **ALB**: Request count, response time, error rate

### CloudWatch Alarms
- **High CPU Usage**: >80% for 5 minutes
- **High Memory Usage**: >85% for 5 minutes
- **High Database Connections**: >80% for 5 minutes
- **Service Unavailable**: Health check failures

### Logging
- **Application Logs**: Structured JSON logs
- **Access Logs**: ALB request logs
- **System Logs**: ECS container logs
- **Retention**: 30 days (configurable)

## Security Best Practices

### Network Security
- Private subnets for application services
- Security groups with least privilege
- VPC Flow Logs enabled
- NAT Gateways for outbound access

### Data Security
- Encryption at rest and in transit
- Secrets Manager for sensitive data
- Regular security updates
- Backup encryption

### Application Security
- Non-root container user
- Minimal base image
- Security scanning in CI/CD
- WAF protection (optional)

## Cost Optimization

### Development Environment
- **Estimated Cost**: $120-215/month
- **Resources**: Smaller instances, single AZ
- **Features**: Basic monitoring, no WAF

### Production Environment
- **Estimated Cost**: $390-880/month
- **Resources**: Larger instances, Multi-AZ
- **Features**: Full monitoring, WAF, backups

### Cost Optimization Tips
- Use Spot instances for non-critical workloads
- Implement auto-scaling to match demand
- Enable S3 Intelligent Tiering
- Use CloudWatch Insights for log analysis
- Regular cleanup of unused resources

## Troubleshooting

### Common Issues

#### Service Won't Start
```bash
# Check ECS service events
aws ecs describe-services --cluster <CLUSTER_NAME> --services <SERVICE_NAME>

# Check task logs
aws logs get-log-events --log-group-name /aws/ecs/<SERVICE_NAME> --log-stream-name <STREAM_NAME>
```

#### Database Connection Issues
```bash
# Check RDS status
aws rds describe-db-instances --db-instance-identifier <DB_INSTANCE_ID>

# Test connection
aws rds describe-db-instances --db-instance-identifier <DB_INSTANCE_ID> --query 'DBInstances[0].Endpoint'
```

#### High Resource Usage
```bash
# Check CloudWatch metrics
aws cloudwatch get-metric-statistics --namespace AWS/ECS --metric-name CPUUtilization --dimensions Name=ServiceName,Value=<SERVICE_NAME> --start-time 2023-01-01T00:00:00Z --end-time 2023-01-01T23:59:59Z --period 300 --statistics Average
```

### Debugging Commands

#### View Service Logs
```bash
# Web service logs
aws logs tail /aws/ecs/cti-scraper-dev-web --follow

# Worker service logs
aws logs tail /aws/ecs/cti-scraper-dev-worker --follow
```

#### Check Service Health
```bash
# Service status
aws ecs describe-services --cluster <CLUSTER_NAME> --services <SERVICE_NAME>

# Task health
aws ecs describe-tasks --cluster <CLUSTER_NAME> --tasks <TASK_ARN>
```

#### Database Access
```bash
# Connect to database
aws rds describe-db-instances --db-instance-identifier <DB_INSTANCE_ID> --query 'DBInstances[0].Endpoint.Address'
```

## Maintenance

### Regular Tasks
- **Security Updates**: Monthly container image updates
- **Database Maintenance**: Weekly maintenance windows
- **Backup Verification**: Monthly backup restoration tests
- **Cost Review**: Monthly cost analysis and optimization

### Backup and Recovery
- **Database Backups**: Automated daily backups with 7-day retention
- **Application Data**: S3 versioning and cross-region replication
- **Configuration**: Infrastructure as Code (Terraform state)

### Scaling
- **Horizontal Scaling**: Auto-scaling based on CPU/memory metrics
- **Vertical Scaling**: Manual instance type changes
- **Database Scaling**: Read replicas for read-heavy workloads

## Support

### Documentation
- [AWS ECS Documentation](https://docs.aws.amazon.com/ecs/)
- [Terraform AWS Provider](https://registry.terraform.io/providers/hashicorp/aws/latest/docs)
- [CTIScraper Documentation](docs/README.md)

### Community
- [GitHub Issues](https://github.com/dfirtnt/CTIScraper/issues)
- [Discussions](https://github.com/dfirtnt/CTIScraper/discussions)

### Professional Support
For enterprise support and custom deployments, contact the development team.

## License

This deployment configuration is provided under the MIT License. See [LICENSE](LICENSE) for details.
