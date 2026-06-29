# Claude Loop 任务分配 — M1254+ (2026-06-29)

## 小弟 #1: Shader编译修复 (ue-atmosphere-sky + at-geometry-loader + at-flower-particle)

git clone https://github.com/dylanyunlon/astro-svgfigure.git && cd astro-svgfigure && git checkout cell-pubsub-loop && git config user.email "claude@anthropic.com" && git config user.name "Claude"

修复3个仍在报错的GPU shader pass:
1. ue-atmosphere-sky.ts: fragColor undeclared — 检查compileShader中out vec4 fragColor注入位置
2. at-geometry-loader.ts: buildGeometryFragGLSL拼接AT shader时uniform重定义(tMRO/tMatcap等) + dFdx(vec3)在某些driver不支持→改为逐分量
3. at-flower-particle.ts: uniform count超MAX_FRAGMENT_UNIFORM_VECTORS(1024) — M1242用了texture lookup但可能仍有残余

push前: git pull --rebase origin cell-pubsub-loop
commit格式: M12XX: 描述
别开新分支/后缀

## 小弟 #2: DOF+Fog接入composite-gpu-pass

git clone https://github.com/dylanyunlon/astro-svgfigure.git && cd astro-svgfigure && git checkout cell-pubsub-loop && git config user.email "claude@anthropic.com" && git config user.name "Claude"

composite-gpu-pass.ts目前只有vignette+grain，需要添加:
- DOF shader: uDOF(vec4)=[0.72,0.8,0.3,1], 基于UV距离中心的模糊
- Fog shader: uFog(vec4)=[0,1.24,1,0.89], uFogColor(vec3)=#1a90ad, 深度雾
- gpu-render-loop.ts已有dofParams/fogParams/fogColor成员变量(M1248加的)，在composite.render()时传入
- CloudFog.ts/CloudFogBackground.ts接入render loop

push前: git pull --rebase origin cell-pubsub-loop
commit格式: M12XX: 描述
别开新分支/后缀

## 小弟 #3: AT粒子颜色+AudioContext fix

git clone https://github.com/dylanyunlon/astro-svgfigure.git && cd astro-svgfigure && git checkout cell-pubsub-loop && git config user.email "claude@anthropic.com" && git config user.name "Claude"

1. AT粒子颜色参数未接入: CoreParticlesShader uColor=#C64DFF, uColorB=#422EA3, uColorC=#84C8C3
   在at-antimatter-particles.ts的speciesColour函数中使用AT调色板
2. AudioContext autoplay fix: audio-system.ts需要在user gesture后resume
3. 检查at-mousefluid-import.ts的splat参数是否用了AT值

push前: git pull --rebase origin cell-pubsub-loop
commit格式: M12XX: 描述
别开新分支/后缀
