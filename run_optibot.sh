#!/bin/bash

# OptiBot Local Cron Runner
# This script runs OptiBot and logs output to logs/cron.log

set -e  # Exit on any error

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Create logs directory if it doesn't exist
mkdir -p logs

# Log start time
echo "=== OptiBot Cron Job Started at $(date) ===" >> logs/cron.log

# Check if .env file exists
if [ ! -f .env ]; then
    echo "ERROR: .env file not found in $(pwd)" >> logs/cron.log
    echo "Please create .env file with your OpenAI API credentials" >> logs/cron.log
    exit 1
fi

# Check if Docker is available
if command -v docker &> /dev/null; then
    echo "Running OptiBot with Docker..." >> logs/cron.log
    
    # Run with Docker
    docker run --rm --env-file .env \
        -v "$(pwd)/logs:/app/runs" \
        -v "$(pwd)/articles:/app/articles" \
        optibot:latest >> logs/cron.log 2>&1
    
    EXIT_CODE=$?
else
    echo "Docker not found, running with Python directly..." >> logs/cron.log
    
    # Check if Python is available
    if command -v python3 &> /dev/null; then
        # Run with Python directly
        python3 main.py >> logs/cron.log 2>&1
        EXIT_CODE=$?
    else
        echo "ERROR: Neither Docker nor Python3 found" >> logs/cron.log
        exit 1
    fi
fi

# Log end time and exit code
echo "=== OptiBot Cron Job Finished at $(date) with exit code $EXIT_CODE ===" >> logs/cron.log
echo "" >> logs/cron.log

exit $EXIT_CODE
