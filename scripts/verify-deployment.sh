#!/bin/bash

# Verify OptiBot deployment
# This script shows deployment status and recent logs

set -e

echo "=== Deployment Summary ==="
echo "✅ Image: $IMAGE_TAG"
echo "✅ Environment: /opt/optibot/.env"
echo "✅ Cron job: Daily at 2 AM UTC"
echo "✅ Log directory: /opt/optibot/logs/"
echo ""

echo "=== Cron Schedule ==="
crontab -l | grep optibot || echo "No cron jobs found"
echo ""

echo "=== Recent Logs ==="
tail -5 /opt/optibot/logs/cron.log 2>/dev/null || echo "No recent logs"
