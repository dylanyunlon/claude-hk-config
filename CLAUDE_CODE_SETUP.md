# Claude Code + claude.hk.cn 代理设置指南

## 已验证可工作的流程

Claude Code CLI 通过本地代理连接 claude.hk.cn，实现完整的 agentic loop：
1. Claude Code 发 `/v1/messages` 请求
2. 代理转发到 claude.hk.cn（cookie 认证）
3. 模型返回 `tool_use` block（如 Bash 命令）
4. **代理拦截 tool_use，不消费 tool_result，返回给 Claude Code**
5. Claude Code 在本地执行 Bash/Read/Edit/Write
6. Claude Code 发回 tool_result
7. 代理把结果作为新消息发给 claude.hk.cn 继续对话

## 文件说明

- `proxy_v2.py` — 核心代理（带 tool_use 拦截 + 429 重试）
- `raw_curl.txt` — cookie 来源（需要定期更新）

## 使用方法

### 1. 更新 cookie
从浏览器 DevTools 复制 claude.hk.cn 的请求为 cURL，更新 `raw_curl.txt`。

### 2. 生成代理配置
```bash
cd Neuron_SP/.claude-hk-config
COOKIE=$(grep -oP "(?<=-b ')[^']*" raw_curl.txt | head -1)
# proxy_v2.py 里的 COOKIE 和 ORG 变量需要手动更新
```

### 3. 启动代理
```bash
python3 -c "
import subprocess,time,socket
p=subprocess.Popen(['python3','proxy_v2.py'],
    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
    stdin=subprocess.DEVNULL,start_new_session=True)
time.sleep(4)
s=socket.socket();s.settimeout(2)
try:s.connect(('127.0.0.1',19876));s.close();print(f'UP pid={p.pid}')
except:print('DOWN')
"
```

### 4. 使用 Claude Code
```bash
export ANTHROPIC_API_KEY=sk-ant-proxy
export ANTHROPIC_BASE_URL=http://127.0.0.1:19876
export DISABLE_AUTOUPDATER=1

# 非交互模式
echo "你的任务" | claude -p --dangerously-skip-permissions --model claude-sonnet-4-6 --max-turns 5

# 交互模式（需要非 root 用户）
claude --dangerously-skip-permissions --model claude-sonnet-4-6
```

### 5. 已知限制
- claude.hk.cn 响应慢（30-60秒/轮），多轮 agentic loop 需要长超时
- 429 限流频繁，代理有 5 次重试 + 指数退避
- tool_use 名称映射：claude.hk.cn 的 `bash_tool` → Claude Code 的 `Bash`
- 第一轮 agentic loop 已验证可工作（模型返回 tool_use → Claude Code 本地执行 → 返回结果）

### 6. 用于管理小弟
```bash
# 让 Claude Code 小弟长期负责一个子系统
echo "你是 MoE 子系统负责人。用 tree -i deepspeed/core/transformer/moe/ 看架构，
然后用 grep + sed 按调用链读代码，找出链路断点，修复后 git commit push。" \
| claude -p --dangerously-skip-permissions --model claude-sonnet-4-6 --max-turns 10
```

## 代理架构

```
Claude Code CLI
    ↓ POST /v1/messages (with tools: Bash, Read, Edit, Write)
Proxy V2 (port 19876)
    ↓ POST /api/organizations/{org}/chat_conversations/{conv}/completion
claude.hk.cn (cookie auth)
    ↓ SSE: content_block_start(tool_use) + input_json_delta
Proxy V2 拦截 tool_use block, 不读 tool_result
    ↓ 返回 {"stop_reason":"tool_use", "content":[{"type":"tool_use",...}]}
Claude Code CLI 本地执行 Bash
    ↓ POST /v1/messages (with tool_result)
Proxy V2 提取 tool_result 内容作为新 prompt
    ↓ 发给 claude.hk.cn 同一个对话
循环...
```
