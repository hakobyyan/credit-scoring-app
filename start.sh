#!/bin/bash

# Credit Scoring Application Startup Script
# Uses PID files for clean process management.
# Ports and paths are configurable via .env or environment variables.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Load .env if present ──
if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

# ── Configuration (with defaults) ──
BENTOML_PORT="${BENTOML_PORT:-3000}"
WEBAPP_PORT="${WEBAPP_PORT:-8501}"
VENV_PATH="${VENV_PATH:-$SCRIPT_DIR/../.venv}"
SERVICE_DIR="$SCRIPT_DIR/service"
APP_DIR="$SCRIPT_DIR/app"
PID_DIR="${PID_DIR:-$SCRIPT_DIR/.pids}"
mkdir -p "$PID_DIR"
BENTOML_PID_FILE="$PID_DIR/credit_scoring_bentoml.pid"
WEBAPP_PID_FILE="$PID_DIR/credit_scoring_webapp.pid"
READYZ_URL="http://localhost:$BENTOML_PORT/readyz"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Starting Credit Scoring Application...${NC}"

# ── Check virtual environment ──
if [ ! -d "$VENV_PATH" ]; then
    echo -e "${RED}❌ Virtual environment not found at $VENV_PATH${NC}"
    echo "Please create it with: python -m venv $VENV_PATH"
    exit 1
fi

echo -e "${YELLOW}📦 Activating virtual environment...${NC}"
source "$VENV_PATH/bin/activate"

# ── Stop any existing instances (gracefully) ──
_stop_pid_file() {
    local pid_file="$1"
    local label="$2"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}  Stopping existing $label (PID $pid)...${NC}"
            kill "$pid" 2>/dev/null || true
            # Wait up to 5 seconds for graceful shutdown
            for i in $(seq 1 10); do
                if ! kill -0 "$pid" 2>/dev/null; then break; fi
                sleep 0.5
            done
            # Force kill if still running
            if kill -0 "$pid" 2>/dev/null; then
                kill -9 "$pid" 2>/dev/null || true
            fi
        fi
        rm -f "$pid_file"
    fi
}

echo -e "${YELLOW}🧹 Cleaning up existing processes...${NC}"
_stop_pid_file "$BENTOML_PID_FILE" "BentoML"
_stop_pid_file "$WEBAPP_PID_FILE" "WebApp"

# ── Start BentoML service ──
echo -e "${YELLOW}🔧 Starting BentoML API service on port $BENTOML_PORT...${NC}"
cd "$SERVICE_DIR"
BENTOML_PORT="$BENTOML_PORT" bentoml serve service:CreditScoringService --port "$BENTOML_PORT" &
BENTOML_PID=$!
echo "$BENTOML_PID" > "$BENTOML_PID_FILE"

# ── Wait for BentoML health endpoint ──
echo -e "${YELLOW}⏳ Waiting for API service to be ready...${NC}"
MAX_WAIT=30
WAITED=0
while [ $WAITED -lt $MAX_WAIT ]; do
    if curl -sf "$READYZ_URL" > /dev/null 2>&1; then
        echo -e "${GREEN}✅ BentoML API service is healthy (PID: $BENTOML_PID)${NC}"
        break
    fi
    if ! kill -0 "$BENTOML_PID" 2>/dev/null; then
        echo -e "${RED}❌ BentoML service failed to start${NC}"
        rm -f "$BENTOML_PID_FILE"
        exit 1
    fi
    sleep 1
    WAITED=$((WAITED + 1))
done

if [ $WAITED -ge $MAX_WAIT ]; then
    echo -e "${RED}❌ BentoML service did not become healthy within ${MAX_WAIT}s${NC}"
    kill "$BENTOML_PID" 2>/dev/null || true
    rm -f "$BENTOML_PID_FILE"
    exit 1
fi

# ── Start Web Application (FastAPI + Uvicorn) ──
echo -e "${YELLOW}🎨 Starting Web Application on port $WEBAPP_PORT...${NC}"
cd "$SCRIPT_DIR"
uvicorn app.server:app --host 0.0.0.0 --port "$WEBAPP_PORT" &
WEBAPP_PID=$!
echo "$WEBAPP_PID" > "$WEBAPP_PID_FILE"
sleep 2

echo ""
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ Credit Scoring Application is running!${NC}"
echo -e "${GREEN}════════════════════════════════════════════════════════════${NC}"
echo ""
echo -e "   📊 API Service:    ${YELLOW}http://localhost:$BENTOML_PORT${NC}"
echo -e "   🖥️  Web App:        ${YELLOW}http://localhost:$WEBAPP_PORT${NC}"
echo -e "   📚 API Docs:       ${YELLOW}http://localhost:$BENTOML_PORT/docs${NC}"
echo ""
echo -e "${YELLOW}Press Ctrl+C to stop all services${NC}"
echo ""

# ── Cleanup on exit ──
cleanup() {
    echo ""
    echo -e "${YELLOW}🛑 Shutting down services...${NC}"
    _stop_pid_file "$BENTOML_PID_FILE" "BentoML"
    _stop_pid_file "$WEBAPP_PID_FILE" "WebApp"
    echo -e "${GREEN}✅ All services stopped${NC}"
    exit 0
}

trap cleanup SIGINT SIGTERM

wait
