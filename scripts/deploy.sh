#!/bin/bash
# MiMo Mobile Server - Quick Deploy Script
# Usage: ./scripts/deploy.sh [standalone|saas|tunnel]

set -e

MODE=${1:-"standalone"}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  MiMo Mobile Server Deploy${NC}"
echo -e "${CYAN}  Mode: ${MODE}${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""

cd "$PROJECT_DIR"

case "$MODE" in
    standalone)
        echo -e "${YELLOW}Deploying standalone mode...${NC}"
        echo "  - WebSocket: ws://localhost:8765"
        echo "  - HTTP: http://localhost:8080"
        echo "  - Auth: PIN only"
        echo ""
        
        docker compose --profile standalone up -d --build
        echo ""
        echo -e "${GREEN}✓ Standalone server started${NC}"
        echo ""
        echo "Test connection:"
        echo "  curl http://localhost:8080/health"
        ;;
        
    saas)
        echo -e "${YELLOW}Deploying SaaS mode...${NC}"
        echo "  - WebSocket: wss://localhost:8765 (TLS)"
        echo "  - HTTP: https://localhost:8080"
        echo "  - Auth: PIN + JWT + API Key"
        echo "  - Analytics: Enabled"
        echo "  - Redis: Enabled"
        echo ""
        
        # Generate JWT secret if not set
        if ! grep -q "MIMO_JWT_SECRET" .env || grep -q "MIMO_JWT_SECRET=$" .env; then
            JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
            sed -i "s/MIMO_JWT_SECRET=.*/MIMO_JWT_SECRET=${JWT_SECRET}/" .env
            echo -e "${GREEN}✓ Generated JWT Secret${NC}"
        fi
        
        # Create analytics directory
        mkdir -p ~/.mimo
        
        docker compose --profile saas up -d --build
        echo ""
        echo -e "${GREEN}✓ SaaS server started${NC}"
        echo ""
        echo "Services:"
        echo "  - WebSocket: wss://localhost:8765"
        echo "  - HTTP API: https://localhost:8080"
        echo "  - Analytics: https://localhost:8080/api/analytics"
        echo "  - Redis: localhost:6379"
        echo "  - Prometheus: http://localhost:9090"
        echo "  - Grafana: http://localhost:3000"
        ;;
        
    tunnel)
        echo -e "${YELLOW}Deploying with Cloudflare Tunnel...${NC}"
        echo ""
        
        # Check for tunnel token
        if [ -z "$CLOUDFLARE_TUNNEL_TOKEN" ]; then
            echo -e "${RED}ERROR: CLOUDFLARE_TUNNEL_TOKEN not set${NC}"
            echo ""
            echo "Set it in .env or export:"
            echo "  export CLOUDFLARE_TUNNEL_TOKEN=your-token"
            echo ""
            echo "Or run setup-tunnel.sh first:"
            echo "  ./scripts/setup-tunnel.sh your-domain.com"
            exit 1
        fi
        
        # Generate JWT secret if not set
        if ! grep -q "MIMO_JWT_SECRET" .env || grep -q "MIMO_JWT_SECRET=$" .env; then
            JWT_SECRET=$(python3 -c "import secrets; print(secrets.token_hex(32))")
            sed -i "s/MIMO_JWT_SECRET=.*/MIMO_JWT_SECRET=${JWT_SECRET}/" .env
            echo -e "${GREEN}✓ Generated JWT Secret${NC}"
        fi
        
        # Create analytics directory
        mkdir -p ~/.mimo
        
        # Enable tunnel in .env
        sed -i "s/MIMO_CLOUDFLARE_TUNNEL=false/MIMO_CLOUDFLARE_TUNNEL=true/" .env
        
        docker compose --profile saas --profile tunnel up -d --build
        echo ""
        echo -e "${GREEN}✓ SaaS + Tunnel started${NC}"
        echo ""
        echo "External access:"
        echo "  - wss://${MIMO_EXTERNAL_HOST:-your-domain.com}"
        ;;
        
    *)
        echo -e "${RED}Unknown mode: $MODE${NC}"
        echo ""
        echo "Usage: ./scripts/deploy.sh [standalone|saas|tunnel]"
        echo ""
        echo "Modes:"
        echo "  standalone - Basic local deployment (PIN auth)"
        echo "  saas       - Full SaaS deployment (JWT + Analytics)"
        echo "  tunnel     - SaaS + Cloudflare Tunnel (external access)"
        exit 1
        ;;
esac

echo ""
echo -e "${CYAN}========================================${NC}"
echo -e "${CYAN}  Deploy Complete!${NC}"
echo -e "${CYAN}========================================${NC}"
