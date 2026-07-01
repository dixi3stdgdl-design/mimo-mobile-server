#!/bin/bash
# MiMo Server Watchdog - auto-restart on crash
SERVER_DIR="/home/DexTer/mimo-mobile-server"
LOG="/tmp/mimo-server.log"

while true; do
    echo "[$(date)] Starting MiMo Server..." >> "$LOG"
    cd "$SERVER_DIR"
    python3 -u server.py >> "$LOG" 2>&1
    EXIT_CODE=$?
    echo "[$(date)] Server exited with code $EXIT_CODE. Restarting in 3s..." >> "$LOG"
    sleep 3
done
