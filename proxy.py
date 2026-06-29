import http.server, json, uuid, urllib.request, urllib.error, time
from http.server import HTTPServer

COOKIE = 'lastActiveOrg=97ee61c0-7dd2-4cc9-ab9c-f95c3e3f9110; ajs_anonymous_id=claudeai.v1.fd38ff3a-6fa9-4bb4-8b45-3d502873bd1f; user-sidebar-visible-on-load=true; CH-prefers-color-scheme=light; user-sidebar-pinned=false; _dd_s=aid=1f0fa0af-44f1-4b2f-8054-15dc64a41176&rum=2&id=06cd5f59-5c6a-44e6-af60-ff47db395832&created=1782439394911&expire=1782440295876; share-session=1gqups11bi4by0djkk3qfcd9o062j4r7; lastActiveOrg=97ee61c0-7dd2-4cc9-ab9c-f95c3e3f9110'
ORG = "97ee61c0-7dd2-4cc9-ab9c-f95c3e3f9110"
ORIGIN = "https://claude.hk.cn"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
conv_id = None

def create_conv():
    url = f"{ORIGIN}/api/organizations/{ORG}/chat_conversations"
    data = json.dumps({"name":"cc-worker","model":"claude-sonnet-4-6","is_temporary":False}).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    for k,v in {"Content-Type":"application/json","origin":ORIGIN,"user-agent":UA,"referer":f"{ORIGIN}/new","anthropic-client-platform":"web_claude_ai"}.items():
        req.add_header(k,v)
    req.add_header("Cookie", COOKIE)
    return json.loads(urllib.request.urlopen(req, timeout=15).read().decode()).get("uuid","")

def call_hk(prompt, model="claude-sonnet-4-6", max_retries=5):
    global conv_id
    if not conv_id:
        conv_id = create_conv()
        print(f"[proxy] conv={conv_id}", flush=True)
    
    h_id, a_id = str(uuid.uuid4()), str(uuid.uuid4())
    hk_data = json.dumps({
        "prompt": prompt, "timezone": "Asia/Shanghai", "model": model,
        "effort": "high", "thinking_mode": "off",
        "tools": [{"type":"repl_v0","name":"repl"}],
        "turn_message_uuids": {"human_message_uuid": h_id, "assistant_message_uuid": a_id},
        "attachments": [], "files": [], "rendering_mode": "messages"
    }).encode()
    
    for attempt in range(max_retries):
        hk_req = urllib.request.Request(
            f"{ORIGIN}/api/organizations/{ORG}/chat_conversations/{conv_id}/completion",
            data=hk_data, method="POST")
        for k,v in {"accept":"text/event-stream","content-type":"application/json",
                     "origin":ORIGIN,"user-agent":UA,"referer":f"{ORIGIN}/new",
                     "anthropic-client-platform":"web_claude_ai"}.items():
            hk_req.add_header(k,v)
        hk_req.add_header("Cookie", COOKIE)
        
        try:
            hk_resp = urllib.request.urlopen(hk_req, timeout=120)
            full = ""
            for line in hk_resp:
                line = line.decode("utf-8", errors="replace").strip()
                if line.startswith("data: "):
                    try:
                        d = json.loads(line[6:])
                        if d.get("type") == "content_block_delta":
                            t = d.get("delta", {}).get("text", "")
                            if t: full += t
                    except: pass
            return h_id, full
        except urllib.error.HTTPError as e:
            code = e.code
            print(f"[proxy] attempt {attempt+1}/{max_retries}: HTTP {code}", flush=True)
            if code == 429:
                wait = min(5 * (attempt + 1), 30)
                print(f"[proxy] 429 rate limit, waiting {wait}s...", flush=True)
                time.sleep(wait)
                # Create new conversation on 429
                try:
                    conv_id = create_conv()
                    print(f"[proxy] new conv={conv_id}", flush=True)
                    h_id, a_id = str(uuid.uuid4()), str(uuid.uuid4())
                    hk_data = json.dumps({
                        "prompt": prompt, "timezone": "Asia/Shanghai", "model": model,
                        "effort": "high", "thinking_mode": "off",
                        "tools": [{"type":"repl_v0","name":"repl"}],
                        "turn_message_uuids": {"human_message_uuid": h_id, "assistant_message_uuid": a_id},
                        "attachments": [], "files": [], "rendering_mode": "messages"
                    }).encode()
                except: pass
                continue
            raise
        except Exception as e:
            print(f"[proxy] attempt {attempt+1}: {e}", flush=True)
            if attempt < max_retries - 1:
                time.sleep(3)
                continue
            raise
    raise Exception("max retries exceeded")

class H(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if "/v1/messages" not in self.path:
            self.send_error(404); return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        msgs = body.get("messages", [])
        prompt = "\n".join(
            c.get("text", "") if isinstance(c, dict) else c
            for m in msgs
            for c in ([m["content"]] if isinstance(m["content"], str) else m["content"])
        )
        try:
            h_id, full = call_hk(prompt, body.get("model", "claude-sonnet-4-6"))
        except Exception as e:
            print(f"[proxy] final error: {e}", flush=True)
            self.send_error(502, str(e)); return
        
        rb = json.dumps({
            "id": f"msg_{h_id[:8]}", "type": "message", "role": "assistant",
            "content": [{"type": "text", "text": full}],
            "model": body.get("model", "claude-sonnet-4-6"),
            "stop_reason": "end_turn", "usage": {"input_tokens": 0, "output_tokens": len(full)//4}
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(rb)))
        self.end_headers()
        self.wfile.write(rb)
    
    def log_message(self, f, *a): print(f"[proxy] {a[0]}", flush=True)

print("proxy on 19876 (with retry)", flush=True)
HTTPServer(("127.0.0.1", 19876), H).serve_forever()
