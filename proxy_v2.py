"""Proxy v2: intercept tool_use, return it to Claude Code for local execution."""
import http.server, json, uuid, urllib.request, re, sys
from http.server import HTTPServer

COOKIE = re.search(r"-b '([^']*)'", open('.claude-hk-config/raw_curl.txt').read()).group(1)
ORG = "8db91fab-aa1e-4fcf-bf00-865d3f094c58"
O = "https://claude.hk.cn"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/149.0.0.0 Safari/537.36"
HDR = {"Content-Type":"application/json","origin":O,"user-agent":UA,"referer":O+"/","anthropic-client-platform":"web_claude_ai"}
conv_id = None

def api(url, data):
    r = urllib.request.Request(url, data=json.dumps(data).encode(), method="POST")
    for k,v in HDR.items(): r.add_header(k,v)
    r.add_header("Cookie", COOKIE); return r

def new_conv():
    global conv_id
    d = json.loads(urllib.request.urlopen(api(
        f"{O}/api/organizations/{ORG}/chat_conversations",
        {"name":"cc-v2","model":"claude-sonnet-4-6","is_temporary":True}
    ), timeout=15).read().decode())
    conv_id = d["uuid"]; return conv_id

class Handler(http.server.BaseHTTPRequestHandler):
    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        self.end_headers()

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type","application/json")
        rb = b'{"status":"ok"}'
        self.send_header("Content-Length",str(len(rb)))
        self.end_headers()
        self.wfile.write(rb)

    def do_POST(self):
        try: self._handle()
        except Exception as e:
            import traceback; traceback.print_exc()
            try: self.send_error(500, str(e))
            except: pass

    def _handle(self):
        global conv_id
        if "/v1/messages" not in self.path:
            # Handle HEAD, count_tokens etc
            if self.path.startswith("/v1/"):
                self.send_response(200)
                self.send_header("Content-Type","application/json")
                rb = json.dumps({"type":"count","count":500}).encode()
                self.send_header("Content-Length",str(len(rb)))
                self.end_headers()
                self.wfile.write(rb)
                return
            self.send_error(404); return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length",0))))
        
        # Extract prompt from messages — only use the LAST user message
        msgs = body.get("messages",[])
        # Claude Code sends full conversation history, but claude.hk.cn
        # already has context from previous turns in the same conversation
        prompt_parts = []
        last_user_msg = None
        for m in msgs:
            if m.get("role") == "user":
                last_user_msg = m
        
        if last_user_msg:
            c = last_user_msg.get("content","")
            if isinstance(c, str):
                prompt_parts.append(c)
            elif isinstance(c, list):
                for item in c:
                    if isinstance(item, dict):
                        if item.get("type") == "text":
                            prompt_parts.append(item["text"])
                        elif item.get("type") == "tool_result":
                            content = item.get("content","")
                            if isinstance(content, list):
                                for ci in content:
                                    if isinstance(ci, dict) and ci.get("type") == "text":
                                        prompt_parts.append(f"工具执行结果:\n{ci['text']}")
                            elif isinstance(content, str):
                                prompt_parts.append(f"工具执行结果:\n{content}")
        
        prompt = "\n".join(prompt_parts)
        if not prompt:
            prompt = "Continue"
        
        stream = body.get("stream", False)
        if not conv_id: new_conv()
        
        hi, ai = str(uuid.uuid4()), str(uuid.uuid4())
        
        # 不传 repl_v0 工具！让 claude.hk.cn 不能自动执行
        # 传 Claude Code 的工具定义，让模型返回 tool_use
        hk_tools = body.get("tools", [])
        # 过滤掉 server-side 工具类型，只保留 function 工具
        clean_tools = []
        for t in hk_tools:
            if t.get("type") == "custom" or "input_schema" in t:
                clean_tools.append({
                    "name": t.get("name",""),
                    "description": t.get("description",""),
                    "input_schema": t.get("input_schema", {"type":"object","properties":{}})
                })
        
        hk_data = {
            "prompt": prompt,
            "timezone": "Asia/Shanghai",
            "model": "claude-sonnet-4-6",
            "effort": "high",
            "thinking_mode": "off",
            "tools": clean_tools if clean_tools else [],  # 不传 repl_v0
            "turn_message_uuids": {"human_message_uuid": hi, "assistant_message_uuid": ai},
            "attachments": [], "files": [], "rendering_mode": "messages"
        }
        
        try:
            resp = None
            for _retry in range(5):
                try:
                    resp = urllib.request.urlopen(api(
                        f"{O}/api/organizations/{ORG}/chat_conversations/{conv_id}/completion",
                        hk_data
                    ), timeout=180)
                    break
                except urllib.error.HTTPError as he:
                    if he.code in (429, 502, 503):
                        import time as _t; _t.sleep(8 * (_retry + 1))
                        if _retry < 4: continue
                    raise
            if resp is None:
                self.send_error(502, "All retries failed"); return
        except Exception as e:
            self.send_error(502, str(e)); return
        
        # Parse SSE and build Anthropic API response
        content_blocks = []
        current_block = None
        
        for line in resp:
            line = line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "): continue
            try:
                d = json.loads(line[6:])
                etype = d.get("type","")
                
                if etype == "content_block_start":
                    cb = d.get("content_block", {})
                    ctype = cb.get("type","")
                    if ctype == "text":
                        current_block = {"type":"text","text":""}
                    elif ctype == "tool_use":
                        tool_name = cb.get("name","")
                        # Map claude.hk.cn tool names to Claude Code tool names
                        if tool_name == "bash_tool": tool_name = "Bash"
                        current_block = {
                            "type": "tool_use",
                            "id": cb.get("id", f"toolu_{uuid.uuid4().hex[:24]}"),
                            "name": tool_name,
                            "input": {}
                        }
                
                elif etype == "content_block_delta":
                    delta = d.get("delta",{})
                    dtype = delta.get("type","")
                    if dtype == "text_delta" and current_block and current_block["type"] == "text":
                        current_block["text"] += delta.get("text","")
                    elif dtype == "input_json_delta" and current_block and current_block["type"] == "tool_use":
                        partial = delta.get("partial_json","")
                        current_block['_raw_input'] = current_block.get('_raw_input',"") + partial
                
                elif etype == "content_block_stop":
                    if current_block:
                        if current_block["type"] == "tool_use" and '_raw_input' in current_block:
                            raw = current_block.pop('_raw_input')
                            try:
                                parsed = json.loads(raw)
                                # bash_tool sends {"command":"...","description":"..."}
                                # Claude Code Bash expects {"command":"..."}
                                if "command" in parsed:
                                    current_block["input"] = {"command": parsed["command"]}
                                else:
                                    current_block["input"] = parsed
                            except:
                                current_block["input"] = {"command": raw}
                        elif current_block["type"] == "tool_use" and '_raw_input' not in current_block:
                            pass
                        content_blocks.append(current_block)
                        
                        # If this is a tool_use block, stop reading — don't consume tool_result
                        if current_block["type"] == "tool_use":
                            current_block = None
                            break
                        current_block = None
                
                elif etype == "message_stop":
                    break
                    
            except json.JSONDecodeError:
                pass
        
        # Determine stop_reason
        has_tool_use = any(b["type"] == "tool_use" for b in content_blocks)
        stop_reason = "tool_use" if has_tool_use else "end_turn"
        
        # Build response
        resp_body = {
            "id": f"msg_{hi[:8]}",
            "type": "message",
            "role": "assistant",
            "content": content_blocks,
            "model": "claude-sonnet-4-6",
            "stop_reason": stop_reason,
            "stop_sequence": None,
            "usage": {"input_tokens": 500, "output_tokens": 200}
        }
        
        rb = json.dumps(resp_body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(rb)))
        self.end_headers()
        self.wfile.write(rb)
    
    def log_message(self, f, *a): 
        import sys; sys.stderr.write(f"[proxy] {a[0] if a else ''}\n"); sys.stderr.flush()

print("PROXY V2 on 19876 — tool_use interception", flush=True)
HTTPServer(("127.0.0.1", 19876), Handler).serve_forever()
