# Claude Loop 任务分配 — M1258+ Visual Upgrade (2026-06-29)

## 战略方向

**停止修 AT/UE 死代码 shader error。直接增强已工作的 PBR pass。**

根因分析：
- 11 个 AT/UE 移植 pass 因依赖 AT 引擎（compiled.vs、getShader、特殊 UV 空间）无法正常编译
- PBR pass 只渲染"纯色圆角矩形"，没消费 composite_params.json 里的丰富视觉参数
- CellData 接口只传 6 字段，丢弃了 glow_color/sdf_shape/internal_pattern/halo_radius/num_rays/focal_intensity

## 小弟 #1: CellData 接口扩展 → M1258

扩展 CellData + CellPBRDescriptor 接口，让数据管线传递全部视觉参数。
改文件：gpu-render-loop.ts, pbr-gpu-pass.ts, world/index.astro

## 小弟 #2: PBR Shader 升级 → M1259

重写 PBR fragment shader：
- SDF 形状（rounded_rect / capsule）替代固定 cornerR
- Glow/Halo 边缘发光
- Rays 径向光线（self_attn 等）
- Internal pattern 内部纹理（grid/bars/sine/bottleneck/plus）
- 时间动画

## 小弟 #3: HUD + Composite + 标记 → M1260

- HUD 连接 GPURenderLoop.stats
- Composite pass 加 DOF + Fog
- 标记 AT/UE dormant passes（不删除）

## 执行顺序

#1 → #2 → #3（串行依赖，每个都要先 pull）

## 运行 dispatch

```bash
cd astro-svgfigure
python3 tasks/dispatch_m1258_visual_upgrade.py
```
