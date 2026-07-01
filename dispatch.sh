#!/usr/bin/env bash
# dispatch.sh — dispatch ONE task to a sub-Claude (Sonnet 4.6) with a bash container.
# The sub-Claude runs its OWN agentic loop. This script just sends the task and streams back.
#
# Usage:
#   bash dispatch.sh "task prompt"
#   TASK_FILE=task.md bash dispatch.sh
#   CONV_ID=xxxx bash dispatch.sh "Continue"        # continue a truncated turn
set -euo pipefail
SD="$(cd "$(dirname "$0")" && pwd)"; cd "$SD"

RAW_CURL="$SD/raw_curl.txt"
[ -f "$RAW_CURL" ] || { echo "ERROR: raw_curl.txt missing"; exit 1; }

# Cookie + UA from raw_curl; ORG from ORG_PIN.txt (single source of truth)
COOKIE=$(grep -oP "(?<=-b ')[^']*" "$RAW_CURL" | head -1)
UA=$(grep -oP "(?<=user-agent: )[^']+" "$RAW_CURL" | head -1)
ORG=$(grep -vE '^\s*#' "$SD/ORG_PIN.txt" | grep -oE '[0-9a-f-]{36}' | head -1)
[ -n "$COOKIE" ] && [ -n "$ORG" ] || { echo "ERROR: cookie/org empty"; exit 1; }

# Verify ORG is reachable; if not, fall back to whatever the cookie actually owns.
LIVE=$(curl -s "https://claude.hk.cn/api/organizations" -H "accept: application/json" \
  -H "user-agent: $UA" -b "$COOKIE" 2>/dev/null \
  | python3 -c "import sys,json;o=json.load(sys.stdin);print(o[0]['uuid'] if isinstance(o,list) and o else '')" 2>/dev/null || echo "")
if [ -n "$LIVE" ] && [ "$LIVE" != "$ORG" ]; then
  echo "WARN: ORG_PIN=$ORG unreachable; cookie owns $LIVE. Using live. (Fix ORG_PIN.txt!)"
  ORG="$LIVE"
fi
echo "Org: $ORG"

COMMON=(-H "user-agent: $UA" -H "referer: https://claude.hk.cn/"
        -H "anthropic-client-platform: web_claude_ai" -b "$COOKIE")

if [ -n "${TASK_FILE:-}" ] && [ -f "$TASK_FILE" ]; then PROMPT=$(cat "$TASK_FILE")
elif [ $# -gt 0 ]; then PROMPT="$*"
else echo "Usage: bash dispatch.sh \"prompt\""; exit 1; fi

ESC=$(python3 -c "import json,sys;print(json.dumps(sys.stdin.read()))" <<< "$PROMPT")
HU=$(python3 -c "import uuid;print(uuid.uuid4())"); AU=$(python3 -c "import uuid;print(uuid.uuid4())")

if [ -n "${CONV_ID:-}" ]; then
  echo "Conv (reuse): $CONV_ID"
else
  CR=$(curl -s -X POST "https://claude.hk.cn/api/organizations/$ORG/chat_conversations" \
    -H "Content-Type: application/json" -H "origin: https://claude.hk.cn" "${COMMON[@]}" \
    --data-raw '{"name":"","model":"claude-sonnet-4-6","is_temporary":false}')
  CONV_ID=$(echo "$CR" | python3 -c "import sys,json;print(json.load(sys.stdin).get('uuid',''))" 2>/dev/null || echo "")
  [ -n "$CONV_ID" ] || { echo "ERROR: create conv failed: ${CR:0:200}"; exit 1; }
  echo "Conv (new): $CONV_ID   — continue: CONV_ID=$CONV_ID bash dispatch.sh Continue"
fi

OUT="$SD/response_$(date +%Y%m%d_%H%M%S).txt"; > "$OUT"
curl -s -N "https://claude.hk.cn/api/organizations/$ORG/chat_conversations/$CONV_ID/completion" \
  -H "accept: text/event-stream" -H "content-type: application/json" \
  -H "origin: https://claude.hk.cn" "${COMMON[@]}" \
  --data-raw "{\"prompt\":$ESC,\"timezone\":\"Asia/Shanghai\",\"model\":\"claude-sonnet-4-6\",\"effort\":\"medium\",\"thinking_mode\":\"off\",\"tools\":[{\"type\":\"repl_v0\",\"name\":\"repl\"}],\"turn_message_uuids\":{\"human_message_uuid\":\"$HU\",\"assistant_message_uuid\":\"$AU\"},\"attachments\":[],\"files\":[],\"rendering_mode\":\"messages\"}" \
  | while IFS= read -r line; do
      [[ "$line" == data:* ]] || continue
      echo "${line#data: }" | python3 -c "
import sys,json
try:
    d=json.loads(sys.stdin.read()); t=d.get('type')
    if t=='content_block_delta':
        x=d.get('delta',{}).get('text','')
        if x: print(x,end='',flush=True)
    elif t=='content_block_start' and d.get('content_block',{}).get('type')=='tool_use':
        print(f\"\n[sub-claude running: {d['content_block'].get('name','')}]\",end='',flush=True)
except: pass" 2>/dev/null | tee -a "$OUT"
    done
echo ""; echo "=== saved: $OUT ($(wc -c < "$OUT") bytes) | CONV_ID=$CONV_ID ==="
