"""Proxy V3: Claude Code CLI -> claude.hk.cn (cookie auth)

Fixes over V2:
1. Pre-warm conv at startup (not in request path)
2. HEAD/GET return instantly (no mkconv)
3. 429 retry interval: 5*(retry+1) instead of 20*(retry+1)
4. ThreadingMixIn for concurrent HEAD+POST
5. Auto-restart safe (crash-proof wrapper in run_proxy.sh)

Usage:
  # Start with auto-restart:
  nohup bash run_proxy.sh </dev/null >/dev/null 2>&1 &

  # Claude Code:
  ANTHROPIC_BASE_URL=http://127.0.0.1:19876 \\
  ANTHROPIC_API_KEY=sk-ant-proxy \\
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \\
  claude -p "task" --max-turns 5 --dangerously-skip-permissions
"""
import http.server, socketserver, json, uuid, urllib.request, sys, time, re, os

# --- Config: read from claude-hk-config ---
_CFG_DIR = os.environ.get("HK_CONFIG_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__))))
_RAW_CURL = os.path.join(_CFG_DIR, "raw_curl.txt")

if os.path.exists(_RAW_CURL):
    _raw = open(_RAW_CURL).read()
    COOKIE = re.search(r"-b '([^']*)'", _raw).group(1)
else:
    COOKIE = os.environ.get("HK_COOKIE", "")

ORG = os.environ.get("HK_ORG", "")
if not ORG:
    # Try ORG_PIN.txt
    _pin = os.path.join(_CFG_DIR, "ORG_PIN.txt")
    if os.path.exists(_pin):
        for line in open(_pin):
            line = line.strip()
            if line and not line.startswith("#"):
                ORG = line; break

O = "https://claude.hk.cn"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
HDR = {"Content-Type":"application/json","origin":O,"user-agent":UA,
       "referer":O+"/new","anthropic-client-platform":"web_claude_ai",
       "accept":"text/event-stream","accept-language":"zh-CN,zh;q=0.9",
       "sec-fetch-dest":"empty","sec-fetch-mode":"cors","sec-fetch-site":"same-origin"}
PORT = int(os.environ.get("PROXY_PORT", "19876"))

# --- Shared state ---
conv_id = None
conv_lock = __import__("threading").Lock()

def _req(url, data):
    r = urllib.request.Request(url, json.dumps(data).encode(), method="POST")
    for k,v in HDR.items(): r.add_header(k,v)
    r.add_header("Cookie", COOKIE)
    return r

def mkconv():
    """Pre-allocate a conversation UUID. Actual creation happens on first completion call."""
    global conv_id
    with conv_lock:
        conv_id = str(uuid.uuid4())
    print(f"[px] conv={conv_id} (pre-allocated)", flush=True)
    return conv_id

# --- PRE-WARM: create conv at startup ---
print("[px] pre-warming conv...", flush=True)
mkconv()

class Handler(http.server.BaseHTTPRequestHandler):
    # --- HEAD/GET: instant response, no side effects ---
    def do_HEAD(self):
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
        except: pass

    def do_OPTIONS(self):
        try:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "*")
            self.end_headers()
        except: pass

    def do_GET(self):
        try:
            b = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)
        except: pass

    # --- POST: the real work ---
    def do_POST(self):
        global conv_id
        path = self.path
        print(f"[px] POST {path}", flush=True)
        try:
            # Non-messages endpoints: return dummy
            if "/v1/messages" not in path:
                b = json.dumps({"type":"count","count":500}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(b)))
                self.end_headers()
                self.wfile.write(b)
                return

            # Read body
            cl = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(cl))

            # Extract last user message
            prompt = ""
            for m in body.get("messages", []):
                if m.get("role") == "user":
                    c = m.get("content", "")
                    if isinstance(c, str):
                        prompt = c
                    elif isinstance(c, list):
                        parts = []
                        for item in c:
                            if isinstance(item, dict):
                                if item.get("type") == "text":
                                    parts.append(item["text"])
                                elif item.get("type") == "tool_result":
                                    tool_id = item.get("tool_use_id", "")
                                    ct = item.get("content", "")
                                    result_text = ""
                                    if isinstance(ct, list):
                                        for ci in ct:
                                            if isinstance(ci, dict) and ci.get("type") == "text":
                                                result_text += ci["text"]
                                    elif isinstance(ct, str):
                                        result_text = ct
                                    parts.append(f"I executed the tool you requested. Here is the output:\n```\n{result_text}\n```\nNow proceed to the next step. Continue using Bash tool for each step.")
                        prompt = "\n".join(parts)
            if not prompt:
                prompt = "Continue"
            print(f"[px] prompt={len(prompt)}c", flush=True)

            # Ensure conv exists (should be pre-warmed)
            if not conv_id:
                mkconv()
            if not conv_id:
                self.send_error(502, "Cannot create conversation")
                return

            # Build tools list from Claude Code's tools
            cc_tools = []
            for t in body.get("tools", []):
                if t.get("name") in ("Bash","Read","Edit","Write","MultiEdit",
                                      "Grep","Glob","TodoRead","TodoWrite"):
                    cc_tools.append({
                        "name": t["name"],
                        "description": t.get("description", ""),
                        "input_schema": t.get("input_schema",
                            {"type":"object","properties":{}})
                    })

            hi = str(uuid.uuid4())
            ai = str(uuid.uuid4())

            # Send to claude.hk.cn
            # First call creates conv; subsequent calls reuse it for agentic loop
            print(f"[px] completion tools={len(cc_tools)}", flush=True)
            resp = None
            for retry in range(8):
                hi = str(uuid.uuid4())
                ai = str(uuid.uuid4())
                with conv_lock:
                    use_conv = conv_id if conv_id else str(uuid.uuid4())
                    is_new = (conv_id is None)
                    if is_new:
                        conv_id = use_conv

                payload = {"prompt": prompt,
                         "timezone": "Asia/Shanghai",
                         "locale": "en-US",
                         "model": "claude-sonnet-4-6",
                         "effort": "high",
                         "thinking_mode": "off",
                         "tools": cc_tools,
                         "turn_message_uuids": {
                             "human_message_uuid": hi,
                             "assistant_message_uuid": ai
                         },
                         "attachments": [], "files": [],
                         "sync_sources": [],
                         "rendering_mode": "messages"}
                if is_new:
                    payload["create_conversation_params"] = {
                        "name": "",
                        "model": "claude-sonnet-4-6",
                        "include_conversation_preferences": True,
                        "is_temporary": True
                    }

                try:
                    resp = urllib.request.urlopen(_req(
                        f"{O}/api/organizations/{ORG}/chat_conversations/{use_conv}/completion",
                        payload
                    ), timeout=300)
                    print(f"[px] got resp (conv={use_conv[:8]} new={is_new})", flush=True)
                    break
                except urllib.error.HTTPError as e:
                    print(f"[px] HTTP {e.code} retry {retry+1}/8", flush=True)
                    if e.code in (429, 502, 503):
                        time.sleep(5 * (retry + 1))
                        if e.code == 429 and retry >= 3:
                            # Fresh conv on persistent 429
                            with conv_lock:
                                conv_id = None
                        continue
                    raise

            if not resp:
                self.send_error(502, "All retries exhausted")
                return

            # Parse SSE — handle both text and tool_use blocks
            blocks = []
            cur = None
            for line in resp:
                line = line.decode("utf-8", errors="replace").strip()
                if not line.startswith("data: "):
                    continue
                try:
                    d = json.loads(line[6:])
                    t = d.get("type", "")

                    if t == "content_block_start":
                        cb = d.get("content_block", {})
                        ct = cb.get("type", "")
                        if ct == "text":
                            cur = {"type": "text", "text": ""}
                        elif ct == "tool_use":
                            name = cb.get("name", "")
                            # Map claude.hk.cn names to Claude Code names
                            if name == "bash_tool": name = "Bash"
                            cur = {
                                "type": "tool_use",
                                "id": cb.get("id", f"toolu_{uuid.uuid4().hex[:24]}"),
                                "name": name,
                                "input": {},
                                "_raw": ""
                            }

                    elif t == "content_block_delta":
                        delta = d.get("delta", {})
                        dt = delta.get("type", "")
                        if dt == "text_delta" and cur and cur["type"] == "text":
                            cur["text"] += delta.get("text", "")
                        elif dt == "input_json_delta" and cur and cur["type"] == "tool_use":
                            cur["_raw"] += delta.get("partial_json", "")

                    elif t == "content_block_stop":
                        if cur:
                            if cur["type"] == "tool_use":
                                raw = cur.pop("_raw", "")
                                try:
                                    p = json.loads(raw)
                                    if "command" in p:
                                        cur["input"] = {"command": p["command"]}
                                    else:
                                        cur["input"] = p
                                except:
                                    cur["input"] = {"command": raw}
                            blocks.append(cur)
                            # Stop reading after first tool_use
                            if cur["type"] == "tool_use":
                                cur = None
                                break
                            cur = None

                    elif t == "message_stop":
                        break
                except json.JSONDecodeError:
                    pass

            has_tu = any(b["type"] == "tool_use" for b in blocks)
            print(f"[px] blocks={len(blocks)} tool_use={has_tu}", flush=True)

            # Build Anthropic API response
            resp_body = {
                "id": f"msg_{hi[:8]}",
                "type": "message",
                "role": "assistant",
                "content": blocks if blocks else [{"type": "text", "text": "OK"}],
                "model": "claude-sonnet-4-6",
                "stop_reason": "tool_use" if has_tu else "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 500, "output_tokens": 200}
            }
            rb = json.dumps(resp_body).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(rb)))
            self.end_headers()
            self.wfile.write(rb)
            print("[px] sent", flush=True)

        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[px] ERR: {e}", flush=True)
            try:
                self.send_error(500, str(e))
            except:
                pass

    def log_message(self, *a):
        pass  # suppress default logging

class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True

print(f"[px] UP :{PORT} (threaded, conv={conv_id})", flush=True)
ThreadedServer(("127.0.0.1", PORT), Handler).serve_forever()
