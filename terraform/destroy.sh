#!/usr/bin/env bash
# destroy.sh — Backup ArangoDB to S3, then destroy all Terraform resources.
#
# Usage:
#   ./destroy.sh              # backup + destroy
#   ./destroy.sh --no-backup  # destroy only (skip backup)
#   ./destroy.sh --backup-only # backup only (no destroy)
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

NO_BACKUP=false
BACKUP_ONLY=false
for arg in "$@"; do
  case $arg in
    --no-backup)   NO_BACKUP=true ;;
    --backup-only) BACKUP_ONLY=true ;;
  esac
done

# ─── Config (read from terraform state) ──────────────────────────────────────
REGION="us-east-1"
SECRET_NAME="complira/arangodb/root-password-prod"
S3_BUCKET="complira-backups-prod-669003566167"

get_instance_id() {
  terraform state show aws_instance.arangodb 2>/dev/null | grep -E "^    id " | awk '{print $3}' | tr -d '"'
}

# ─── Backup ───────────────────────────────────────────────────────────────────
backup() {
  echo "▶ Fetching ArangoDB instance ID..."
  INSTANCE_ID=$(get_instance_id)
  if [[ -z "$INSTANCE_ID" ]]; then
    echo "✗ No ArangoDB instance found in state. Skipping backup."
    return
  fi
  echo "  Instance: $INSTANCE_ID"

  echo "▶ Fetching ArangoDB password from Secrets Manager..."
  ARANGO_PASS=$(aws secretsmanager get-secret-value \
    --secret-id "$SECRET_NAME" \
    --region "$REGION" \
    --query SecretString --output text)

  echo "▶ Running arangodump via SSM..."
  CMD_ID=$(aws ssm send-command \
    --instance-ids "$INSTANCE_ID" \
    --document-name "AWS-RunShellScript" \
    --region "$REGION" \
    --parameters "commands=[
      \"set -e\",
      \"BACKUP_DATE=\$(date +%Y%m%d-%H%M%S)\",
      \"BACKUP_DIR=/tmp/arangodb-backup-\$BACKUP_DATE\",
      \"mkdir -p \$BACKUP_DIR\",
      \"arangodump --server.endpoint tcp://127.0.0.1:8529 --server.username root --server.password '${ARANGO_PASS}' --all-databases true --output-directory \$BACKUP_DIR\",
      \"tar -czf /tmp/arangodb-\$BACKUP_DATE.tar.gz -C /tmp arangodb-backup-\$BACKUP_DATE\",
      \"aws s3 cp /tmp/arangodb-\$BACKUP_DATE.tar.gz s3://${S3_BUCKET}/final-backup/arangodb-\$BACKUP_DATE.tar.gz --region ${REGION}\",
      \"echo BACKUP_COMPLETE: s3://${S3_BUCKET}/final-backup/arangodb-\$BACKUP_DATE.tar.gz\",
      \"rm -rf \$BACKUP_DIR /tmp/arangodb-\$BACKUP_DATE.tar.gz\"
    ]" \
    --query 'Command.CommandId' --output text)

  echo "  Command ID: $CMD_ID"
  echo "▶ Waiting for backup to complete..."

  for i in $(seq 1 60); do
    STATUS=$(aws ssm get-command-invocation \
      --command-id "$CMD_ID" \
      --instance-id "$INSTANCE_ID" \
      --region "$REGION" \
      --query 'Status' --output text 2>/dev/null || echo "Pending")
    echo "  [$i] $STATUS"
    if [[ "$STATUS" == "Success" ]]; then
      OUTPUT=$(aws ssm get-command-invocation \
        --command-id "$CMD_ID" \
        --instance-id "$INSTANCE_ID" \
        --region "$REGION" \
        --query 'StandardOutputContent' --output text)
      S3_PATH=$(echo "$OUTPUT" | grep "BACKUP_COMPLETE:" | awk '{print $2}')
      echo "✓ Backup saved: $S3_PATH"
      return
    elif [[ "$STATUS" == "Failed" || "$STATUS" == "Cancelled" || "$STATUS" == "TimedOut" ]]; then
      STDERR=$(aws ssm get-command-invocation \
        --command-id "$CMD_ID" \
        --instance-id "$INSTANCE_ID" \
        --region "$REGION" \
        --query 'StandardErrorContent' --output text)
      echo "✗ Backup failed: $STDERR"
      echo "  Continue with destroy anyway? (y/N)"
      read -r REPLY
      [[ "$REPLY" =~ ^[Yy]$ ]] || exit 1
      return
    fi
    sleep 15
  done
  echo "✗ Backup timed out after 15 minutes"
  exit 1
}

# ─── Destroy ─────────────────────────────────────────────────────────────────
destroy() {
  echo "▶ Running terraform destroy..."
  terraform destroy -auto-approve
  echo "✓ All resources destroyed"
}

# ─── Main ─────────────────────────────────────────────────────────────────────
if [[ "$NO_BACKUP" == false && "$BACKUP_ONLY" == false ]]; then
  backup
  destroy
elif [[ "$BACKUP_ONLY" == true ]]; then
  backup
else
  destroy
fi
