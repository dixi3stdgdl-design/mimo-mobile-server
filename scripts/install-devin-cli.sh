#!/bin/bash
# ============================================================
# Devin CLI Installer for MiMo Server
# ============================================================
# Installs Devin CLI on Linux for integration with MiMo Mobile
#
# Usage: ./install-devin-cli.sh
# ============================================================

set -e

echo "╔══════════════════════════════════════════════════════════╗"
echo "║       Devin CLI Installer for MiMo Server               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok() { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }

# ─── Step 1: Check/Install dependencies ─────────────────────
echo "[1/6] Checking dependencies..."

install_if_missing() {
    local cmd=$1
    local pkg=$2
    
    if ! command -v $cmd &> /dev/null; then
        echo "  Installing $pkg..."
        if command -v apt-get &> /dev/null; then
            sudo apt-get update -qq && sudo apt-get install -y -qq $pkg
        elif command -v dnf &> /dev/null; then
            sudo dnf install -y $pkg
        elif command -v pacman &> /dev/null; then
            sudo pacman -S --noconfirm $pkg
        elif command -v brew &> /dev/null; then
            brew install $pkg
        else
            fail "Cannot install $pkg - no supported package manager found"
        fi
        ok "$pkg installed"
    else
        ok "$pkg already installed"
    fi
}

install_if_missing curl curl
install_if_missing ca-certificates ca-certificates

# ─── Step 2: Check glibc version ────────────────────────────
echo ""
echo "[2/6] Checking glibc version..."

GLIBC_VERSION=$(ldd --version 2>&1 | head -1 | grep -oP '\d+\.\d+' | head -1)
GLIBC_MAJOR=$(echo $GLIBC_VERSION | cut -d. -f1)
GLIBC_MINOR=$(echo $GLIBC_VERSION | cut -d. -f2)

if [ "$GLIBC_MAJOR" -lt 2 ] || ([ "$GLIBC_MAJOR" -eq 2 ] && [ "$GLIBC_MINOR" -lt 28 ]); then
    fail "glibc $GLIBC_VERSION found, but >= 2.28 is required"
else
    ok "glibc $GLIBC_VERSION (>= 2.28 required)"
fi

# ─── Step 3: Check for DEVIN_API_KEY ────────────────────────
echo ""
echo "[3/6] Checking environment..."

if [ -z "$DEVIN_API_KEY" ]; then
    warn "DEVIN_API_KEY not set in environment"
    echo "  Please set it in /etc/environment or ~/.bashrc:"
    echo "  export DEVIN_API_KEY='your-api-key-here'"
    echo ""
    echo "  Get your API key from: https://devin.ai/settings"
else
    ok "DEVIN_API_KEY is set"
fi

# ─── Step 4: Install Devin CLI ──────────────────────────────
echo ""
echo "[4/6] Installing Devin CLI..."

curl -fsSL https://cli.devin.ai/install.sh | bash

# ─── Step 5: Update PATH ────────────────────────────────────
echo ""
echo "[5/6] Updating PATH..."

SHELL_RC=""
if [ -f "$HOME/.bashrc" ]; then
    SHELL_RC="$HOME/.bashrc"
elif [ -f "$HOME/.zshrc" ]; then
    SHELL_RC="$HOME/.zshrc"
fi

if [ -n "$SHELL_RC" ]; then
    if ! grep -q '.local/bin' "$SHELL_RC"; then
        echo '' >> "$SHELL_RC"
        echo '# Devin CLI' >> "$SHELL_RC"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        ok "PATH updated in $SHELL_RC"
    else
        ok "PATH already configured"
    fi
fi

# Export for current session
export PATH="$HOME/.local/bin:$PATH"

# ─── Step 6: Verify installation ────────────────────────────
echo ""
echo "[6/6] Verifying installation..."

if command -v devin &> /dev/null; then
    DEVIN_VERSION=$(devin --version 2>&1)
    ok "Devin CLI installed: $DEVIN_VERSION"
else
    # Check if it's in ~/.local/bin
    if [ -f "$HOME/.local/bin/devin" ]; then
        ok "Devin CLI installed at ~/.local/bin/devin"
        echo "  Run: source $SHELL_RC"
        echo "  Or:  export PATH=\"\$HOME/.local/bin:\$PATH\""
    else
        fail "Devin CLI not found after installation"
    fi
fi

# ─── Create environment file ────────────────────────────────
echo ""
echo "Setting up environment..."

ENV_FILE="/etc/environment"
if [ -w "$ENV_FILE" ] || [ -f "$ENV_FILE" ]; then
    if ! grep -q "DEVIN_API_KEY" "$ENV_FILE" 2>/dev/null; then
        echo "" >> "$ENV_FILE"
        echo "# Devin AI" >> "$ENV_FILE"
        echo "# DEVIN_API_KEY=your-key-here" >> "$ENV_FILE"
        ok "Environment template added to $ENV_FILE"
    fi
fi

echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║       Installation Complete!                            ║"
echo "╠══════════════════════════════════════════════════════════╣"
echo "║                                                          ║"
echo "║  Next steps:                                             ║"
echo "║                                                          ║"
echo "║  1. Set your API key:                                    ║"
echo "║     export DEVIN_API_KEY='your-key-here'                 ║"
echo "║                                                          ║"
echo "║  2. Test the installation:                               ║"
echo "║     devin --version                                      ║"
echo "║                                                          ║"
echo "║  3. Run a task:                                          ║"
echo "║     devin run \"Hello, Devin!\"                           ║"
echo "║                                                          ║"
echo "║  API Key: https://devin.ai/settings                      ║"
echo "║                                                          ║"
echo "╚══════════════════════════════════════════════════════════╝"
