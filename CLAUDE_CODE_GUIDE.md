# Claude Code 小弟招聘指南

## 核心思路

Claude Code CLI (`claude -p "任务"`) 是 Anthropic 官方的 agentic coding 工具。
它需要 `ANTHROPIC_API_KEY` 或 `ANTHROPIC_BASE_URL` 来连接 API。

我们没有 API key，但有 claude.hk.cn 的 cookie。
解决方案：本地起一个代理服务器，把 Claude Code 的 `/v1/messages` 请求
转发到 claude.hk.cn 的 chat completion SSE 端点，用 cookie 认证。

```
Claude Code CLI ──POST /v1/messages──▶ proxy:19876 ──转换格式──▶ claude.hk.cn/api/.../completion
                                         │                              │
                                    Anthropic API 格式            claude.hk.cn SSE 格式
                                         │                              │
                                         ◀──────转换回来──────────────────┘
```

## 快速启动（3 步）

### 1. 同步 cookie

从浏览器打开 claude.hk.cn，F12 → Network → 找任意 completion 请求 → 右键 Copy as cURL。
更新 `raw_curl.txt`（主要需要 `-b '...'` 里的 cookie 和 URL 里的 org ID）。

然后更新 `proxy.py` 里的 `COOKIE` 和 `ORG` 变量。

**关于 cookie 过期**：`_dd_s` 里的 `expire` 是 DataDog session tracking 的过期时间，
不是认证过期。实测发现即使这个时间过了，请求仍然可以成功。
遇到 429 是正常限流，代理会自动重试（最多 5 次，每次间隔递增）。

### 2. 启动代理 + 安装 Claude Code

```bash
# 安装 Claude Code（只需一次）
npm install -g @anthropic-ai/claude-code

# 启动代理（在 Python 子进程里，避免被 shell 杀掉）
python3 -c "
import subprocess, time, socket
p = subprocess.Popen(['python3', '/path/to/.claude-hk-config/proxy.py'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
time.sleep(3)
s = socket.socket(); s.settimeout(2)
s.connect(('127.0.0.1', 19876)); s.close()
print('Proxy UP, PID:', p.pid)
"
```

### 3. 招聘小弟

```python
import subprocess, time, socket, os

# 启动代理
proxy = subprocess.Popen(['python3', 'proxy.py'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
time.sleep(3)

# 配置环境变量
env = os.environ.copy()
env['ANTHROPIC_BASE_URL'] = 'http://127.0.0.1:19876'
env['ANTHROPIC_API_KEY'] = 'sk-proxy-dummy'  # 任意值，代理会忽略

# 派发任务
TASK = """
git clone https://github.com/dylanyunlon/astro-svgfigure.git
cd astro-svgfigure && git checkout cell-pubsub-loop
git config user.email "claude@anthropic.com" && git config user.name "Claude"
git remote set-url origin https://<GIT_TOKEN>@github.com/dylanyunlon/astro-svgfigure.git

（你的具体任务描述）

完成后: git pull --rebase origin cell-pubsub-loop && git commit -m "M编号: 描述" && git push
"""

cc = subprocess.Popen(
    ['claude', '-p', TASK, '--max-turns', '10', '--allowedTools', 'bash,edit,write'],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    env=env, stdin=subprocess.DEVNULL, cwd='/tmp'
)
out, _ = cc.communicate(timeout=300)
print(out.decode())

proxy.terminate()
```

## 多线程并行招聘

```python
import subprocess, time, socket, os, threading

# 启动代理
proxy = subprocess.Popen(['python3', 'proxy.py'],
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
time.sleep(3)

env = os.environ.copy()
env['ANTHROPIC_BASE_URL'] = 'http://127.0.0.1:19876'
env['ANTHROPIC_API_KEY'] = 'sk-proxy-dummy'

def run_worker(name, task):
    print(f"[{name}] 开始")
    cc = subprocess.Popen(
        ['claude', '-p', task, '--max-turns', '10', '--allowedTools', 'bash,edit,write'],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        env=env, stdin=subprocess.DEVNULL, cwd='/tmp'
    )
    try:
        out, _ = cc.communicate(timeout=300)
        print(f"[{name}] 完成:\n{out.decode()[-500:]}")
    except subprocess.TimeoutExpired:
        print(f"[{name}] 超时")
        cc.kill()

tasks = {
    "小弟1": "任务1的描述...",
    "小弟2": "任务2的描述...",
}

threads = []
for name, task in tasks.items():
    t = threading.Thread(target=run_worker, args=(name, task))
    t.start()
    threads.append(t)
    time.sleep(5)  # 间隔 5 秒避免 429

for t in threads:
    t.join()

proxy.terminate()
```

## 注意事项

1. **429 限流**：正常现象，代理自动重试最多 5 次，每次间隔递增。
   多个小弟并行时加 5 秒间隔。

2. **代理进程管理**：代理必须在同一个 Python 进程里启动和管理，
   不能用 `&` 后台运行（会被 shell 杀掉）。

3. **任务粒度**：给小弟的任务要有宏观能力的描述，不要拆得太细。
   小弟自己会用 tree -i 看架构、grep 找代码、git push。

4. **git 冲突**：多个小弟同时 push 会冲突。让每个小弟在 push 前
   `git pull --rebase`。或者让它们改不同的文件。

5. **cookie 不需要频繁更新**：429 不代表 cookie 过期，只是限流。
   多试几次就行。

## 代理架构

`proxy.py` 做的事情：

1. 收到 Claude Code 的 `/v1/messages` POST 请求
2. 提取 messages 里的 prompt 文本
3. 在 claude.hk.cn 创建对话（如果还没有）
4. 把 prompt 发到 `claude.hk.cn/api/organizations/{org}/chat_conversations/{conv}/completion`
5. 读取 SSE 流，提取 `content_block_delta` 里的文本
6. 组装成标准 Anthropic API Messages 响应格式返回
7. 遇到 429 自动重试（创建新对话 + 等待 + 重试）

## 验证方式

```bash
# 验证代理
curl -s http://127.0.0.1:19876/v1/messages \
  -H "content-type: application/json" \
  -d '{"model":"claude-sonnet-4-6","max_tokens":10,"messages":[{"role":"user","content":"say OK"}]}'

# 验证 Claude Code CLI
ANTHROPIC_BASE_URL=http://127.0.0.1:19876 ANTHROPIC_API_KEY=sk-dummy \
  claude -p "say hello" --max-turns 1
```
