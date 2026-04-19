#!/bin/bash

# Credit Scoring Application Stop Script
# Uses PID files for clean shutdown — no blind kill-by-port.

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

PID_DIR="${PID_DIR:-/tmp}"
BENTOML_PID_FILE="$PID_DIR/credit_scoring_bentoml.pid"
STREAMLIT_PID_FILE="$PID_DIR/credit_scoring_streamlit.pid"

echo -e "${YELLOW}🛑 Stopping Credit Scoring services...${NC}"

_stop_service() {
    local pid_file="$1"
    local label="$2"
    if [ -f "$pid_file" ]; then
        local pid
        pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            echo -e "${YELLOW}  Sending SIGTERM to $label (PID $pid)...${NC}"
            kill "$pid" 2>/dev/null || true
            # Wait up to 5 seconds
            for i in $(seq 1 10); do
                if ! kill -0 "$pid" 2>/dev/null; then break; fi
                sleep 0.5
            done
            if kill -0 "$pid" 2>/dev/null; then
                echo -e "${YELLOW}  Force-killing $label (PID $pid)...${NC}"
                kill -9 "$pid" 2>/dev/null || true
            fi
            echo -e "${GREEN}✅ $label stopped${NC}"
        else
            echo -e "${YELLOW}⚠️  $label (PID $pid) is not running${NC}"
        fi
        rm -f "$pid_file"
    else
        echo -e "${YELLOW}⚠️  No PID file for $label${NC}"
    fi
}

_stop_service "$BENTOML_PID_FILE" "BentoML"
_stop_service "$STREAMLIT_PID_FILE" "Streamlit"

echo -e "${GREEN}✅ All services stopped${NC}"
