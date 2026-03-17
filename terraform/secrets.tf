# Secrets Management

# ========== Random Passwords ==========
# Use alphanumeric-only password to avoid shell escaping issues in userdata scripts
resource "random_password" "arangodb" {
  length  = 32
  special = false  # Avoid special characters that cause shell/debconf issues
  upper   = true
  lower   = true
  numeric = true
}

# ========== AWS Secrets Manager ==========

# ArangoDB Root Password
resource "aws_secretsmanager_secret" "arangodb_password" {
  name                    = "${var.project_name}/arangodb/root-password-${var.environment}"
  description             = "ArangoDB root password"
  recovery_window_in_days = 7

  tags = {
    Name = "${var.project_name}-arangodb-password-${var.environment}"
  }
}

resource "aws_secretsmanager_secret_version" "arangodb_password" {
  secret_id     = aws_secretsmanager_secret.arangodb_password.id
  secret_string = random_password.arangodb.result
}

# Grant ECS Task Execution Role access to secrets
resource "aws_iam_role_policy" "ecs_secrets_access" {
  name = "${var.project_name}-ecs-secrets-access-${var.environment}"
  role = aws_iam_role.ecs_task_execution.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue"
        ]
        Resource = [
          aws_secretsmanager_secret.arangodb_password.arn
        ]
      }
    ]
  })
}
