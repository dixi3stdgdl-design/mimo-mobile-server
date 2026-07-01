#!/bin/bash
# MiMo Mobile - Quick Start Script
# Run this on your PC to start the server

echo "============================================"
echo "  MiMo Mobile Server"
echo "============================================"
echo ""

# Get IP address
IP=$(hostname -I | awk '{print $1}')
echo "Your PC's IP: $IP"
echo "WebSocket URL: ws://$IP:8765"
echo "HTTP URL: http://$IP:8080"
echo ""

# Check if mimo command exists
if command -v mimo &> /dev/null; then
    echo "MiMo CLI found: $(which mimo)"
else
    echo "WARNING: 'mimo' command not found"
    echo "Set MIMO_CMD environment variable or install MiMo CLI"
    echo "Example: export MIMO_CMD='path/to/mimo'"
fi

echo ""
echo "Starting server..."
echo "On your phone, enter IP: $IP"
echo "============================================"
echo ""

python3 "$(dirname "$0")/server.py"
