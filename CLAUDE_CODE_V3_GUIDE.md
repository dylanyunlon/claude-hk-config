# Claude Code 小弟招聘指南 V3

## 上次管理者踩的坑 + 修复

### 问题1: 代理在 HEAD 请求后 mkconv() 触发 429
**症状**: Claude Code 发 `HEAD /` + `POST /v1/messages`，代理在 POST handler 里调 mkconv()→429 重试花 60-120s→Claude Code 超时断连→报 `ConnectionRefused`。

**修复**: proxy_v3.py 在启动时 **pre-warm conv**（预先创建对话），HEAD 秒回不触发任何初始化。

### 问题2: 单线程代理阻塞
**症状**: 代理在处理一个长请求时无法 accept 新连接。
**修复**: 使用 `ThreadingMixIn`。

### 问题3: ORG 过期
**症状**: `raw_curl.txt` 里的 org ID 和实际 org 不一致。
**修复**: proxy_v3.py 读 `ORG_PIN.txt` 或 `HK_ORG` 环境变量。每次开始前先 `git pull` 这个 repo。

### 问题4: Claude Code 启动阶段卡住
**症状**: Claude Code 连 TCP 成功但不发 HTTP 请求。
**原因**: Claude Code 在启动时做内部初始化（git repo检查、growthbook feature fetch），如果不在 git repo 目录里运行可能卡住。
**修复**: 在 git repo 目录里运行 `claude -p`，设 `CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1`。

### 问题5: root 用户限制
**症状**: `--dangerously-skip-permissions cannot be used with root/sudo privileges`。
**修复**: 用 `runuser -u ccworker` 以非 root 用户运行。

## 快速启动 (3步)

### 1. 同步 config + 启动代理
```bash
cd /path/to/claude-hk-config
git pull

# 更新 ORG (如果 cookie 换了)
COOKIE=$(grep -oP "(?<=-b ')[^']*" raw_curl.txt | head -1)
NEW_ORG=$(curl -s "https://claude.hk.cn/api/organizations" \
  -H "accept: application/json" \
  -H "user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" \
  -H "anthropic-client-platform: web_claude_ai" \
  -H "referer: https://claude.hk.cn/" \
  -b "$COOKIE" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['uuid'])")
echo "$NEW_ORG" > ORG_PIN.txt

# 启动代理 (setsid 确保不被 shell 退出杀掉)
setsid bash run_proxy.sh </dev/null &

# 等 pre-warm 完成 (5-30s, 看 429 重试次数)
tail -f proxy.log  # 看到 "UP :19876" 就可以了
```

### 2. 创建非 root worker 用户
```bash
useradd -m -s /bin/bash ccworker
mkdir -p /home/ccworker/.claude
cat > /home/ccworker/.claude.json << 'EOF'
{"hasCompletedOnboarding":true}
EOF
cat > /home/ccworker/.claude/settings.json << 'EOF'
{"permissions":{"allow":["Bash(*)","Read(*)","Edit(*)","Write(*)","MultiEdit(*)"],"deny":[]}}
EOF
chown -R ccworker:ccworker /home/ccworker
```

### 3. 派发小弟
```bash
runuser -u ccworker -- env \
  ANTHROPIC_BASE_URL=http://127.0.0.1:19876 \
  ANTHROPIC_API_KEY=sk-ant-proxy \
  DISABLE_AUTOUPDATER=1 \
  CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC=1 \
  HOME=/home/ccworker \
  PATH=/usr/local/bin:/usr/bin:/bin \
  timeout 300 claude -p "你的任务prompt" \
  --max-turns 5 --dangerously-skip-permissions < /dev/null 2>&1
```

## 429 限流处理

- 429 是**正常**的，代理自动重试最多 8 次（5s, 10s, 15s...间隔）
- 不要同时开多个小弟，每个小弟间隔 30-60s 启动
- 如果持续 429，等 5 分钟再试

## 代理架构

```
Claude Code CLI (Bun runtime)
  ↓ HEAD / (Connection: keep-alive)
  ↓ POST /v1/messages?beta=true (Authorization: Bearer sk-ant-proxy)
Proxy V3 (port 19876, threaded)
  ↓ Pre-warmed conv (startup 时已创建)
  ↓ POST claude.hk.cn/api/organizations/{org}/chat_conversations/{conv}/completion
  ↓ SSE 流 → 解析 text + tool_use blocks
  ↓ 组装 Anthropic API Messages 格式返回
Claude Code CLI
  ↓ 如果 stop_reason=tool_use → 本地执行 Bash/Edit/Write
  ↓ 发回 tool_result → 代理 → claude.hk.cn → 下一轮
```

## 已知限制

- 每次请求通过 claude.hk.cn 需要 30-90s（包括 429 重试）
- 代理是单 conversation 模式 — 多个小弟串行共享同一个 conv
- tool 名称映射: claude.hk.cn 的 `bash_tool` → Claude Code 的 `Bash`
- 不支持 streaming（Claude Code 等完整响应）

## 文件说明

- `proxy_v3.py` — 修复版代理（pre-warm + threaded + fast HEAD + short retry）
- `proxy_v2.py` — 旧版代理（保留参考，有 bug）
- `run_proxy.sh` — 自动重启包装器
- `raw_curl.txt` — cookie 来源（需定期从浏览器更新）
- `ORG_PIN.txt` — 当前有效的 org UUID
- `CLAUDE_CODE_V3_GUIDE.md` — 本文档

## 重要: claude.hk.cn 的 tool_use 限制

claude.hk.cn 的 web 版 Claude **不会自动生成 Anthropic API 格式的 tool_use block**。
它会说"我没有文件系统访问权限"或"我不能执行命令"。

### 解决方案

**方案A (推荐): 不传 tools，让模型返回文本**
- 在 proxy_v3.py 里 `cc_tools = []` (不传 tools)
- Claude Code 收到纯文本响应，不会进入 agentic loop
- 适合: 代码分析、方案设计、文档生成

**方案B: 手动 agentic loop**
- 管理者用 `claude_hk_chat.sh` 给小弟发分析任务
- 小弟返回代码/diff
- 管理者在自己的环境里 apply diff + git push
- 适合: 需要多轮代码修改的任务

**方案C: 在 ags1 集群上直接跑 Claude Code**
- 如果 ags1 有网络访问和 npm，直接在上面跑
- 用 ANTHROPIC_API_KEY (真正的 sk-ant-xxx) 或 ANTHROPIC_BASE_URL 连代理
- 适合: 完整的 agentic coding

### 当前推荐工作流

1. 管理者 (claude.ai 的 Opus) 做架构设计、审计、配置修改、git push
2. 小弟 (claude.hk.cn 的 Sonnet) 做代码分析、方案设计、diff 生成
3. 管理者 apply 小弟的 diff，验证后 push
