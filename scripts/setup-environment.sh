#!/bin/bash

# Setup OptiBot environment
# This script creates necessary directories and sets permissions

set -e

echo "Setting up OptiBot environment..."

# Create directories
mkdir -p /opt/optibot/logs
mkdir -p /opt/optibot/articles

# Set permissions
chmod 777 /opt/optibot/logs
chmod 777 /opt/optibot/articles

# Change to project directory
cd /opt/optibot

echo "✅ Environment setup completed"
echo "Directories created:"
echo "  - /opt/optibot/logs (777 permissions)"
echo "  - /opt/optibot/articles (777 permissions)"
