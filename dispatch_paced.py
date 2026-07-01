#!/usr/bin/env python3
"""dispatch_paced.py — dispatch a task file to a sub-Claude with 429 backoff.
Usage: python3 dispatch_paced.py <task.md> [conv_id]
Handles the shared-cookie rate limit by retrying on HTTP 429 with backoff.
"""
import re, subprocess, json, uuid, time, sys

RAW=open('raw_curl.txt').read()
COOKIE=re.search(r"-b '([^']*)'",RAW).group(1)
UA=re.search(r"user-agent: ([^']+)",RAW).group(1)
ORG=re.search(r'[0-9a-f-]{36}',open('ORG_PIN.txt').read()).group(0)
COMMON=["-H",f"user-agent: {UA}","-H","referer: https://claude.hk.cn/",
        "-H","anthropic-client-platform: web_claude_ai","-b",COOKIE]

def create_conv(name):
    r=subprocess.run(["curl","-s","-X","POST",
        f"https://claude.hk.cn/api/organizations/{ORG}/chat_conversations",
        "-H","Content-Type: application/json","-H","origin: https://claude.hk.cn",*COMMON,
        "--data-raw",json.dumps({"name":name,"model":"claude-sonnet-4-6","is_temporary":False})],
        capture_output=True,text=True,timeout=30)
    return json.loads(r.stdout)["uuid"]

def send(conv_id, prompt, max_retries=6):
    body={"prompt":prompt,"timezone":"Asia/Shanghai","model":"claude-sonnet-4-6",
      "effort":"medium","thinking_mode":"off",
      "tools":[{"type":"repl_v0","name":"repl"}],
      "turn_message_uuids":{"human_message_uuid":str(uuid.uuid4()),"assistant_message_uuid":str(uuid.uuid4())},
      "attachments":[],"files":[],"rendering_mode":"messages"}
    for attempt in range(max_retries):
        r=subprocess.run(["curl","-s","-N",
            f"https://claude.hk.cn/api/organizations/{ORG}/chat_conversations/{conv_id}/completion",
            "-H","accept: text/event-stream","-H","content-type: application/json",
            "-H","origin: https://claude.hk.cn",*COMMON,"--data-raw",json.dumps(body)],
            capture_output=True,text=True,timeout=280)
        out=r.stdout
        if '"type":"error"' in out and '429' not in out and 'permission_error' not in out:
            pass
        if 'permission_error' in out or '频率过快' in out or 'reached the limit' in out:
            wait=15*(attempt+1)
            print(f"  [429 rate limit — backoff {wait}s, attempt {attempt+1}/{max_retries}]",flush=True)
            time.sleep(wait); continue
        # parse
        tool=0; text=""
        for line in out.splitlines():
            if line.startswith("data:"):
                try:
                    d=json.loads(line[5:].strip()); t=d.get("type")
                    if t=="content_block_start" and d.get("content_block",{}).get("type")=="tool_use": tool+=1
                    elif t=="content_block_delta": text+=d.get("delta",{}).get("text","")
                except: pass
        if text or tool: return tool,text
        # empty -> maybe transient, brief retry
        time.sleep(8)
    return 0,"(exhausted retries)"

if __name__=="__main__":
    task=open(sys.argv[1]).read()
    conv=sys.argv[2] if len(sys.argv)>2 else create_conv("subtask-"+sys.argv[1])
    print(f"CONV: {conv}",flush=True)
    tool,text=send(conv,task)
    print(f"[tool calls: {tool}]",flush=True)
    print("="*70)
    print(text[-3000:])
    open(sys.argv[1]+'.conv','w').write(conv)
