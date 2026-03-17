# Terraform Deployment & Teardown Guide

## Quick Start

### Deploy Infrastructure
```bash
cd terraform
terraform init
terraform plan
terraform apply
```

### Teardown Infrastructure
```bash
terraform destroy -auto-approve
```

## Issues Fixed for Clean Teardowns

### 1. Load Balancer Deletion Protection
**Issue**: ALB had deletion protection enabled for prod, preventing `terraform destroy`

**Fix**: Disabled deletion protection in `alb.tf:11`
```hcl
enable_deletion_protection = false  # Disabled for easy teardown
```

### 2. Password Generation
**Issue**: Random passwords with special characters caused shell escaping issues in userdata scripts

**Fix**: Generate alphanumeric-only passwords in `secrets.tf`
```hcl
resource "random_password" "arangodb" {
  length  = 32
  special = false  # Avoid special characters
  upper   = true
  lower   = true
  numeric = true
}
```

### 3. ArangoDB Password Setting
**Issue**: debconf password setting was unreliable

**Fix**: Added automatic password reset in `userdata/arangodb.sh` using arangosh after installation

### 4. Resource Dependencies
**Issue**: Resources destroyed in wrong order causing timeouts

**Fix**: Added proper `depends_on` and lifecycle blocks in `ecs.tf`

## Deployment Order

Terraform automatically handles dependencies, but resources are created in this order:
1. VPC, Subnets, Internet Gateway
2. Security Groups
3. NAT Gateway (depends on public subnet + Elastic IP)
4. EC2 Instances (ArangoDB)
5. ElastiCache (Redis)
6. Load Balancer
7. ECS Cluster & Services
8. Auto Scaling

## Teardown Order

Terraform automatically destroys in reverse dependency order:
1. ECS Services (scaled to 0 first)
2. Auto Scaling policies
3. Load Balancer (deletion protection disabled)
4. EC2 Instances
5. ElastiCache
6. NAT Gateway
7. Security Groups
8. Subnets
9. Internet Gateway
10. VPC

## Troubleshooting Teardown Issues

### If `terraform destroy` hangs:

1. **Check running ECS tasks**:
   ```bash
   aws ecs list-tasks --cluster complira-cluster-prod --region us-east-1
   ```

2. **Force delete ECS service**:
   ```bash
   aws ecs delete-service --cluster complira-cluster-prod --service complira-api-prod --force --region us-east-1
   ```

3. **Delete Load Balancer manually** (if deletion protection was re-enabled):
   ```bash
   # Disable protection
   aws elbv2 modify-load-balancer-attributes \
     --load-balancer-arn <ALB_ARN> \
     --attributes Key=deletion_protection.enabled,Value=false \
     --region us-east-1

   # Delete ALB
   aws elbv2 delete-load-balancer --load-balancer-arn <ALB_ARN> --region us-east-1
   ```

4. **Wait for NAT Gateway to delete** (can take 2-3 minutes):
   ```bash
   aws ec2 describe-nat-gateways --filter "Name=tag:Name,Values=complira-nat-prod" --region us-east-1
   ```

5. **Retry destroy**:
   ```bash
   terraform destroy -auto-approve
   ```

## Cost Optimization

### Development Environment
For dev/test, use smaller instance types in `variables.tf`:
```hcl
arangodb_instance_type = "t3.small"  # Instead of t3.large
api_cpu               = "256"        # Instead of 1024
api_memory            = "512"        # Instead of 2048
```

### Teardown When Not in Use
Since this is a test/dev environment, destroy when not actively developing:
```bash
terraform destroy -auto-approve
```

All data in ArangoDB will be backed up to S3 (if backup cron is enabled).

## Security Notes

1. **Never commit secrets**: `.env` files are gitignored
2. **Rotate passwords**: Change ArangoDB password via Secrets Manager
3. **Enable HTTPS**: Uncomment HTTPS listener in `alb.tf` after obtaining ACM certificate
4. **Restrict access**: Update security group rules to limit source IPs in production

## Database Seeding

To seed the reference database after deployment:
1. Build and push Docker image to ECR
2. Update ECS task definition with seeding command
3. Run one-time task (30-60 minutes)

See `seed-task-definition.json` for reference.
