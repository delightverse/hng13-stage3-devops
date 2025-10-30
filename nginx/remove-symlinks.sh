#!/bin/sh
# Remove symlinked log files so nginx creates real files
set -e

echo "[INFO] Removing nginx log symlinks..."
rm -f /var/log/nginx/access.log
rm -f /var/log/nginx/error.log
echo "[SUCCESS] Log symlinks removed. Nginx will create real log files."
