# AWS Deployment Plan for CTIScraper

## Executive Summary

This document outlines a comprehensive AWS deployment strategy for CTIScraper, a modern threat intelligence collection and analysis platform. The deployment leverages AWS managed services for scalability, reliability, and security while maintaining the application's core functionality.

## Current Architecture Analysis

### Application Components
- **FastAPI Web Application** (Python 3.11) - Main web interface and API
- **PostgreSQL Database** - Primary data storage with async support
- **Redis Cache** - Celery task queue and caching
- **Celery Workers** - Background task processing for content scraping
- **Celery Beat Scheduler** - Periodic task scheduling
- **Ollama LLM Service** - Local LLM for content analysis
- **Nginx Reverse Proxy** - Load balancing and SSL termination

### Key Features
- RSS + web scraping with structured data extraction
- Content processing: cleaning, normalization, hashing, deduplication
- Robots.txt compliance with per-source configuration
- Source tiering system (premium/standard/basic)
- Async FastAPI with dashboards and JSON APIs
- Background task processing with Celery

## AWS Infrastructure Design

### 1. Compute Layer - Amazon ECS with Fargate

**Web Application Service**
- **Service Type**: ECS Fargate
- **CPU**: 1 vCPU
- **Memory**: 2 GB
- **Desired Count**: 2-10 (auto-scaling)
- **Health Check**: `/health` endpoint
- **Load Balancer**: Application Load Balancer (ALB)

**Worker Service**
- **Service Type**: ECS Fargate
- **CPU**: 1 vCPU
- **Memory**: 2 GB
- **Desired Count**: 2-5 (auto-scaling based on queue depth)
- **Task Definition**: Separate from web service

**Scheduler Service**
- **Service Type**: ECS Fargate
- **CPU**: 0.5 vCPU
- **Memory**: 1 GB
- **Desired Count**: 1 (single instance for consistency)

**Ollama LLM Service**
- **Service Type**: ECS Fargate
- **CPU**: 4 vCPU
- **Memory**: 16 GB
- **Desired Count**: 1-2 (based on usage)
- **GPU**: Consider EC2 with GPU instances for better performance

### 2. Database Layer - Amazon RDS

**PostgreSQL Database**
- **Engine**: PostgreSQL 15.x
- **Instance Class**: db.t3.medium (2 vCPU, 4 GB RAM)
- **Storage**: 100 GB GP3 with auto-scaling
- **Multi-AZ**: Enabled for high availability
- **Backup**: 7-day retention with point-in-time recovery
- **Encryption**: At rest and in transit

**Connection Pooling**: Consider RDS Proxy for connection management

### 3. Caching Layer - Amazon ElastiCache

**Redis Cluster**
- **Engine**: Redis 7.x
- **Node Type**: cache.t3.micro (1 vCPU, 0.5 GB RAM)
- **Cluster Mode**: Disabled (single node for Celery)
- **Backup**: Daily snapshots
- **Encryption**: At rest and in transit

### 4. Storage Layer - Amazon S3

**Application Data**
- **Bucket**: `cti-scraper-data-{environment}`
- **Purpose**: Configuration files, logs, backups
- **Encryption**: AES-256
- **Lifecycle**: Intelligent tiering

**Container Images**
- **Registry**: Amazon ECR
- **Repositories**: 
  - `cti-scraper/web`
  - `cti-scraper/worker`
  - `cti-scraper/scheduler`
  - `cti-scraper/ollama`

### 5. Networking Layer

**VPC Configuration**
- **CIDR**: 10.0.0.0/16
- **Public Subnets**: 2 AZs (10.0.1.0/24, 10.0.2.0/24)
- **Private Subnets**: 2 AZs (10.0.11.0/24, 10.0.12.0/24)
- **Database Subnets**: 2 AZs (10.0.21.0/24, 10.0.22.0/24)

**Security Groups**
- **ALB-SG**: Allow HTTP/HTTPS from internet
- **Web-SG**: Allow traffic from ALB-SG
- **Worker-SG**: Allow outbound to RDS and ElastiCache
- **RDS-SG**: Allow PostgreSQL from Web-SG and Worker-SG
- **Redis-SG**: Allow Redis from Web-SG and Worker-SG

**Load Balancer**
- **Type**: Application Load Balancer
- **Scheme**: Internet-facing
- **SSL Certificate**: ACM certificate
- **Health Check**: `/health` endpoint

### 6. Monitoring and Logging

**CloudWatch**
- **Log Groups**: 
  - `/aws/ecs/cti-scraper/web`
  - `/aws/ecs/cti-scraper/worker`
  - `/aws/ecs/cti-scraper/scheduler`
- **Metrics**: ECS service metrics, RDS metrics, ElastiCache metrics
- **Dashboards**: Custom dashboard for application monitoring
- **Alarms**: CPU, memory, error rate, database connections

**X-Ray Tracing**
- **Service**: AWS X-Ray for distributed tracing
- **Integration**: FastAPI and Celery tracing

### 7. Security and Compliance

**IAM Roles**
- **ECS Task Role**: Access to S3, CloudWatch, X-Ray
- **ECS Execution Role**: Access to ECR, CloudWatch Logs
- **RDS Role**: Enhanced monitoring

**Secrets Management**
- **AWS Secrets Manager**: Database credentials, API keys
- **Environment Variables**: Non-sensitive configuration

**Network Security**
- **WAF**: AWS WAF for web application protection
- **VPC Flow Logs**: Network traffic monitoring
- **Security Groups**: Least privilege access

## Deployment Strategy

### Phase 1: Infrastructure Setup
1. **VPC and Networking**
   - Create VPC with public/private subnets
   - Set up security groups and NACLs
   - Configure Application Load Balancer

2. **Database and Cache**
   - Deploy RDS PostgreSQL instance
   - Deploy ElastiCache Redis cluster
   - Configure backup and monitoring

3. **Container Registry**
   - Create ECR repositories
   - Set up image scanning and lifecycle policies

### Phase 2: Application Deployment
1. **Container Images**
   - Build and push Docker images to ECR
   - Create ECS task definitions
   - Configure environment variables and secrets

2. **ECS Services**
   - Deploy web application service
   - Deploy worker service
   - Deploy scheduler service
   - Deploy Ollama service (optional)

3. **Load Balancer Configuration**
   - Configure ALB target groups
   - Set up SSL certificate
   - Configure health checks

### Phase 3: Monitoring and Optimization
1. **CloudWatch Setup**
   - Create log groups and streams
   - Set up custom metrics and dashboards
   - Configure alarms and notifications

2. **Performance Optimization**
   - Implement auto-scaling policies
   - Optimize database queries
   - Configure caching strategies

3. **Security Hardening**
   - Enable WAF rules
   - Implement secrets rotation
   - Set up compliance monitoring

## Cost Estimation (Monthly)

### Development Environment
- **ECS Fargate**: ~$50-100 (low usage)
- **RDS PostgreSQL**: ~$30-50 (db.t3.small)
- **ElastiCache Redis**: ~$15-25 (cache.t3.micro)
- **ALB**: ~$20-30
- **S3**: ~$5-10
- **Total**: ~$120-215/month

### Production Environment
- **ECS Fargate**: ~$200-500 (higher usage)
- **RDS PostgreSQL**: ~$100-200 (db.t3.medium)
- **ElastiCache Redis**: ~$50-100 (cache.t3.small)
- **ALB**: ~$20-30
- **S3**: ~$20-50
- **Total**: ~$390-880/month

## Migration Considerations

### Data Migration
1. **Database Migration**
   - Export existing PostgreSQL data
   - Import to RDS with minimal downtime
   - Verify data integrity

2. **Configuration Migration**
   - Move configuration files to S3
   - Update environment variables
   - Test configuration changes

### Application Modifications
1. **Environment Variables**
   - Update database connection strings
   - Configure Redis connection
   - Set up logging configuration

2. **Health Checks**
   - Implement proper health check endpoints
   - Configure readiness and liveness probes
   - Set up graceful shutdown

## Security Best Practices

### Network Security
- Use private subnets for application services
- Implement least privilege security groups
- Enable VPC Flow Logs for monitoring

### Data Security
- Encrypt data at rest and in transit
- Use AWS Secrets Manager for sensitive data
- Implement proper backup and recovery procedures

### Application Security
- Regular security updates and patches
- Implement proper authentication and authorization
- Use AWS WAF for web application protection

## Monitoring and Alerting

### Key Metrics
- **Application Metrics**: Response time, error rate, throughput
- **Infrastructure Metrics**: CPU, memory, disk usage
- **Database Metrics**: Connection count, query performance
- **Business Metrics**: Articles processed, sources active

### Alerting Strategy
- **Critical Alerts**: Service down, database unavailable
- **Warning Alerts**: High CPU/memory usage, slow queries
- **Info Alerts**: Deployment notifications, scaling events

## Disaster Recovery

### Backup Strategy
- **Database**: Automated daily backups with 7-day retention
- **Application Data**: S3 versioning and cross-region replication
- **Configuration**: Infrastructure as Code (Terraform/CloudFormation)

### Recovery Procedures
- **RTO**: 4-8 hours for full recovery
- **RPO**: 24 hours maximum data loss
- **Testing**: Quarterly disaster recovery drills

## Next Steps

1. **Infrastructure as Code**: Create Terraform/CloudFormation templates
2. **CI/CD Pipeline**: Set up CodePipeline with automated testing
3. **Monitoring Setup**: Implement comprehensive monitoring and alerting
4. **Security Review**: Conduct security assessment and compliance review
5. **Performance Testing**: Load testing and optimization
6. **Documentation**: Create operational runbooks and procedures

## Conclusion

This AWS deployment plan provides a scalable, secure, and cost-effective solution for hosting CTIScraper in the cloud. The architecture leverages AWS managed services to reduce operational overhead while maintaining high availability and performance. The phased approach allows for gradual migration and testing, minimizing risk and ensuring a smooth transition to the cloud.
