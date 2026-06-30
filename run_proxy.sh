#!/bin/bash
# Auto-restart wrapper for proxy_v3.py
# Usage: setsid bash run_proxy.sh </dev/null &
export HK_CONFIG_DIR="${HK_CONFIG_DIR:-$(cd "$(dirname "$0")" && pwd)}"
export HK_ORG="${HK_ORG:-$(grep -v '^#' "$HK_CONFIG_DIR/ORG_PIN.txt" | head -1 | tr -d ' ')}"
LOG="${HK_CONFIG_DIR}/proxy.log"
while true; do
    python3 "${HK_CONFIG_DIR}/proxy_v3.py" >> "$LOG" 2>&1
    echo "[CRASH $(date)]" >> "$LOG"
    sleep 2
done
