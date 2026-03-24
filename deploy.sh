#!/bin/bash
set -e

echo "========================================="
echo "  AI Inbox Manager — Production Deploy"
echo "========================================="
echo ""

# ---- Step 1: Install Docker Compose if missing ----
if ! command -v docker compose &> /dev/null && ! command -v docker-compose &> /dev/null; then
    echo "[1/5] Installing Docker Compose plugin..."
    sudo apt-get update -qq
    sudo apt-get install -y -qq docker-compose-plugin
    echo "  Done."
else
    echo "[1/5] Docker Compose already installed."
fi

# ---- Step 2: Check .env file ----
if [ ! -f .env ]; then
    echo ""
    echo "ERROR: .env file not found!"
    echo "Copy .env.example to .env and fill in your API keys:"
    echo "  cp .env.example .env"
    echo "  nano .env"
    exit 1
fi

# Check required keys
source .env
if [ -z "$OPENAI_API_KEY" ]; then
    echo "WARNING: OPENAI_API_KEY is empty in .env — AI will run in test mode (mock responses)"
fi
if [ -z "$INSTANTLY_API_KEY" ]; then
    echo "WARNING: INSTANTLY_API_KEY is empty in .env — cannot send replies via Instantly"
fi

echo "[2/5] .env file found."

# ---- Step 3: Build and start containers ----
echo "[3/5] Building containers (this may take 2-3 minutes on first run)..."
docker compose -f docker-compose.prod.yml build --quiet

echo "[4/5] Starting services..."
docker compose -f docker-compose.prod.yml up -d

# ---- Step 4: Wait and verify ----
echo "[5/5] Waiting for services to start..."
sleep 8

echo ""
echo "========================================="
echo "  Checking services..."
echo "========================================="

# Check backend
if curl -s http://localhost:8888/health > /dev/null 2>&1; then
    echo "  Backend (FastAPI)  :  OK  →  http://YOUR_IP:8888"
else
    echo "  Backend (FastAPI)  :  STARTING (may need a few more seconds)"
fi

# Check n8n
if curl -s http://localhost:5678 > /dev/null 2>&1; then
    echo "  n8n Workflows      :  OK  →  http://YOUR_IP:5678"
else
    echo "  n8n Workflows      :  STARTING (may need a few more seconds)"
fi

# Check dashboard
if curl -s http://localhost:8080 > /dev/null 2>&1; then
    echo "  Dashboard          :  OK  →  http://YOUR_IP:8080"
else
    echo "  Dashboard          :  STARTING (may need a few more seconds)"
fi

echo ""
echo "========================================="
echo "  Deploy complete!"
echo "========================================="
echo ""
echo "  Next steps:"
echo "  1. Open http://YOUR_IP:5678 → log in to n8n (admin/changeme)"
echo "  2. Import the 3 workflow JSON files from n8n-workflows/"
echo "  3. Configure Slack + Google Sheets credentials in n8n"
echo "  4. Point Instantly.ai webhook to: http://YOUR_IP:8888/webhook/instantly"
echo "  5. Open http://YOUR_IP:8080 → your dashboard"
echo ""
echo "  Useful commands:"
echo "    docker compose -f docker-compose.prod.yml logs -f        # View logs"
echo "    docker compose -f docker-compose.prod.yml restart        # Restart all"
echo "    docker compose -f docker-compose.prod.yml down           # Stop all"
echo ""
