#!/bin/bash
# MiMo Mobile Server - One-Click Install
# Detects OS, Python, ADB, and configures everything

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${CYAN}  MiMo Mobile Server Installer${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""

# --- Detect OS ---
OS="unknown"
case "$(uname -s)" in
    Linux*)     OS="linux";;
    Darwin*)    OS="macos";;
    MINGW*|MSYS*|CYGWIN*) OS="windows";;
esac
echo -e "${GREEN}[1/6]${NC} Detected OS: $OS"

# Check if running in WSL2
IS_WSL=false
if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    echo -e "       Running inside WSL2"
fi

# --- Check Python ---
echo ""
echo -e "${GREEN}[2/6]${NC} Checking Python..."
PYTHON_CMD=""
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}ERROR: Python not found. Install Python 3.10+ first.${NC}"
    exit 1
fi
PY_VERSION=$($PYTHON_CMD --version 2>&1)
echo -e "       Found: $PY_VERSION"

# --- Check/create .env ---
echo ""
echo -e "${GREEN}[3/6]${NC} Configuring environment..."
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ENV_FILE="$SCRIPT_DIR/.env"

if [ ! -f "$ENV_FILE" ]; then
    cp "$SCRIPT_DIR/.env.example" "$ENV_FILE"
    echo -e "       Created .env from .env.example"
else
    echo -e "       .env already exists"
fi

# --- Detect MiMo CLI ---
MIMO_PATH=$(command -v mimo 2>/dev/null || echo "$HOME/.mimocode/bin/mimo")
if [ -x "$MIMO_PATH" ]; then
    echo -e "       MiMo CLI: $MIMO_PATH"
    sed -i "s|^MIMO_CMD=.*|MIMO_CMD=$MIMO_PATH|" "$ENV_FILE" 2>/dev/null || true
else
    echo -e "${YELLOW}       WARNING: MiMo CLI not found at $MIMO_PATH${NC}"
    echo -e "${YELLOW}       Set MIMO_CMD in .env after installing MiMo Code CLI${NC}"
fi

# --- Detect ADB ---
echo ""
echo -e "${GREEN}[4/6]${NC} Checking ADB..."
ADB_PATH=""
if [ -n "$ANDROID_HOME" ] && [ -f "$ANDROID_HOME/platform-tools/adb" ]; then
    ADB_PATH="$ANDROID_HOME/platform-tools/adb"
elif command -v adb &> /dev/null; then
    ADB_PATH=$(command -v adb)
fi

if [ -n "$ADB_PATH" ]; then
    echo -e "       ADB: $ADB_PATH"
    # Update server.py ADB_PATH dynamically via env
    echo "export ADB_PATH='$ADB_PATH'" >> "$ENV_FILE"
else
    echo -e "${YELLOW}       ADB not found (device management disabled)${NC}"
fi

# --- Detect screen capture method ---
echo ""
echo -e "${GREEN}[5/6]${NC} Detecting screen capture..."
CAPTURE_METHOD="none"

if [ "$IS_WSL" = true ]; then
    if [ -f "/mnt/c/WINDOWS/System32/WindowsPowerShell/v1.0/powershell.exe" ]; then
        CAPTURE_METHOD="wsl2-powershell"
        echo -e "       Method: WSL2 PowerShell passthrough"
    fi
elif [ "$OS" = "linux" ]; then
    if command -v gnome-screenshot &> /dev/null; then
        CAPTURE_METHOD="gnome-screenshot"
    elif command -v scrot &> /dev/null; then
        CAPTURE_METHOD="scrot"
    elif command -v xdotool &> /dev/null; then
        CAPTURE_METHOD="xdotool+xwd"
    fi
    echo -e "       Method: $CAPTURE_METHOD"
elif [ "$OS" = "macos" ]; then
    CAPTURE_METHOD="screencapture"
    echo -e "       Method: macOS screencapture"
fi

if [ "$CAPTURE_METHOD" = "none" ]; then
    echo -e "${YELLOW}       No screen capture method found (remote desktop disabled)${NC}"
fi

# --- Network info ---
echo ""
echo -e "${GREEN}[6/6]${NC} Network information..."
LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "unknown")
echo -e "       Your IP: ${CYAN}$LOCAL_IP${NC}"

# --- Make scripts executable ---
chmod +x "$SCRIPT_DIR/server.py" 2>/dev/null || true
chmod +x "$SCRIPT_DIR/relay.py" 2>/dev/null || true

# --- Done ---
echo ""
echo -e "${CYAN}============================================${NC}"
echo -e "${GREEN}  Installation Complete!${NC}"
echo -e "${CYAN}============================================${NC}"
echo ""
echo -e "  To start the server:"
echo -e "    ${CYAN}python3 server.py${NC}"
echo ""
echo -e "  Or use the quick start:"
echo -e "    ${CYAN}./start.sh${NC}"
echo ""
echo -e "  Then in the MiMo Mobile app:"
echo -e "    1. Open Settings"
echo -e "    2. Enter IP: ${CYAN}$LOCAL_IP${NC}"
echo -e "    3. Port: ${CYAN}8765${NC}"
echo -e "    4. Tap Connect"
echo ""
echo -e "  Or let the app auto-discover this server!"
echo ""
