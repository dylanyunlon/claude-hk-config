# Claude HK Dispatch Guide — SINGLE SOURCE OF TRUTH

Supersedes `CLAUDE_CODE_GUIDE.md`, `CLAUDE_CODE_SETUP.md`, `CLAUDE_CODE_V3_GUIDE.md`
and all `proxy_v2.py` / `proxy_v3.py` variants. **Do not create v2/v3/vN files.**

## The sub-Claude has a FULL bash code-execution container

When you send a completion request with the tools from `raw_curl.txt`,
the server gives the sub-Claude a **real Linux container with `bash_tool`** — not a
sandboxed calculator, not a widget renderer.

- The sub-Claude can `git clone`, run multi-step shell pipelines, install packages,
  edit files, and make **multiple tool calls per turn**.
- It runs its own **agentic loop** inside its container.

**The manager must NEVER be the sub-Claude's terminal.** The sub-Claude runs code
itself. The manager defines the task and reviews the artifact.

## Request format — mirror raw_curl.txt exactly

The completion request body must match `raw_curl.txt` exactly: full tools list
(including `repl_v0`, `web_search`, `artifacts`, visualizer tools), all headers
(`sec-ch-ua`, `sec-fetch-*`, etc.), `locale`, `sync_sources`,
`create_conversation_params`. Do NOT simplify the request into a minimal subset —
the server uses these fields to determine what capabilities the sub-Claude gets.

Model selection:
- `claude-opus-4-6` for complex architectural tasks (subsystem design, kernel writing)
- `claude-sonnet-4-6` for implementation tasks (module migration, bug fixes)

## Traceability: CCCL-grade issue → commit → PR linkage

**This is the #1 process rule.** Every line of code must trace back to a design
decision. Reference: NVIDIA/cccl#9656 — 40 lines with full issue/PR/API-surface
traceability beats 2357 lines of unlinked kernel code.

### Before dispatching any task:

1. **Create a GitHub issue** in `dylanyunlon/Neuron_SP` describing the problem and
   the design approach. Include:
   - API surface inventory (what interfaces are touched)
   - Gap analysis (what's missing vs what exists)
   - Before/after code sketch (even pseudocode)
   - Links to reference implementations (Megatron commit hashes, CCCL PRs, etc.)

2. **Add the issue to Project #2** (`Neuron_SP – Current Sprint`) with all fields:
   Status, Priority, Module, Claude, Sprint, Language.

3. **Include the issue number in the dispatch prompt** so the sub-Claude references
   it in every commit.

### Every sub-Claude commit MUST follow this format:

```
<type>(<scope>): <description> — addresses #<issue_number>

<body explaining the design decision, not just what changed>

Refs: <Megatron commit hash>, <CCCL issue>, <upstream PR> if applicable
```

Types: `feat`, `fix`, `perf`, `refactor`, `test`, `bench`, `docs`
Scopes: `parallel_state`, `distributed`, `optimizer`, `transformer`,
        `pipeline_parallel`, `tensor_parallel`, `hetero_reduce`, `autosp`,
        `desloc_engine`, `csrc`

Example:
```
feat(hetero_reduce): warp-cooperative reduction kernel — addresses #21

Replace per-thread atomicAdd with warp-level __shfl_down + single-lane
atomic. Reduces global memory traffic by 32x for the gradient reduce-
scatter hot path on PCIe topology (A6000 ↔ H100 cross-NUMA).

Design: CCCL cub::WarpReduce pattern adapted for heterogeneous SM
(SM8.6 uses 32-wide warps, SM9.0 identical, SM12.0 TBD).

Refs: Megatron-LM 5486c69c6 (timing debug), CCCL cub/warp/specializations
Benchmark: bench_hetero_reduce.py — 2.3x faster than baseline NCCL
allreduce for <1MB payloads on PCIe Gen4 x16.
```

### Sub-Claude must NOT:
- Push commits with messages like "mirrors X", "port of Y", "stub for Z"
- Create files without linking them to an issue
- Write code without a benchmark or smoke test that proves it works
- **CREATE BRANCHES** — push to main directly, always
- Create v2/v3/port/alt suffixed files

### Workflow (direct push to main):

```
Sub-Claude
──────────
1. git clone + set token
2. Write code, test, commit (--signoff)
3. git pull --rebase origin main
4. git push origin main
```

**NEVER create branches.** All 18 feature branches created by previous workers
were deleted because they caused merge conflicts and fragmented development.
The iron rule: one branch (main), all commits go there.

## The dispatch prompt template

Every task prompt sent to a sub-Claude MUST include these sections:

```
## Identity
You are Claude-{letter}, working on Neuron_SP issue #{N}: {title}

## Setup
git clone https://github.com/dylanyunlon/Neuron_SP.git && cd Neuron_SP

## Issue context
{Copy the issue body here, or link to it}

## Your deliverables
1. {Specific files to create/modify}
2. {Import contract: "from X import Y must work"}
3. {Benchmark/test: "python bench_Z.py must show >2x improvement"}

## Workflow rules
- Branch: git checkout -b {type}/issue-{N}-{short-desc}
- Every commit: git commit -m "{type}({scope}): {desc} — addresses #{N}"
- Push branch: git push origin {branch-name}
  Token: <GH_TOKEN from ORG_PIN or env>
- Create PR via:
  curl -X POST https://api.github.com/repos/dylanyunlon/Neuron_SP/pulls \
    -H "Authorization: token <GH_TOKEN from ORG_PIN or env>" \
    -d '{"title":"...","head":"{branch}","base":"main","body":"..."}'
- Do NOT push to main directly
- Do NOT create v2/v3 suffixed files
- Do NOT write stub/placeholder code — every function must have a real body

## Design references
{Links to Megatron commits, CCCL issues, upstream PRs that inform the design}

## Success criteria
{Exact commands that must pass before you consider the task done}
```

## Org ID — read `ORG_PIN.txt`, never hardcode

The cookie can access exactly one org. `ORG_PIN.txt` is the single source of truth.

## One conversation per task

Each dispatched issue = its own new conversation. Do not reuse conversations
across unrelated issues.

## Rate limits

The API has weekly rate limits. 429 errors are normal — wait and retry.
Do not panic or rewrite the dispatch script. The manager reports the wait
to the user and queues tasks for when quota refreshes.
