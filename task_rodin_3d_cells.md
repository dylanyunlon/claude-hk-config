# Rodin 3D 细胞方案 — 断链诊断 + 行动路径

## 现状诊断
- GLTFLoader: 874行完整GLB解析器, 从未被实例化
- at-jellyfish-cell: fetch AT私有.bin → 404 + identity view/proj → 不显示  
- 17万行3D代码全部因加载失败/坐标错误/shader编译失败而死

## 方案
Rodin生成标准GLB → 已有GLTFLoader加载 → 正交投影 → 渲染到cell位置

## 需要Rodin生成的5个GLB
1. self_attn.glb — 水母/触手形(自注意力=感知)
2. ffn.glb — 能量球/闪电形(FFN=快速处理)
3. embedding.glb — 晶体/棱镜形(嵌入=映射)
4. add_norm.glb — 十字/节点形(残差=合并)
5. forward.glb — 箭头/管道形(前向传递=流动)

## 代码任务: CellMeshRenderer (替代at-jellyfish-cell)
- 用GLTFLoader加载GLB(不需要Draco)
- 正交投影矩阵匹配cell pixel space(0-2040 × 0-3965)
- per-cell model matrix: translate + scale
- 渲染到单独FBO, composite时alpha-over混合

## 小弟任务
等Rodin GLB就绪后, 写CellMeshRenderer接入gpu-render-loop
