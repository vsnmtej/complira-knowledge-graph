# Complira Knowledge Graph - AWS Infrastructure
# Terraform configuration for production deployment

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Backend for state management (configure after initial setup)
  # backend "s3" {
  #   bucket         = "complira-terraform-state"
  #   key            = "prod/terraform.tfstate"
  #   region         = "us-east-1"
  #   encrypt        = true
  #   dynamodb_table = "complira-terraform-locks"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "Complira"
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

# ========== Variables ==========
variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Environment name (dev, staging, prod)"
  type        = string
  default     = "prod"
}

variable "project_name" {
  description = "Project name for resource naming"
  type        = string
  default     = "complira"
}

variable "vpc_cidr" {
  description = "CIDR block for VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "api_cpu" {
  description = "CPU units for API container (1024 = 1 vCPU)"
  type        = number
  default     = 2048  # 2 vCPUs
}

variable "api_memory" {
  description = "Memory for API container (MB)"
  type        = number
  default     = 4096  # 4 GB
}

variable "api_desired_count" {
  description = "Desired number of API tasks"
  type        = number
  default     = 2
}

variable "arangodb_instance_type" {
  description = "EC2 instance type for ArangoDB"
  type        = string
  default     = "m7i-flex.large"  # 2 vCPUs, 8 GB RAM (Intel-based, cost-effective for testing)
}

variable "domain_name" {
  description = "Domain name for the API (optional)"
  type        = string
  default     = ""
}

# ========== Data Sources ==========
data "aws_availability_zones" "available" {
  state = "available"
}

# ========== Outputs ==========
output "api_endpoint" {
  description = "API Load Balancer endpoint"
  value       = aws_lb.api.dns_name
}

output "arangodb_endpoint" {
  description = "ArangoDB endpoint"
  value       = aws_instance.arangodb.private_ip
}

output "redis_endpoint" {
  description = "Redis cluster endpoint"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
}

output "ecr_repository_url" {
  description = "ECR repository URL for API image"
  value       = aws_ecr_repository.api.repository_url
}
