#!/bin/bash
set -e

# Wait for network connectivity
echo "Waiting for network connectivity..."
for i in {1..30}; do
  if curl -s --max-time 5 http://security.ubuntu.com > /dev/null 2>&1; then
    echo "Network is ready"
    break
  fi
  echo "Attempt $i: Network not ready, waiting 10 seconds..."
  sleep 10
done

# Update system
apt-get update
apt-get upgrade -y

# Install dependencies
apt-get install -y curl gnupg apt-transport-https ca-certificates

# Add ArangoDB repository (with GPG verification disabled for testing)
echo 'deb [trusted=yes] https://download.arangodb.com/arangodb310/DEBIAN/ /' | tee /etc/apt/sources.list.d/arangodb.list

# Install ArangoDB
apt-get update
# Use printf to safely handle special characters in password
printf "arangodb3 arangodb3/password password %s\n" "${arango_password}" | debconf-set-selections
printf "arangodb3 arangodb3/password_again password %s\n" "${arango_password}" | debconf-set-selections
DEBIAN_FRONTEND=noninteractive apt-get install -y --allow-unauthenticated arangodb3=3.10.*

# Format and mount data volume
mkfs -t ext4 /dev/nvme1n1
mkdir -p /var/lib/arangodb3-data
mount /dev/nvme1n1 /var/lib/arangodb3-data
echo '/dev/nvme1n1 /var/lib/arangodb3-data ext4 defaults,nofail 0 2' >> /etc/fstab

# Set ownership
chown -R arangodb:arangodb /var/lib/arangodb3-data

# Configure ArangoDB - modify existing config instead of replacing
# Change data directory
sed -i 's|^directory = .*|directory = /var/lib/arangodb3-data|' /etc/arangodb3/arangod.conf

# Change endpoint to listen on all interfaces
sed -i 's|^endpoint = .*|endpoint = tcp://0.0.0.0:8529|' /etc/arangodb3/arangod.conf

# Add RocksDB cache size if not present
if ! grep -q "block-cache-size" /etc/arangodb3/arangod.conf; then
  echo "" >> /etc/arangodb3/arangod.conf
  echo "[rocksdb]" >> /etc/arangodb3/arangod.conf
  echo "block-cache-size = 8589934592" >> /etc/arangodb3/arangod.conf
fi

# Restart ArangoDB with new configuration
systemctl enable arangodb3
systemctl restart arangodb3

# Wait for ArangoDB to be ready
echo "Waiting for ArangoDB to start..."
for i in {1..30}; do
  if curl -s http://127.0.0.1:8529/_api/version > /dev/null 2>&1; then
    echo "ArangoDB is ready"
    break
  fi
  echo "Attempt $i: ArangoDB not ready, waiting 2 seconds..."
  sleep 2
done

# Reset root password using arangosh (debconf password setting is unreliable)
cat > /tmp/reset_password.js <<'RESET_SCRIPT'
const db = require('@arangodb').db;
const users = require('@arangodb/users');
users.update('root', '${arango_password}', true);
print('Password updated successfully');
RESET_SCRIPT

arangosh --server.authentication=false --javascript.execute /tmp/reset_password.js
rm /tmp/reset_password.js

# Install AWS CLI for backups
apt-get install -y awscli

# Create backup script
cat > /usr/local/bin/backup-arangodb.sh <<'BACKUP_SCRIPT'
#!/bin/bash
BACKUP_DIR="/tmp/arangodb-backup"
DATE=$(date +%Y%m%d-%H%M%S)
S3_BUCKET="${project_name}-backups-${environment}"

# Create backup
arangodump \
  --server.endpoint tcp://127.0.0.1:8529 \
  --server.password ${arango_password} \
  --output-directory "$BACKUP_DIR"

# Compress backup
tar -czf "/tmp/arangodb-backup-$DATE.tar.gz" -C "$BACKUP_DIR" .

# Upload to S3
aws s3 cp "/tmp/arangodb-backup-$DATE.tar.gz" "s3://$S3_BUCKET/arangodb/$DATE.tar.gz"

# Cleanup
rm -rf "$BACKUP_DIR" "/tmp/arangodb-backup-$DATE.tar.gz"
BACKUP_SCRIPT

chmod +x /usr/local/bin/backup-arangodb.sh

# Schedule daily backups at 2 AM
echo "0 2 * * * root /usr/local/bin/backup-arangodb.sh" > /etc/cron.d/arangodb-backup

echo "ArangoDB installation complete"
