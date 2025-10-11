# AWS Migration Plan - Cost-Optimized Architecture

## Executive Summary

**Target Budget**: <$200/month  
**Usage Pattern**: Single-user/small team, ~1000 articles/month, business hours availability  
**Estimated Monthly Cost**: **$130-175/month**

## Current Architecture Analysis

**Current Components**:
- PostgreSQL with pgvector (768-dim embeddings for articles + annotations)
- Redis (Celery broker, caching)
- FastAPI web application (80+ endpoints)
- Celery worker + scheduler (30-min source checks, daily maintenance)
- Ollama LLM (8-16GB memory requirement)
- 5 containers total

**Resource Usage**:
- Database: ~5-10GB (articles, embeddings, source data)
- Redis: <1GB
- Application: ~2GB per container
- Ollama: 8-16GB memory (LARGEST cost driver in current setup)

## Proposed AWS Architecture

### Architecture Diagram
```
┌─────────────────────────────────────────────────────────────────┐
│                        CloudFront (Optional)                     │
│                    CDN + Static Assets Caching                   │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│              Application Load Balancer (ALB)                     │
│              SSL/TLS Termination + Path Routing                  │
└────────────────────────────────┬────────────────────────────────┘
                                 │
                ┌────────────────┴────────────────┐
                ▼                                 ▼
┌──────────────────────────────┐    ┌──────────────────────────────┐
│   ECS Fargate (Web)          │    │   ECS Fargate (Worker)       │
│   - FastAPI Application      │    │   - Celery Worker            │
│   - 0.5 vCPU, 1GB RAM        │    │   - Celery Beat              │
│   - Auto-scaling (1-2 tasks) │    │   - 0.5 vCPU, 1GB RAM        │
└──────────────┬───────────────┘    └──────────────┬───────────────┘
               │                                   │
               └───────────────┬───────────────────┘
                               │
        ┌──────────────────────┼──────────────────────┐
        ▼                      ▼                      ▼
┌────────────────┐    ┌────────────────┐    ┌────────────────┐
│ RDS PostgreSQL │    │ ElastiCache    │    │  AWS Bedrock   │
│   db.t4g.micro │    │   Redis        │    │  (On-Demand)   │
│   20GB gp3     │    │ cache.t4g.micro│    │ Claude Haiku   │
│   Single-AZ    │    │   1GB memory   │    │ or Llama 3.2   │
└────────────────┘    └────────────────┘    └────────────────┘
```

### Component Breakdown

#### 1. **Compute: AWS ECS Fargate** (Serverless Containers)
- **Web Service**: 0.5 vCPU, 1GB RAM (1-2 tasks with auto-scaling)
- **Worker Service**: 0.5 vCPU, 1GB RAM (1 task)
- **Benefits**: 
  - No EC2 instance management
  - Pay only for running time
  - Can schedule worker to run only during business hours
- **Cost**: ~$25-35/month (with business hours optimization)

#### 2. **Database: Amazon RDS PostgreSQL**
- **Instance**: db.t4g.micro (2 vCPU, 1GB RAM) with Graviton2 (ARM-based, 20% cheaper)
- **Storage**: 20GB gp3 (upgradable to 100GB as needed)
- **Configuration**: Single-AZ (Multi-AZ adds ~$15/month if needed later)
- **pgvector**: Install via RDS parameter groups + extensions
- **Cost**: ~$15-18/month (instance) + $2/month (storage) = **$17-20/month**

#### 3. **Cache: Amazon ElastiCache for Redis**
- **Instance**: cache.t4g.micro (0.5GB memory)
- **Purpose**: Celery broker, session caching, task results
- **Alternative**: Consider Amazon MemoryDB for Redis Serverless (pay-per-request)
- **Cost**: ~$12-15/month

#### 4. **LLM: AWS Bedrock** (RECOMMENDED REPLACEMENT FOR OLLAMA)
- **Model Options**:
  - **Claude 3 Haiku**: $0.25/1M input tokens, $1.25/1M output tokens
  - **Llama 3.2 (3B)**: $0.15/1M input tokens, $0.60/1M output tokens
- **Estimated Usage**: 1000 articles/month × 5 API calls/article × 2K tokens = 10M tokens/month
- **Cost**: ~$15-25/month (vs $80-120/month for EC2 to run Ollama)
- **Benefits**: 
  - No infrastructure to manage
  - Pay only for what you use
  - Better models than Llama 3.2 1B
  - Sub-second response times

#### 5. **Load Balancer: Application Load Balancer (ALB)**
- **Purpose**: SSL termination, path-based routing, health checks
- **Cost**: ~$16/month (base) + $0.008/LCU-hour (minimal for your traffic)
- **Total**: ~$20-25/month

#### 6. **Storage: Amazon S3**
- **Purpose**: Backups, logs, ML models, static assets
- **Storage**: ~5GB backups + 1GB logs = 6GB
- **Requests**: Minimal (daily backups, occasional retrieval)
- **Cost**: ~$0.15-0.50/month

#### 7. **Networking: VPC, NAT Gateway (Optimized)**
- **VPC**: Free
- **NAT Gateway**: $32/month (EXPENSIVE!)
- **OPTIMIZATION**: Use VPC Endpoints for AWS services (S3, Bedrock, Secrets Manager)
  - Reduces/eliminates NAT Gateway needs
  - VPC Endpoints: ~$7-10/month (much cheaper)
- **Cost with optimization**: ~$10-15/month

#### 8. **Secrets Management: AWS Secrets Manager**
- **Purpose**: Database passwords, API keys, Redis password
- **Cost**: $0.40/secret/month × 5 secrets = $2/month

#### 9. **Monitoring: CloudWatch**
- **Logs**: 5GB ingestion + 5GB storage
- **Metrics**: Standard metrics (free) + custom metrics
- **Alarms**: 10 alarms (3 free, 7 × $0.10 = $0.70)
- **Cost**: ~$5-8/month

#### 10. **Optional: CloudFront CDN**
- **Purpose**: Static assets, reduced latency for dashboard
- **Cost**: ~$1-3/month (minimal traffic)
- **Recommendation**: Add only if users are geographically distributed

## Monthly Cost Breakdown

| Service | Configuration | Monthly Cost |
|---------|--------------|--------------|
| **ECS Fargate (Web)** | 0.5 vCPU, 1GB × 1-2 tasks × 730 hrs | $20-30 |
| **ECS Fargate (Worker)** | 0.5 vCPU, 1GB × 1 task × 12 hrs/day | $10-15 |
| **RDS PostgreSQL** | db.t4g.micro + 20GB gp3 | $17-20 |
| **ElastiCache Redis** | cache.t4g.micro | $12-15 |
| **AWS Bedrock (LLM)** | Claude Haiku or Llama 3.2 | $15-25 |
| **Application Load Balancer** | Standard ALB | $20-25 |
| **VPC Endpoints** | S3, Bedrock, Secrets Manager | $10-15 |
| **S3 Storage** | Backups, logs, models | $0.50 |
| **Secrets Manager** | 5 secrets | $2 |
| **CloudWatch** | Logs, metrics, alarms | $5-8 |
| **Data Transfer** | Outbound (minimal) | $1-3 |
| **TOTAL** | | **$113-158/month** |

**With buffer for overages**: **$130-175/month**

## Cost Optimization Strategies

### Immediate Optimizations (Included Above)
1. **ARM-based instances** (Graviton2): 20% cheaper than x86
2. **Business hours scheduling**: Worker runs only 12 hrs/day (saves ~$10/month)
3. **VPC Endpoints**: Avoid NAT Gateway costs (saves ~$20/month)
4. **AWS Bedrock over EC2**: Eliminates $80-120/month EC2 instance for Ollama
5. **Single-AZ RDS**: Acceptable for business hours availability (saves ~$15/month)

### Additional Cost Savings (If Needed)
1. **Savings Plans**: 1-year commitment = 17% savings, 3-year = 42% savings
2. **Reserved Instances**: For RDS/ElastiCache (saves ~20-30%)
3. **S3 Lifecycle Policies**: Move old backups to Glacier (saves ~70% on storage)
4. **CloudWatch Logs**: Reduce retention to 7 days (saves ~$2-3/month)
5. **Fargate Spot**: For non-critical worker tasks (saves up to 70%)

### Scale-Up Path (When Budget Increases)
1. Add Multi-AZ for RDS (+$15/month) → 99.95% availability
2. Add second worker task (+$15/month) → Faster processing
3. Upgrade RDS to db.t4g.small (+$15/month) → Better performance
4. Add CloudFront CDN (+$5-10/month) → Faster page loads
5. Enable RDS automated backups to S3 (+$2/month)

## Migration Implementation Plan

### Phase 1: Infrastructure Setup (Week 1)
1. Create VPC with public/private subnets across 2 AZs
2. Set up VPC Endpoints (S3, Bedrock, Secrets Manager)
3. Provision RDS PostgreSQL with pgvector extension
4. Provision ElastiCache Redis cluster
5. Create S3 buckets (backups, logs, static assets)
6. Set up Secrets Manager for credentials

### Phase 2: Application Migration (Week 2)
1. Update Docker images for AWS deployment
2. Create ECS Task Definitions for web + worker
3. Update application configuration for AWS services
4. Replace Ollama integration with AWS Bedrock SDK
5. Set up ALB with target groups and health checks
6. Configure ECS Services with auto-scaling policies

### Phase 3: Data Migration (Week 3)
1. Export current PostgreSQL database
2. Import to RDS using `pg_restore`
3. Verify data integrity and embeddings
4. Test Redis connectivity from ECS
5. Upload ML models and configs to S3

### Phase 4: Testing & Validation (Week 4)
1. Run health checks on all endpoints
2. Test source collection and article processing
3. Verify Celery worker execution
4. Test AWS Bedrock integration (summaries, SIGMA rules)
5. Performance testing under expected load
6. Backup and restore testing

### Phase 5: Deployment & Monitoring (Week 5)
1. Set up CloudWatch dashboards
2. Configure alarms (CPU, memory, error rates)
3. Enable AWS Cost Explorer alerts
4. Update DNS to point to ALB
5. Monitor for 48 hours before decommissioning old infrastructure
6. Document runbooks and troubleshooting guides

## Code Changes Required

### 1. Environment Configuration (`env.example`)
```bash
# AWS-specific configuration
AWS_REGION=us-east-1
AWS_ACCOUNT_ID=your-account-id

# RDS PostgreSQL
DATABASE_URL=postgresql+asyncpg://${POSTGRES_USER}:${POSTGRES_PASSWORD}@rds-endpoint:5432/cti_scraper

# ElastiCache Redis
REDIS_URL=redis://elasticache-endpoint:6379/0

# AWS Bedrock (replaces Ollama)
AWS_BEDROCK_REGION=us-east-1
AWS_BEDROCK_MODEL_ID=anthropic.claude-3-haiku-20240307-v1:0
# Alternative: meta.llama3-2-3b-instruct-v1:0

# S3 Buckets
S3_BACKUP_BUCKET=ctiscraper-backups
S3_LOGS_BUCKET=ctiscraper-logs
S3_MODELS_BUCKET=ctiscraper-models
```

### 2. Create AWS Bedrock Integration (`src/services/bedrock_service.py`)
New file to replace Ollama integration with AWS Bedrock:
- Support for Claude Haiku and Llama 3.2
- Token counting and cost tracking
- Rate limiting and error handling
- Drop-in replacement for existing LLM calls

### 3. Update Celery Configuration
- Use ElastiCache endpoint for broker/backend
- Configure business hours schedule (8am-6pm weekdays)
- Add CloudWatch Logs handler

### 4. Update Health Check Endpoints
- Add RDS connection health check
- Add ElastiCache health check
- Add AWS Bedrock availability check
- Add CloudWatch metrics publishing

### 5. Docker Image Optimization
- Multi-stage builds for smaller images
- Use AWS ECR for container registry
- Install AWS SDK dependencies (boto3)
- Remove Ollama-specific dependencies

### 6. Infrastructure as Code (Terraform/CloudFormation)
Create IaC templates for:
- VPC and networking
- RDS and ElastiCache
- ECS cluster, task definitions, services
- ALB and target groups
- S3 buckets and IAM roles
- CloudWatch dashboards and alarms

## Risk Mitigation

### Technical Risks
1. **pgvector on RDS**: Verify extension availability in target RDS version (PostgreSQL 15+)
   - Mitigation: Test on RDS free tier first
2. **AWS Bedrock Quotas**: Default quotas may be low for new accounts
   - Mitigation: Request quota increase during setup
3. **Network latency**: RDS/ElastiCache in private subnets
   - Mitigation: Place all services in same VPC and AZ

### Cost Risks
1. **NAT Gateway surprise costs**: Can be $32/month if not optimized
   - Mitigation: Use VPC Endpoints for all AWS services
2. **Data transfer costs**: Can accumulate unexpectedly
   - Mitigation: Keep everything in same region, use VPC Endpoints
3. **CloudWatch Logs**: Can grow quickly
   - Mitigation: Set 7-day retention, use log filters

### Operational Risks
1. **Single-AZ database**: No automatic failover
   - Mitigation: Manual backups to S3, documented restore procedure
2. **Limited budget for scaling**: May hit limits under load
   - Mitigation: Implement rate limiting, queue depth monitoring

## Alternative Architectures Considered

### Option B: EC2 with Ollama (NOT RECOMMENDED)
- **Cost**: ~$220-250/month (exceeds budget)
- **Reason**: t3a.xlarge (4 vCPU, 16GB) needed for Ollama = $100-120/month alone
- **Pros**: Full control, no per-request LLM costs
- **Cons**: Expensive, requires management, exceeds budget

### Option C: Serverless (Aurora Serverless + Lambda)
- **Cost**: ~$180-220/month
- **Reason**: Aurora Serverless v2 minimum is ~$90/month
- **Pros**: True serverless, auto-scaling
- **Cons**: Higher costs, Lambda cold starts for web app, complex migration

### Option D: Lightsail (Simple Stack)
- **Cost**: ~$90-120/month
- **Reason**: 2GB instance ($10) + 4GB instance ($20) + Managed DB ($15) + Load Balancer ($18)
- **Pros**: Simplest, predictable pricing
- **Cons**: No pgvector support, limited scalability, no auto-scaling, no managed Redis

## Recommended Architecture: ECS Fargate + RDS + Bedrock

**Why this is optimal for your requirements**:
1. ✅ Under $200/month budget
2. ✅ Eliminates Ollama infrastructure costs
3. ✅ Business hours optimization available
4. ✅ Managed services (less operational burden)
5. ✅ Scales up easily when budget allows
6. ✅ pgvector support via RDS PostgreSQL
7. ✅ AWS Bedrock provides better LLM quality than Ollama Llama 3.2 1B
8. ✅ Pay-per-use LLM pricing aligns with 1000 articles/month usage

## Implementation Tasks

### Infrastructure Setup
- [ ] Create VPC with public/private subnets across 2 AZs
- [ ] Set up VPC Endpoints (S3, Bedrock, Secrets Manager)
- [ ] Provision RDS PostgreSQL with pgvector extension and test connectivity
- [ ] Provision ElastiCache Redis cluster and configure security groups
- [ ] Create S3 buckets for backups, logs, and ML models with lifecycle policies
- [ ] Request and verify AWS Bedrock access for Claude Haiku or Llama 3.2

### Application Migration
- [ ] Create AWS Bedrock service integration to replace Ollama calls
- [ ] Update Dockerfiles for AWS deployment: multi-stage builds, boto3, remove Ollama deps
- [ ] Update environment configuration for AWS services (RDS, ElastiCache, Bedrock, S3)
- [ ] Create ECS task definitions for web and worker services with proper resource limits
- [ ] Configure Application Load Balancer with SSL, health checks, and target groups
- [ ] Create ECS services with auto-scaling policies and business hours scheduling

### Data Migration
- [ ] Export current database and import to RDS, verify embeddings and data integrity

### Testing & Monitoring
- [ ] Set up CloudWatch dashboards, alarms, and cost alerts
- [ ] Execute full testing suite: health checks, source collection, worker tasks, Bedrock integration

### Documentation
- [ ] Create Terraform/CloudFormation templates for infrastructure reproducibility
- [ ] Document deployment procedures, troubleshooting guides, and rollback plans

## Next Steps

1. **Review and approve this plan**
2. **Set up AWS account** (if not already done)
3. **Request AWS Bedrock access** (may take 24-48 hours)
4. **Create Phase 1 infrastructure** using Terraform/CloudFormation
5. **Begin code modifications** for AWS integration
6. **Test migration on staging environment**
7. **Execute production cutover** during low-usage window

---

**Note**: This plan targets a single-user/small team deployment with business hours availability. For production environments with higher availability requirements, consider Multi-AZ RDS and additional redundancy measures.
