#!/bin/bash
# Kill any existing server
pkill -f "python3.*server.py" 2>/dev/null
sleep 1
# Start watchdog in background
nohup /home/DexTer/mimo-mobile-server/watchdog.sh > /dev/null 2>&1 &
echo "Watchdog started. Server will auto-restart on crash."
