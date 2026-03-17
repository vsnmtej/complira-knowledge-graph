#!/bin/bash
# AWS Deployment Script for Complira Knowledge Graph
#
# Prerequisites:
# - AWS CLI configured with appropriate credentials
# - Docker installed
# - Terraform installed (>= 1.6.0)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
AWS_REGION=${AWS_REGION:-us-east-1}
ENVIRONMENT=${ENVIRONMENT:-prod}
PROJECT_NAME="complira"

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Complira AWS Deployment${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Step 1: Validate prerequisites
echo -e "${YELLOW}[1/6] Validating prerequisites...${NC}"

# Check AWS CLI
if ! command -v aws &> /dev/null; then
    echo -e "${RED}✗ AWS CLI not found. Please install it first.${NC}"
    exit 1
fi

# Check Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}✗ Docker not found. Please install it first.${NC}"
    exit 1
fi

# Check Terraform
if ! command -v terraform &> /dev/null; then
    echo -e "${RED}✗ Terraform not found. Please install it first.${NC}"
    exit 1
fi

# Verify AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}✗ AWS credentials not configured. Run 'aws configure' first.${NC}"
    exit 1
fi

AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${GREEN}✓ AWS Account: $AWS_ACCOUNT_ID${NC}"
echo -e "${GREEN}✓ Region: $AWS_REGION${NC}"
echo ""

# Step 2: Initialize Terraform
echo -e "${YELLOW}[2/6] Initializing Terraform...${NC}"
cd terraform
terraform init
echo -e "${GREEN}✓ Terraform initialized${NC}"
echo ""

# Step 3: Plan infrastructure
echo -e "${YELLOW}[3/6] Planning infrastructure...${NC}"
terraform plan \
  -var="aws_region=$AWS_REGION" \
  -var="environment=$ENVIRONMENT" \
  -out=tfplan
echo ""

# Confirm deployment
read -p "Do you want to proceed with deployment? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo -e "${RED}Deployment cancelled.${NC}"
    exit 0
fi
echo ""

# Step 4: Apply infrastructure
echo -e "${YELLOW}[4/6] Deploying infrastructure...${NC}"
terraform apply tfplan
echo -e "${GREEN}✓ Infrastructure deployed${NC}"
echo ""

# Get outputs
ECR_REPOSITORY=$(terraform output -raw ecr_repository_url)
echo -e "${GREEN}✓ ECR Repository: $ECR_REPOSITORY${NC}"
echo ""

# Step 5: Build and push Docker image
echo -e "${YELLOW}[5/6] Building and pushing Docker image...${NC}"
cd ..

# Login to ECR
aws ecr get-login-password --region $AWS_REGION | \
    docker login --username AWS --password-stdin $ECR_REPOSITORY

# Build image
docker build -t ${PROJECT_NAME}-api:latest .

# Tag image
docker tag ${PROJECT_NAME}-api:latest $ECR_REPOSITORY:latest
docker tag ${PROJECT_NAME}-api:latest $ECR_REPOSITORY:$(git rev-parse --short HEAD)

# Push image
docker push $ECR_REPOSITORY:latest
docker push $ECR_REPOSITORY:$(git rev-parse --short HEAD)

echo -e "${GREEN}✓ Docker image pushed to ECR${NC}"
echo ""

# Step 6: Update ECS service
echo -e "${YELLOW}[6/6] Updating ECS service...${NC}"

# Force new deployment to pick up latest image
aws ecs update-service \
    --cluster ${PROJECT_NAME}-cluster-${ENVIRONMENT} \
    --service ${PROJECT_NAME}-api-${ENVIRONMENT} \
    --force-new-deployment \
    --region $AWS_REGION

echo -e "${GREEN}✓ ECS service updated${NC}"
echo ""

# Get API endpoint
cd terraform
API_ENDPOINT=$(terraform output -raw api_endpoint)

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "API Endpoint: ${GREEN}http://$API_ENDPOINT${NC}"
echo ""
echo -e "Next steps:"
echo -e "1. Test API: ${YELLOW}curl http://$API_ENDPOINT/health${NC}"
echo -e "2. View logs: ${YELLOW}aws logs tail /ecs/${PROJECT_NAME}-api-${ENVIRONMENT} --follow${NC}"
echo -e "3. Monitor: Check CloudWatch dashboard in AWS Console"
echo ""
echo -e "${YELLOW}Note: It may take 2-3 minutes for the service to become healthy.${NC}"
