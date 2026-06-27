# Claude 小弟任务分配 — M1248+ (2026-06-27)

## 当前状态
- 分支: cell-pubsub-loop
- 最新: M1252 (expose program getter) + M1248 (UIL pipeline fix)
- UIL参数管道已打通, AT生产参数已注入
- 仍有6个GPU pass shader编译失败

## 小弟 #1: Shader编译修复
```
git clone https://github.com/dylanyunlon/astro-svgfigure.git && cd astro-svgfigure && git checkout cell-pubsub-loop
```
修复: at-antimatter-particles.ts (gl_FragColor), ue-lumen-gi.ts (fragColor inject位置), ue-atmosphere-sky.ts (fragColor), at-geometry-loader.ts (cameraPosition+uniform重定义+dFdx vec3), at-flower-particle.ts (uniform overflow)

## 小弟 #2: DOF+CloudFog+Composite
```
git clone https://github.com/dylanyunlon/astro-svgfigure.git && cd astro-svgfigure && git checkout cell-pubsub-loop
```
composite-gpu-pass添加DOF(uDOF=[0.72,0.8,0.3,1])+Fog(uFog=[0,1.24,1,0.89],uFogColor=#1a90ad), CloudFog.ts接入gpu-render-loop

## 小弟 #3: MouseFluid+HydraThread
```
git clone https://github.com/dylanyunlon/astro-svgfigure.git && cd astro-svgfigure && git checkout cell-pubsub-loop
```
at-mousefluid完善(dyeTexture→composite, splat AT参数), at-hydra-bloom(HydraBloom_Intensity=1), thread Worker验证

## RULES
- 别开新分支/后缀, 直接push到cell-pubsub-loop
- commit: M12XX: 描述
- push前: git pull --rebase origin cell-pubsub-loop
