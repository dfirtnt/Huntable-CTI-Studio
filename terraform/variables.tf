# Terraform Variables for CTIScraper

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "dev"
  
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be one of: dev, staging, prod."
  }
}

variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name"
  type        = string
  default     = "cti-scraper"
}

variable "db_password" {
  description = "Database password"
  type        = string
  sensitive   = true
}

variable "redis_password" {
  description = "Redis password"
  type        = string
  sensitive   = true
  default     = ""
}

variable "openai_api_key" {
  description = "OpenAI API key"
  type        = string
  sensitive   = true
  default     = ""
}

variable "domain_name" {
  description = "Domain name for the application"
  type        = string
  default     = ""
}

variable "certificate_arn" {
  description = "ACM certificate ARN for HTTPS"
  type        = string
  default     = ""
}

variable "web_cpu" {
  description = "CPU units for web service"
  type        = number
  default     = 1024
}

variable "web_memory" {
  description = "Memory for web service"
  type        = number
  default     = 2048
}

variable "worker_cpu" {
  description = "CPU units for worker service"
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Memory for worker service"
  type        = number
  default     = 2048
}

variable "scheduler_cpu" {
  description = "CPU units for scheduler service"
  type        = number
  default     = 512
}

variable "scheduler_memory" {
  description = "Memory for scheduler service"
  type        = number
  default     = 1024
}

variable "web_desired_count" {
  description = "Desired number of web service instances"
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Desired number of worker service instances"
  type        = number
  default     = 2
}

variable "enable_ollama" {
  description = "Enable Ollama LLM service"
  type        = bool
  default     = false
}

variable "ollama_cpu" {
  description = "CPU units for Ollama service"
  type        = number
  default     = 4096
}

variable "ollama_memory" {
  description = "Memory for Ollama service"
  type        = number
  default     = 16384
}

variable "enable_auto_scaling" {
  description = "Enable auto scaling for services"
  type        = bool
  default     = true
}

variable "min_capacity" {
  description = "Minimum capacity for auto scaling"
  type        = number
  default     = 1
}

variable "max_capacity" {
  description = "Maximum capacity for auto scaling"
  type        = number
  default     = 10
}

variable "backup_retention_days" {
  description = "Database backup retention in days"
  type        = number
  default     = 7
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 30
}

variable "enable_waf" {
  description = "Enable AWS WAF"
  type        = bool
  default     = false
}

variable "enable_xray" {
  description = "Enable AWS X-Ray tracing"
  type        = bool
  default     = true
}

variable "tags" {
  description = "Additional tags to apply to resources"
  type        = map(string)
  default     = {}
}
