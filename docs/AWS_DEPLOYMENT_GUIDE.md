# AWS Deployment Guide for Complira Knowledge Graph

This guide walks you through deploying the Complira Knowledge Graph API to AWS using Terraform and ECS Fargate.

---

## 📋 Architecture Overview

**What Gets Deployed:**
- **VPC** with public/private subnets across 2 AZs
- **Application Load Balancer** (ALB) for HTTPS traffic
- **ECS Fargate** cluster running the FastAPI application (auto-scaling 2-10 tasks)
- **ArangoDB** on dedicated EC2 instance (r6g.xlarge, ARM-based)
- **Redis** on ElastiCache (cache.r6g.large)
- **S3** for database backups
- **CloudWatch** for logging and monitoring
- **Secrets Manager** for sensitive credentials

**Estimated Monthly Cost:** ~$450-600/month for production configuration

---

## 🛠️ Prerequisites

### 1. Install Required Tools

```bash
# AWS CLI
curl "https://awscli.amazonaws.com/AWSCLIV2.pkg" -o "AWSCLIV2.pkg"
sudo installer -pkg AWSCLIV2.pkg -target /

# Terraform
brew install terraform

# Docker Desktop (if not already installed)
# Download from: https://www.docker.com/products/docker-desktop
```

### 2. Configure AWS Credentials

```bash
aws configure
```

You'll need:
- **AWS Access Key ID**
- **AWS Secret Access Key**
- **Default region:** us-east-1 (recommended)
- **Output format:** json

### 3. Verify AWS Account Access

```bash
aws sts get-caller-identity
```

You should see your AWS account ID and ARN.

---

## 🚀 Quick Deployment (Automated)

### Option A: One-Command Deployment

```bash
# Make deployment script executable
chmod +x scripts/deploy-aws.sh

# Run deployment
./scripts/deploy-aws.sh
```

This automated script:
1. ✅ Validates prerequisites
2. ✅ Initializes Terraform
3. ✅ Plans infrastructure
4. ✅ Deploys AWS resources
5. ✅ Builds & pushes Docker image to ECR
6. ✅ Updates ECS service

**Time to complete:** 15-20 minutes

---

## 📝 Manual Deployment (Step-by-Step)

### Step 1: Initialize Terraform

```bash
cd terraform
terraform init
```

### Step 2: Review Infrastructure Plan

```bash
terraform plan \
  -var="aws_region=us-east-1" \
  -var="environment=prod"
```

Review the resources that will be created:
- **VPC & Networking:** 1 VPC, 4 subnets, NAT gateway
- **Compute:** 1 EC2 (ArangoDB), ECS cluster
- **Database:** 1 ElastiCache cluster
- **Load Balancer:** 1 ALB
- **Storage:** 1 S3 bucket, 1 EBS volume (500 GB)

### Step 3: Deploy Infrastructure

```bash
terraform apply \
  -var="aws_region=us-east-1" \
  -var="environment=prod"
```

Type `yes` to confirm.

**Wait time:** ~12-15 minutes

### Step 4: Get ECR Repository URL

```bash
ECR_REPOSITORY=$(terraform output -raw ecr_repository_url)
echo $ECR_REPOSITORY
```

### Step 5: Build and Push Docker Image

```bash
cd ..

# Login to ECR
aws ecr get-login-password --region us-east-1 | \
    docker login --username AWS --password-stdin $ECR_REPOSITORY

# Build image
docker build -t complira-api:latest .

# Tag image
docker tag complira-api:latest $ECR_REPOSITORY:latest

# Push image
docker push $ECR_REPOSITORY:latest
```

### Step 6: Trigger ECS Deployment

```bash
aws ecs update-service \
    --cluster complira-cluster-prod \
    --service complira-api-prod \
    --force-new-deployment \
    --region us-east-1
```

### Step 7: Get API Endpoint

```bash
cd terraform
API_ENDPOINT=$(terraform output -raw api_endpoint)
echo "API URL: http://$API_ENDPOINT"
```

---

## ✅ Verification

### 1. Check API Health

```bash
curl http://$API_ENDPOINT/health
```

Expected response:
```json
{"status":"healthy","version":"0.1.0"}
```

### 2. Test API Endpoint

```bash
# Get API key from database (one-time setup)
API_KEY="your_api_key_here"

# Test reference API
curl -H "X-API-Key: $API_KEY" \
     http://$API_ENDPOINT/v1/reference/vulnerabilities/CVE-2021-44228
```

### 3. Monitor Logs

```bash
# Stream logs in real-time
aws logs tail /ecs/complira-api-prod --follow

# Or view in AWS Console
open https://console.aws.amazon.com/cloudwatch
```

### 4. Check ECS Service Status

```bash
aws ecs describe-services \
    --cluster complira-cluster-prod \
    --services complira-api-prod \
    --region us-east-1 \
    --query 'services[0].deployments'
```

---

## 🔧 Configuration

### Customize Deployment Variables

Edit `terraform/terraform.tfvars`:

```hcl
aws_region         = "us-east-1"
environment        = "prod"
project_name       = "complira"

# API Configuration
api_cpu            = 2048  # 2 vCPUs
api_memory         = 4096  # 4 GB
api_desired_count  = 2     # Number of tasks

# ArangoDB Configuration
arangodb_instance_type = "r6g.xlarge"  # 4 vCPUs, 32 GB RAM
```

Apply changes:
```bash
cd terraform
terraform apply -var-file="terraform.tfvars"
```

### Environment Variables

The ECS task automatically sets these environment variables:
- `ENVIRONMENT=prod`
- `ARANGO_URL=http://<private-ip>:8529`
- `REDIS_HOST=<elasticache-endpoint>`
- `REDIS_PORT=6379`
- `ARANGO_PASSWORD` (from Secrets Manager)

To add custom environment variables, edit `terraform/ecs.tf`:

```hcl
environment = [
  {
    name  = "YOUR_VAR_NAME"
    value = "your_value"
  }
]
```

---

## 📊 Monitoring & Operations

### CloudWatch Dashboards

View metrics in AWS Console:
- **ECS Service:** CPU, memory, task count
- **ALB:** Request count, latency, 5xx errors
- **ArangoDB:** Disk usage, CPU
- **Redis:** Cache hit rate, evictions

### Logs

```bash
# API logs
aws logs tail /ecs/complira-api-prod --follow

# ArangoDB logs (SSH to EC2)
aws ssm start-session --target <instance-id>
tail -f /var/log/arangodb3/arangod.log
```

### Backups

**ArangoDB backups** run daily at 2 AM UTC and are stored in S3:

```bash
# List backups
aws s3 ls s3://complira-backups-prod-<account-id>/arangodb/

# Restore from backup
aws s3 cp s3://complira-backups-prod-<account-id>/arangodb/20260314-020000.tar.gz .
tar -xzf 20260314-020000.tar.gz
arangorestore --server.endpoint tcp://localhost:8529 --input-directory ./
```

---

## 🔐 Security Best Practices

### 1. Enable HTTPS (Production Required)

1. Register domain in Route 53
2. Request ACM certificate
3. Update `terraform/alb.tf` to use HTTPS listener
4. Redeploy

### 2. Restrict ALB Access (Optional)

Edit `terraform/network.tf` to limit ingress:

```hcl
ingress {
  description = "HTTPS from specific IPs"
  from_port   = 443
  to_port     = 443
  protocol    = "tcp"
  cidr_blocks = ["YOUR_OFFICE_IP/32"]  # Replace with your IP
}
```

### 3. Enable WAF (Optional)

```bash
# Create WAF WebACL
aws wafv2 create-web-acl \
    --name complira-waf \
    --scope REGIONAL \
    --default-action Allow={} \
    --region us-east-1

# Associate with ALB
aws wafv2 associate-web-acl \
    --web-acl-arn <web-acl-arn> \
    --resource-arn <alb-arn>
```

---

## 💰 Cost Optimization

### Development Environment

For lower-cost development deployment:

```hcl
# terraform/terraform.tfvars
environment            = "dev"
api_desired_count      = 1            # Single task
api_cpu                = 1024         # 1 vCPU
api_memory             = 2048         # 2 GB
arangodb_instance_type = "t4g.medium" # 2 vCPUs, 4 GB
```

**Estimated cost:** ~$150-200/month

### Stop/Start Environment

```bash
# Stop (saves ~70% of costs)
terraform destroy -target=aws_ecs_service.api
terraform destroy -target=aws_instance.arangodb

# Start (redeploy when needed)
terraform apply
```

---

## 🐛 Troubleshooting

### Issue: ECS tasks fail to start

**Check:**
1. Docker image exists in ECR:
   ```bash
   aws ecr describe-images --repository-name complira-api-prod
   ```

2. Task definition is valid:
   ```bash
   aws ecs describe-task-definition --task-definition complira-api-prod
   ```

3. View task logs:
   ```bash
   aws logs tail /ecs/complira-api-prod --follow
   ```

### Issue: Cannot connect to API

**Check:**
1. Security groups allow traffic:
   ```bash
   aws ec2 describe-security-groups --group-ids sg-xxx
   ```

2. Target group health:
   ```bash
   aws elbv2 describe-target-health \
       --target-group-arn <target-group-arn>
   ```

3. ECS service is running:
   ```bash
   aws ecs describe-services \
       --cluster complira-cluster-prod \
       --services complira-api-prod
   ```

### Issue: High costs

**Actions:**
1. Check unused resources:
   ```bash
   aws ce get-cost-and-usage \
       --time-period Start=2026-03-01,End=2026-03-15 \
       --granularity MONTHLY \
       --metrics "UnblendedCost"
   ```

2. Enable cost allocation tags
3. Review NAT gateway usage (expensive if high traffic)
4. Consider reserved instances for ArangoDB EC2

---

## 📦 Cleanup

### Destroy All Resources

```bash
cd terraform
terraform destroy -var="environment=prod"
```

Type `yes` to confirm.

**Note:** This will:
- ✅ Delete all AWS resources
- ✅ Preserve S3 backups (delete manually if needed)
- ⚠️ **Data loss:** ArangoDB data will be deleted

---

## 🚀 Next Steps

After successful deployment:

1. **Set up CI/CD:**
   - Configure GitHub Actions to automatically deploy on push to main
   - See `.github/workflows/deploy.yml` (create this)

2. **Configure custom domain:**
   - Register domain in Route 53
   - Request ACM certificate
   - Update ALB listener to use HTTPS

3. **Set up monitoring alerts:**
   - CloudWatch alarms for high CPU, memory
   - SNS notifications for critical errors

4. **Populate reference data:**
   ```bash
   # SSH to ArangoDB instance
   aws ssm start-session --target <instance-id>

   # Run data seeding scripts
   python scripts/seed_reference_database.py
   ```

5. **Create demo customer:**
   ```bash
   curl -X POST http://$API_ENDPOINT/v1/admin/customers \
       -H "Content-Type: application/json" \
       -d '{"name":"Demo Corp","email":"demo@example.com"}'
   ```

---

## 📞 Support

- **Terraform Issues:** Check `terraform/` directory for configuration files
- **AWS Issues:** Review CloudWatch logs and ECS service events
- **Application Issues:** Check `/ecs/complira-api-prod` logs

**Architecture Diagram:** See `docs/cloud-architecture.md`
