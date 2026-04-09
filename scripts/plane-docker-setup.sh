#!/usr/bin/env bash
# plane-docker-setup.sh — Deploy Plane self-hosted for ClawTeam development
set -euo pipefail

PLANE_DIR="${PLANE_DIR:-$HOME/plane-selfhost}"
PLANE_PORT="${PLANE_PORT:-8082}"

echo "==> Setting up Plane self-hosted in $PLANE_DIR (port $PLANE_PORT)"

if [ -d "$PLANE_DIR/plane-app" ]; then
    echo "Plane already installed at $PLANE_DIR/plane-app"
    echo "To restart: cd $PLANE_DIR/plane-app && docker compose up -d"
    exit 0
fi

mkdir -p "$PLANE_DIR"
cd "$PLANE_DIR"

curl -fsSL -o setup.sh https://github.com/makeplane/plane/releases/latest/download/setup.sh
chmod +x setup.sh

echo ""
echo "==> Running Plane installer..."
echo "    When prompted:"
echo "    - Choose option 1 (Install)"
echo "    - Use default domain (localhost)"
echo "    - Set HTTP port to $PLANE_PORT"
echo ""

./setup.sh

echo ""
echo "==> Plane setup complete!"
echo "    Access: http://localhost:$PLANE_PORT"
echo "    1. Create an account"
echo "    2. Create a workspace"
echo "    3. Go to Settings > API Tokens > Create API Token"
echo "    4. Run: clawteam plane setup --url http://localhost:$PLANE_PORT --api-key <token>"
