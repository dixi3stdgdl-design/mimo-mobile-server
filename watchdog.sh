#!/bin/bash
# MiMo Server Watchdog - auto-restart on crash with safety limits
SERVER_DIR="/home/DexTer/mimo-mobile-server"
LOG="/tmp/mimo-server.log"
MAX_CRASHES=5
CRASH_COUNT=0
LAST_CRASH_TIME=0

while true; do
    CURRENT_TIME=$(date +%s)

    # Reset crash count if last crash was more than 60 seconds ago
    if [ $((CURRENT_TIME - LAST_CRASH_TIME)) -gt 60 ]; then
        CRASH_COUNT=0
    fi

    # Check if we've crashed too many times
    if [ "$CRASH_COUNT" -ge "$MAX_CRASHES" ]; then
        echo "[$(date)] Server crashed $MAX_CRASHES times in 60s. Stopping watchdog." >> "$LOG"
        echo "[$(date)] Fix the issue and restart manually: $SERVER_DIR/start-server.sh" >> "$LOG"
        exit 1
    fi

    echo "[$(date)] Starting MiMo Server... (attempt $((CRASH_COUNT + 1))/$MAX_CRASHES)" >> "$LOG"
    cd "$SERVER_DIR"
    python3 -u server.py >> "$LOG" 2>&1
    EXIT_CODE=$?
    CRASH_COUNT=$((CRASH_COUNT + 1))
    LAST_CRASH_TIME=$(date +%s)

    if [ "$EXIT_CODE" -eq 0 ]; then
        echo "[$(date)] Server stopped cleanly. Not restarting." >> "$LOG"
        exit 0
    fi

    echo "[$(date)] Server exited with code $EXIT_CODE. Restarting in 5s..." >> "$LOG"
    sleep 5
done
