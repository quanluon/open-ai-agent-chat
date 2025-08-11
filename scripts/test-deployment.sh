#!/bin/bash

# Test OptiBot deployment
# This script tests the deployment with a temporary container

set -e

echo "🧪 Testing OptiBot deployment with temporary container..."

# Run test container
docker run --rm \
  --name optibot-test \
  --env-file /opt/optibot/.env \
  -v /opt/optibot/logs:/app/runs \
  -v /opt/optibot/articles:/app/articles \
  --user appuser \
  optibot:latest

echo "✅ Deployment test completed successfully!"
