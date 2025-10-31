#!/bin/sh
set -e

echo "[NGINX Config] Starting configuration generation..."

# Determine backup pool
if [ "$ACTIVE_POOL" = "blue" ]; then
    BACKUP_POOL="green"
elif [ "$ACTIVE_POOL" = "green" ]; then
    BACKUP_POOL="blue"
else
    echo "[ERROR] ACTIVE_POOL must be 'blue' or 'green'. Got: $ACTIVE_POOL"
    exit 1
fi

echo "[INFO] Active Pool: $ACTIVE_POOL"
echo "[INFO] Backup Pool: $BACKUP_POOL"

# Set default APP_PORT
APP_PORT=${APP_PORT:-3000}
echo "[INFO] Application Port: $APP_PORT"

# Create backup server configuration
BACKUP_SERVER_CONFIG="server app_${BACKUP_POOL}:${APP_PORT} backup max_fails=1 fail_timeout=10s;"

# Export for envsubst
export ACTIVE_POOL
export BACKUP_POOL
export APP_PORT
export BACKUP_SERVER_CONFIG

# Remove any existing configs to prevent duplicates
rm -f /etc/nginx/conf.d/*.conf

# Generate nginx config
echo "[INFO] Generating NGINX configuration..."
envsubst '${ACTIVE_POOL} ${BACKUP_POOL} ${APP_PORT} ${BACKUP_SERVER_CONFIG}' \
    < /etc/nginx/templates/default.conf.template \
    > /etc/nginx/conf.d/default.conf

echo "[SUCCESS] Configuration generated!"
echo "=========================================="
cat /etc/nginx/conf.d/default.conf
echo "=========================================="

# List all config files to verify no duplicates
echo "[INFO] Config files in /etc/nginx/conf.d/:"
ls -la /etc/nginx/conf.d/

# Test configuration
nginx -t

echo "[SUCCESS] NGINX configuration valid!"