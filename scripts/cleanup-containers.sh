#!/bin/bash

# Cleanup OptiBot containers
# This script stops and removes existing OptiBot containers

set -e

echo "Stopping any existing OptiBot containers..."

# Stop and remove containers
docker stop optibot-cron optibot-test 2>/dev/null || true
docker rm optibot-cron optibot-test 2>/dev/null || true

echo "✅ Container cleanup completed"
