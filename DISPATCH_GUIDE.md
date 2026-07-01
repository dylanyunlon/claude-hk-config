# Claude HK Dispatch Guide — SINGLE SOURCE OF TRUTH

Supersedes `CLAUDE_CODE_GUIDE.md`, `CLAUDE_CODE_SETUP.md`, `CLAUDE_CODE_V3_GUIDE.md`
and all `proxy_v2.py` / `proxy_v3.py` variants. **Do not create v2/v3/vN files.**

## The sub-Claude has a FULL bash code-execution container

This is the single most important fact and the reason past dispatches failed.

When you send a completion request with `"tools":[{"type":"repl_v0","name":"repl"}]`,
the server gives the sub-Claude a **real Linux container with `bash_tool`** — not a
sandboxed calculator, not a widget renderer. Verified 2026-07-01:

- The sub-Claude fires `bash_tool` (confirmed in the SSE stream), not `repl`.
- It can `git clone`, run multi-step shell pipelines, install packages, edit files,
  and make **multiple tool calls per turn** (verified: 3 tool calls, cloned all 4209
  files of Neuron_SP, listed real directory trees, read git log).
- It runs its own **agentic loop** inside its container.

**Therefore: the manager must NEVER ask the sub-Claude to hand a `bash_tool` request
back up to the manager.** The sub-Claude runs code itself. The manager's job is to
define the task and review the artifact — not to be the sub-Claude's terminal.

## The V1 dispatch pattern (this is correct — use it)

```
Manager (this Claude)          Sub-Claude (Sonnet 4.6 on claude.hk.cn)
─────────────────────          ────────────────────────────────────────
1. Define task prompt    ──▶
                                2. git clone the repo in its container
                                3. Explore, read module history, iterate
                                4. AGENTIC LOOP (many turns) until subsystem works
                                5. Output: real code / analysis / artifacts
6. Review the output     ◀──
7. git push (manager only)
```

The manager defines *what* and *why*. The sub-Claude does *how*, in its own container.
The manager reviews and is the ONLY one who pushes to `main`.

## How to write a task prompt that produces WORKING code, not dead code

Past failure: "generate one `hetero_xxx.py` per Megatron commit, write 'mirrors X', push."
This produced 150,264 lines of dead code (122 files never imported) because the success
criterion was *file existence*, not *being called by training*.

Every task prompt MUST:

1. **Give a clone command, not a wall of text.** First line: the `git clone`. Let the
   sub-Claude read the code itself. Do not paste large excerpts.
2. **Define the import contract.** State exactly which existing training entrypoint
   (`run_pretrain.py`, `desloc_engine.py`, an AutoSP or DES-LOC hook) must `import` and
   `call` the new subsystem. "It must be imported and invoked by X" is the success test.
3. **Assign a whole subsystem, not one commit.** "Read module M from its first commit to
   HEAD, understand its evolution, produce a complete importable subsystem (multiple files
   with real software architecture, not one wired file)."
4. **Demand a long agentic loop.** "Iterate in your container until `python -c 'import ...'`
   succeeds and a smoke test passes. Do not stop at a single file."
5. **Forbid mechanical mirroring.** "Do NOT generate one-file-per-commit stubs. Do NOT
   write commit messages that just say 'mirrors X'. Reuse and adapt real logic."
6. **No new branches, no v2/v3 suffixes.** "Work on `main`. Do not create branches or
   files with v2/v3/vN or port suffixes." (Applies to the sub-Claude too.)

## Org ID — read `ORG_PIN.txt`, never hardcode

This cookie can access **exactly one** org. `ORG_PIN.txt` is the single source of truth.
Hardcoding a different org id (the old `bc451b9e...` was stale) is what caused
"cannot create conversation" and colliding-task confusion. All dispatchers read the file.

## Verified-correct request format

Extract from `raw_curl.txt`: `cookie` (via `-b '...'`) and `user-agent`.
Org id: from `ORG_PIN.txt`. Model: `claude-sonnet-4-6` for sub-Claudes.

Create conversation:
```
POST /api/organizations/{ORG}/chat_conversations
  --data-raw {"name":"...","model":"claude-sonnet-4-6","is_temporary":false}
  → returns {"uuid": CONV_ID}
```

Completion (streams SSE):
```
POST /api/organizations/{ORG}/chat_conversations/{CONV_ID}/completion
Headers: accept: text/event-stream, content-type: application/json,
         origin: https://claude.hk.cn, referer: https://claude.hk.cn/,
         anthropic-client-platform: web_claude_ai, user-agent: <from raw_curl>, -b <cookie>
Body:
  {
    "prompt": "<task>",
    "timezone": "Asia/Shanghai",
    "model": "claude-sonnet-4-6",
    "effort": "medium",
    "thinking_mode": "off",
    "tools": [{"type":"repl_v0","name":"repl"}],   ← gives the sub-Claude bash
    "turn_message_uuids": {"human_message_uuid": <uuid4>, "assistant_message_uuid": <uuid4>},
    "attachments": [], "files": [], "rendering_mode": "messages"
  }
```

Parse SSE lines starting `data:`:
- `content_block_start` with `content_block.type == "tool_use"` → sub-Claude is running code
- `content_block_delta` → `delta.text` is the streamed answer
- `message_stop` → done

Continue a truncated turn: reuse the same `CONV_ID`, send prompt `"Continue"`.

## One conversation per task

Each dispatched module = its own new conversation (own CONV_ID). Do not reuse one
conversation across unrelated modules — that is what tangled prior runs. Multiple
sub-Claudes run in parallel, each in its own conversation, each on `main`.
