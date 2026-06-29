# 方向修正: 停止修AT/UE死代码, 用已有数据驱动视觉效果

## 现状
- 170K行GPU代码, 只有PBR+Bloom+Edge+Composite在渲染
- AT/UE移植的11个pass全部shader编译失败, 是死代码
- PBR只画纯色圆角矩形, cell看起来像Windows98窗口
- composite_params.json有丰富视觉参数(glow/sdf/pattern/halo)全被忽略

## 新方向: 增强PBR pass, 让它消费所有cell视觉参数

---

## 小弟 #1: 扩展CellData + PBR shader (核心视觉)

git clone https://github.com/dylanyunlon/astro-svgfigure.git && cd astro-svgfigure && git checkout cell-pubsub-loop && git config user.email "claude@anthropic.com" && git config user.name "Claude"

任务: 扩展CellData接口和PBR fragment shader, 让每个cell看起来像赛博细胞

1. 扩展CellData接口(gpu-render-loop.ts):
   新增: glowColor, sdfShape, internalPattern, haloRadius, numRays, focalIntensity, animSpeed, fillColor, strokeColor, opacity

2. 修改world/index.astro的cell构造, 把两种数据源都传入:
   - 7个有primary_color的cell: 传入glow_color/sdf_shape/internal_pattern/halo_radius等
   - 51个有fill_color的cell: 用fill_color作albedo, stroke_color作边框色

3. PBR fragment shader增强(pbr-gpu-pass.ts):
   - SDF形状: rounded_rect用现有的, capsule用胶囊SDF
   - 内部纹理: 根据internal_pattern画不同的纹理(网格/条纹/渐变等)
   - 发光边缘: 用glow_color在cell边缘画发光轮廓, 强度由halo_radius控制
   - 边框: stroke_color画1-2px边框
   
别开新分支, push到cell-pubsub-loop。commit格式M12XX。push前git pull --rebase。
key: [见仓库设置的key]

## 小弟 #2: Edge流动动画 + 粒子

git clone https://github.com/dylanyunlon/astro-svgfigure.git && cd astro-svgfigure && git checkout cell-pubsub-loop && git config user.email "claude@anthropic.com" && git config user.name "Claude"

任务: 让edge线条有流动动画, 加入简单粒子效果

1. edge-gpu-pass.ts: 当前画的是静态线条且闪烁
   - 加入流动动画: dash offset随时间移动, 模拟数据流
   - 用edge颜色, 不要全部一个色
   - 修复闪烁(可能是z-fighting或alpha问题)

2. particle-gpu-pass.ts: 当前没有粒子数据
   - 在edge路径上生成流动粒子(沿控制点移动的小光点)
   - 每条edge 3-5个粒子, 颜色跟edge一致
   - 这比修AT的antimatter-particles.ts(1364行死代码)有效得多

别开新分支, push到cell-pubsub-loop。commit格式M12XX。push前git pull --rebase。
key: [见仓库设置的key]

## 小弟 #3: 背景 + 后处理 (不用AT死代码)

git clone https://github.com/dylanyunlon/astro-svgfigure.git && cd astro-svgfigure && git checkout cell-pubsub-loop && git config user.email "claude@anthropic.com" && git config user.name "Claude"

任务: 用简单shader实现赛博背景, 不要用AT的atmosphereSky(死代码)

1. 直接在composite-gpu-pass.ts的shader里加背景:
   - 深色径向渐变(中心#0a1628, 边缘#020810)
   - 微妙的网格线(每隔50px一条细线, 亮度0.03)
   - 慢速噪声扰动(让背景有微动感)
   替代atmosphereSky(1270行死代码)

2. composite shader加DOF效果:
   - 简单的基于UV距离的模糊(不需要深度buffer)
   - 边缘略微模糊, 中心清晰

3. bloom调优: 当前threshold=0.35/strength=1.2
   - 只让glow_color的cell产生bloom
   - bloom颜色跟cell的glow_color一致

别开新分支, push到cell-pubsub-loop。commit格式M12XX。push前git pull --rebase。
key: [见仓库设置的key]
