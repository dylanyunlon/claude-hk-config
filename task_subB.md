git clone https://${GH_TOKEN}@github.com/dylanyunlon/Neuron_SP.git && cd Neuron_SP

You are Sub-Claude B. Work in YOUR bash container. Run a long agentic loop — clone, read, implement, test, iterate — until it works. Do not hand bash commands back to me; run them yourself.

TASK: Implement two files (bodies only — signatures are FROZEN, do not change them):
  deepspeed/core/hetero_bridge/dist_opt_adapter.py
  deepspeed/core/hetero_bridge/tier_map.py  (only if Sub-Claude A hasn't; check git log first)

READ FIRST (full evolution, not one commit):
  - deepspeed/core/hetero_bridge/ARCHITECTURE.md   (the contract you must satisfy)
  - deepspeed/core/optimizer/distrib_optimizer.py  (the Megatron optimizer you're wrapping)
  - deepspeed/runtime/zero3_hetero_shard.py         (existing hetero shard logic to reuse)
  - git log --oneline -- deepspeed/core/optimizer/  (understand how it got here)
  - HEAD commit a52efee1 (VRAM-adaptive optimizer: A6000->DeepSpeedCPUAdam, H100/Blackwell->fused AdamW)

REQUIREMENTS:
  - DistOptAdapter.build() must construct the real core.optimizer.DistributedOptimizer,
    choosing CPUAdam on A6000 ranks and fused AdamW on H100/Blackwell ranks (per-rank).
  - reduce_scatter_grads / all_gather_params must be PCIe-aware (P2P disabled, no NVLink).
  - REUSE existing code in zero3_hetero_shard.py and core.optimizer — do NOT reinvent.
  - No new files. No v2/v3/vN suffixes. No new branches. Edit the frozen skeleton in place.

DONE means: `grep -c NotImplementedError dist_opt_adapter.py` is 0, and you have written a
tiny local test proving the adapter builds an optimizer object without error (mock the model
with a 2-layer nn.Module if no GPU). Paste your final diff and the test output.

When finished, output the full content of dist_opt_adapter.py so I can review and push.
