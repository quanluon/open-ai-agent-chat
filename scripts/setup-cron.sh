#!/bin/bash

# Setup cron job for OptiBot
# This script sets up the daily cron job to run OptiBot at 2 AM UTC

set -e

echo "Setting up OptiBot cron job..."

# Remove any existing optibot cron entries
crontab -l 2>/dev/null | grep -v "optibot" | crontab - || true

# Add new cron job
CRON_JOB="0 2 * * *  /usr/bin/docker run --rm --env-file /opt/optibot/.env -v /opt/optibot/logs:/app/runs -v /opt/optibot/articles:/app/articles --user appuser --name optibot-cron optibot:latest >> /opt/optibot/logs/cron.log 2>&1"

(crontab -l 2>/dev/null; echo "$CRON_JOB") | crontab -

echo "✅ Cron job setup completed"
echo "Schedule: Daily at 2 AM UTC"
echo "Command: $CRON_JOB"

# Verify cron job was added
echo ""
echo "Current cron jobs:"
crontab -l | grep optibot || echo "No optibot cron jobs found"
