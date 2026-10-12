# 舰首与中段任务包 · form-study-03

本轮是可编辑形体稿，未作为最终精细模型或网页发布包。

## 文件入口

- `scenes/flagship-form-study-03.blend`：当前场景，用 Blender 4.5.14 LTS 打开。
- `inputs/integration-01/flagship-orbit-study.blend`：保持原校验值的上一轮输入，可重新生成本轮。
- `scenes/textures/blue_metal_plate_rough_1k.png`：场景已内嵌的 CC0 粗糙度副本；`textures/source/` 保留 4K 原文件。
- `previews/`：对比板；`current/`、`baseline/`、`cutaway/` 为未修图的 960×600 原始帧。
- `evidence/`：环境、检查、CPU 计时和迁移结果。
- `tools/flagship/`：脚本；`DELIVERY.json`、`SHA256SUMS`、`ATTRIBUTION.md`：交付与素材记录。

研究记录位于 `docs/kuhai/references/2026-10-12-form-study-03.md`，没有把参考照片打包为可发布贴图。

## 环境与场景

实测 Blender 4.5.14 LTS（构建 `62c1db4208e8`）、Python 3.11.17、`bpy==4.5.14`、numpy 1.26.4，依赖见 `requirements-cloud.txt`。桌面 Blender 自带渲染脚本所需模块，无需安装 bpy。可选对比图工具使用 `Pillow==12.3.0`。

`SHIP_HULL` 是主结构，`ARCHIVE_SHELL` 是可移除舱区外壳及附件，`ARCHIVE_INTERIOR` 是原档案室。左右后部细节在 `PORT_DETAILS` / `STARBOARD_DETAILS`；`BASELINE_SHIP` 是默认隐藏的整合 01 对照。`SPACE`、`LIGHTING`、`ROOM_LIGHTS` 沿用原环境与照明。对照/剖视只切换可见性。

Z 向上、舰首 -X、左舷 -Y，单位米。约 500 m 舰长及室内尺度是创作假设。虚构星体、大气表面近似与艺术补光不是物理散射模拟；百万米环境坐标不直接用于网页。

## 启动与小样

从任务包根目录执行，默认 CPU。已有输出默认拒绝覆盖，手工精修请另存。

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/inspect_form.py -- --scene scenes/flagship-form-study-03.blend --output evidence/validation-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/form_study.py -- render --scene scenes/flagship-form-study-03.blend --output previews/local-cpu --views overview --width 640 --height 400 --samples 16
```

Linux/macOS 使用 `blender -b --python-exit-code 1 --python ... -- ...`。固定 bpy 环境可直接运行 `python tools/flagship/form_study.py ...`。

```bash
blender -b --python-exit-code 1 --python tools/flagship/form_study.py -- build --scene inputs/integration-01/flagship-orbit-study.blend --output regenerated
blender -b --python-exit-code 1 --python tools/flagship/form_study.py -- render --scene regenerated/flagship-form-study-03.blend --output previews/new --views overview,port,form_close,form_top,form_archive
blender -b --python-exit-code 1 --python tools/flagship/form_study.py -- render --scene regenerated/flagship-form-study-03.blend --output previews/old --views overview,form_close,form_top --baseline
blender -b --python-exit-code 1 --python tools/flagship/form_study.py -- render --scene regenerated/flagship-form-study-03.blend --output previews/open --views form_archive --cutaway
python tools/flagship/form_review.py --baseline previews/old --current previews/new --cutaway previews/open --output previews/review
```

生成器校验输入 SHA256，不把未知的手工精修版当作旧场景。图片已打包且使用相对路径，可单独迁移 `.blend`。隐藏对象在 Blender 中可能有未求值的世界矩阵缓存；检查器先显示并更新依赖图，再比较实际几何。

## 验证与本地移交

主舰 228648 个求值网格三角形，含室内、不含环境/字体/隐藏对照。新增网格避开室内占用预留区，尚未进行全舰工程验算。已渲染五张当前帧、三张对照、一张剖视，以及只携带 `.blend` 的跨目录 640×400 小样。

本轮约 6–18 秒/帧，云端无必须换 GPU 的瓶颈。用户明确连接家中电脑、核实机器/授权/软件/驱动/可用显存后，才考虑 `--device optix`；先用 640×400 / 16 次采样测试，再定高清规格与批次。Windows 和 3060 Ti 尚未实测。

本包没有新整舰 GLB。网页模型仍需独立拓扑整理、UV、烘焙、LOD、压缩和设备测试；制作显卡不决定访客显卡要求，预览分辨率不降低最终质量目标。
