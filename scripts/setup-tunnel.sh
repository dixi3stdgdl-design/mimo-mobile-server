#!/bin/bash
# Cloudflare Tunnel Quick Setup for MiMo Mobile
# Usage: ./scripts/setup-tunnel.sh your-domain.com

set -e

DOMAIN=${1:-""}
TUNNEL_NAME="mimo-mobile"
CONFIG_DIR="$HOME/.cloudflared"
CONFIG_FILE="$CONFIG_DIR/config.yml"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Cloudflare Tunnel Setup for MiMo${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

# Check prerequisites
if ! command -v cloudflared &> /dev/null; then
    echo -e "${RED}ERROR: cloudflared not installed${NC}"
    echo ""
    echo "Install cloudflared:"
    echo "  - macOS: brew install cloudflare/cloudflare/cloudflared"
    echo "  - Linux: https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
    echo "  - Docker: docker pull cloudflare/cloudflared"
    exit 1
fi

if [ -z "$DOMAIN" ]; then
    read -p "Enter your domain (e.g., mimo.yourdomain.com): " DOMAIN
fi

if [ -z "$DOMAIN" ]; then
    echo -e "${RED}ERROR: Domain is required${NC}"
    exit 1
fi

echo -e "${YELLOW}Setting up tunnel for: ${DOMAIN}${NC}"
echo ""

# Check if logged in
echo "1. Checking Cloudflare authentication..."
if ! cloudflared tunnel list &> /dev/null; then
    echo -e "${YELLOW}Not logged in. Starting login...${NC}"
    cloudflared tunnel login
fi
echo -e "${GREEN}✓ Authenticated${NC}"

# Create tunnel
echo "2. Creating tunnel: ${TUNNEL_NAME}..."
if cloudflared tunnel list | grep -q "${TUNNEL_NAME}"; then
    echo -e "${YELLOW}Tunnel ${TUNNEL_NAME} already exists${NC}"
else
    cloudflared tunnel create "${TUNNEL_NAME}"
    echo -e "${GREEN}✓ Tunnel created${NC}"
fi

# Route DNS
echo "3. Routing DNS..."
cloudflared tunnel route dns "${TUNNEL_NAME}" "${DOMAIN}" || true
echo -e "${GREEN}✓ DNS routed${NC}"

# Create config
echo "4. Creating configuration..."
mkdir -p "$CONFIG_DIR"

cat > "$CONFIG_FILE" << EOF
tunnel: ${TUNNEL_NAME}
credentials-file: ${CONFIG_DIR}/credentials.json

ingress:
  - hostname: ${DOMAIN}
    service: https://localhost:8765
    originRequest:
      noTLSVerify: true
      connectTimeout: 30s
  - service: http_status:404
EOF

echo -e "${GREEN}✓ Config written to: ${CONFIG_FILE}${NC}"

# Create systemd service (Linux only)
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "5. Creating systemd service..."
    sudo tee /etc/systemd/system/cloudflared.service > /dev/null << EOF
[Unit]
Description=Cloudflare Tunnel for MiMo
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --config ${CONFIG_FILE} run
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    echo -e "${GREEN}✓ Systemd service created${NC}"
fi

echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Next steps:"
echo ""
echo "1. Start the tunnel:"
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "   sudo systemctl start cloudflared"
else
    echo "   cloudflared tunnel --config ${CONFIG_FILE} run"
fi
echo ""
echo "2. Start MiMo Server with TLS:"
echo "   MIMO_TLS_ENABLED=true MIMO_EXTERNAL_HOST=${DOMAIN} docker compose --profile saas up -d"
echo ""
echo "3. Your external WebSocket URL:"
echo "   wss://${DOMAIN}"
echo ""
echo "4. Test connection:"
echo "   curl https://${DOMAIN}/health"
echo ""
