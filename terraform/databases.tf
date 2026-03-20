# Database Infrastructure

# ========== ArangoDB EC2 Instance ==========

# AMI for ArangoDB (Ubuntu 22.04 LTS x86_64)
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# User data script to install ArangoDB
locals {
  arangodb_userdata = templatefile("${path.module}/userdata/arangodb.sh", {
    arango_password = random_password.arangodb.result
    project_name    = var.project_name
    environment     = var.environment
  })
}

# EBS Volume for ArangoDB data
resource "aws_ebs_volume" "arangodb_data" {
  availability_zone = data.aws_availability_zones.available.names[0]
  size              = 500  # 500 GB for production data
  type              = "gp3"
  iops              = 3000
  throughput        = 125
  encrypted         = true

  tags = {
    Name = "${var.project_name}-arangodb-data-${var.environment}"
  }
}

# ArangoDB Instance
resource "aws_instance" "arangodb" {
  ami           = data.aws_ami.ubuntu.id
  instance_type = var.arangodb_instance_type
  subnet_id     = aws_subnet.private[0].id

  vpc_security_group_ids = [aws_security_group.arangodb.id]

  iam_instance_profile = aws_iam_instance_profile.arangodb.name

  user_data = local.arangodb_userdata

  root_block_device {
    volume_type           = "gp3"
    volume_size           = 50
    delete_on_termination = true
    encrypted             = true
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  monitoring = true

  tags = {
    Name = "${var.project_name}-arangodb-${var.environment}"
  }
}

# Attach EBS volume to ArangoDB instance
resource "aws_volume_attachment" "arangodb_data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.arangodb_data.id
  instance_id = aws_instance.arangodb.id
}

# IAM Role for ArangoDB instance (for backups to S3)
resource "aws_iam_role" "arangodb" {
  name = "${var.project_name}-arangodb-role-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "ec2.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name = "${var.project_name}-arangodb-role-${var.environment}"
  }
}

resource "aws_iam_instance_profile" "arangodb" {
  name = "${var.project_name}-arangodb-profile-${var.environment}"
  role = aws_iam_role.arangodb.name
}

# SSM access for instance management
resource "aws_iam_role_policy_attachment" "arangodb_ssm" {
  role       = aws_iam_role.arangodb.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Policy for ArangoDB backups to S3
resource "aws_iam_role_policy" "arangodb_s3_backup" {
  name = "${var.project_name}-arangodb-s3-backup-${var.environment}"
  role = aws_iam_role.arangodb.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "s3:PutObject",
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.backups.arn,
          "${aws_s3_bucket.backups.arn}/*"
        ]
      }
    ]
  })
}

# ========== Redis ElastiCache ==========

# Subnet group for Redis
resource "aws_elasticache_subnet_group" "redis" {
  name       = "${var.project_name}-redis-subnet-${var.environment}"
  subnet_ids = aws_subnet.private[*].id

  tags = {
    Name = "${var.project_name}-redis-subnet-group-${var.environment}"
  }
}

# Redis Cluster
resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${var.project_name}-redis-${var.environment}"
  engine               = "redis"
  engine_version       = "7.1"
  node_type            = "cache.t4g.small"  # ARM-based, 1.37 GB RAM (cost-effective for testing)
  num_cache_nodes      = 1
  parameter_group_name = aws_elasticache_parameter_group.redis.name
  subnet_group_name    = aws_elasticache_subnet_group.redis.name
  security_group_ids   = [aws_security_group.redis.id]
  port                 = 6379

  snapshot_retention_limit = 5
  snapshot_window          = "03:00-05:00"

  maintenance_window = "sun:05:00-sun:07:00"

  tags = {
    Name = "${var.project_name}-redis-${var.environment}"
  }
}

# Redis Parameter Group
resource "aws_elasticache_parameter_group" "redis" {
  name   = "${var.project_name}-redis-params-${var.environment}"
  family = "redis7"

  parameter {
    name  = "maxmemory-policy"
    value = "allkeys-lru"
  }

  tags = {
    Name = "${var.project_name}-redis-params-${var.environment}"
  }
}

# ========== S3 Bucket for Backups ==========
resource "aws_s3_bucket" "backups" {
  bucket        = "${var.project_name}-backups-${var.environment}-${data.aws_caller_identity.current.account_id}"
  force_destroy = true

  tags = {
    Name = "${var.project_name}-backups-${var.environment}"
  }
}

resource "aws_s3_bucket_versioning" "backups" {
  bucket = aws_s3_bucket.backups.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "backups" {
  bucket = aws_s3_bucket.backups.id

  rule {
    id     = "expire-old-backups"
    status = "Enabled"

    filter {}

    expiration {
      days = 30
    }

    noncurrent_version_expiration {
      noncurrent_days = 7
    }
  }
}

# Data source for current AWS account
data "aws_caller_identity" "current" {}
