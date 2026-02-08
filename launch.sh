#!/bin/bash
# Dashboard Launcher Script
# Launches the Pi 400 dashboard on the TFT display

set -e

# Source bashrc to get TODOIST_API_TOKEN
if [ -f ~/.bashrc ]; then
    source ~/.bashrc
fi

# Set display
export DISPLAY=:0

# Get gateway token and port from running gateway process
GATEWAY_PID=$(pgrep -f openclaw-gateway | head -1)
if [ -n "$GATEWAY_PID" ]; then
    export OPENCLAW_GATEWAY_TOKEN=$(cat /proc/$GATEWAY_PID/environ | tr '\0' '\n' | grep ^OPENCLAW_GATEWAY_TOKEN= | cut -d= -f2)
    export OPENCLAW_GATEWAY_PORT=$(cat /proc/$GATEWAY_PID/environ | tr '\0' '\n' | grep ^OPENCLAW_GATEWAY_PORT= | cut -d= -f2)
fi

# Fallback to defaults if not found
if [ -z "$OPENCLAW_GATEWAY_PORT" ]; then
    export OPENCLAW_GATEWAY_PORT=18789
fi
if [ -z "$OPENCLAW_GATEWAY_TOKEN" ]; then
    echo "Warning: Could not find gateway token"
fi

# Change to dashboard directory
cd "$(dirname "$0")"

# Check if pygame is installed
if ! python3 -c "import pygame" 2>/dev/null; then
    echo "Error: pygame not installed"
    echo "Install with: sudo apt-get install python3-pygame"
    exit 1
fi

# Check for todoist CLI
if ! command -v todoist &> /dev/null; then
    echo "Warning: todoist CLI not found"
    echo "Install with: pip3 install todoist-python"
fi

# Launch dashboard (v11 - Safe Commands Edition)
echo "Starting Pi 400 Dashboard..."
python3 dashboard_v13.py

exit 0
