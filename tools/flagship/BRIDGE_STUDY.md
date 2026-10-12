# 舰桥外部结构制作与启动 · bridge-study-01

基于不可变的 surface-study-03，新增观察窗凹槽、装甲挑檐与后掠支撑。本包是 kuhai 主舰的可编辑外部研究；最终美术目标不变，但本轮不是最终模型、官方蓝图或新的线上版本。

## 包内入口

- `scenes/flagship-bridge-study-01.blend`：本轮可编辑场景。
- `inputs/surface-study-03.blend`：完整前一版输入，SHA-256 为 `b14004497af8b87412687fdef43f497c8b8be09acf7f7e23a1b5288f69a866cb`。
- `previews/bridge-study-01.webp`：近景、低角度和整舰概览。
- `previews/bridge-study-01-comparison.webp`：旧桥楼与新结构的同机位对照。
- `previews/current/`、`previews/previous/`：未经修饰的比较 PNG 和渲染记录。
- `previews/cutaway/`：档案室剖视核查。
- `evidence/`：几何、资源、迁移和当前云端环境记录。
- `tools/flagship/`：生成、渲染、检查、预览排版脚本和 JSON 配置。

Blender 的 `BRIDGE01_EXTERIOR` 是当前结构，`BRIDGE01_PREVIOUS` 是隐藏的旧桥楼。比较时只启用其中一个。`ARCHIVE_SHELL` 仍独立控制档案室外壳，切换不会移动舰体或相机。Blender Z 向上，舰首为 -X，左舷为 -Y；尺寸仍为暂定制作尺度。

观察窗为不透明的外观代理；其前方装甲、窗框和凹槽为真实几何，未制作透射玻璃背后的完整舰桥。当前场景新增两个透视机位 `bridge_close`、`bridge_low`，保留原有机位。没有修改网站交互。

## 依赖与素材

已验证 Blender **4.5.14 LTS**（build `62c1db4208e8`）、Python 3.11.17。桌面 Blender 自带 Python，直接打开 `.blend` 不用安装 pip 依赖。云端路线使用 `requirements-cloud.txt`；比较板可选 `requirements-review.txt`（Pillow 12.3.0），与建模运行时分开亦可。

沿用 Rob Tuytel / Poly Haven 的 [Blue Metal Plate](https://polyhaven.com/a/blue_metal_plate) 粗糙度，许可 [CC0](https://polyhaven.com/license)。原始 4K JPG 放在 `textures/source/`，实际使用的 1K PNG 放在 `.blend` 旁 `textures/`，使用相对路径并已打包。其余材质和星体为程序化。`textures/ATTRIBUTION.md` 保留原链接、处理与校验值。

没有附带官方/二创模型、参考图片、付费素材、Blender 安装包或家用电脑凭据。

## 从包根目录执行

以下均为 CPU 默认小样，不会自动选择显卡。已有输出拒绝覆盖；手工修改请另存，只有可再生成输出才使用 `--overwrite`。

Linux / macOS（已安装 Blender 4.5.14）：

```bash
blender --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-new-machine.json
blender --background --python-exit-code 1 --python tools/flagship/bridge_study.py -- inspect --baseline inputs/surface-study-03.blend --scene scenes/flagship-bridge-study-01.blend --output evidence/inspection-new-machine.json
blender --background --python-exit-code 1 --python tools/flagship/bridge_study.py -- render --scene scenes/flagship-bridge-study-01.blend --output previews/cpu-sample --views bridge_low --width 640 --height 400 --samples 16
```

Windows PowerShell（路径只是启动示例，先核实实际安装位置）：

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-new-machine.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/bridge_study.py -- inspect --baseline inputs/surface-study-03.blend --scene scenes/flagship-bridge-study-01.blend --output evidence/inspection-new-machine.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/bridge_study.py -- render --scene scenes/flagship-bridge-study-01.blend --output previews/cpu-sample --views bridge_low --width 640 --height 400 --samples 16
```

云端已配置 pinned `bpy` 的 Python 可直接执行。以下用于另建输出，不能覆盖手工精修文件：

```bash
python tools/flagship/bridge_study.py build --scene inputs/surface-study-03.blend --output regenerated
python tools/flagship/bridge_study.py inspect --baseline inputs/surface-study-03.blend --scene regenerated/flagship-bridge-study-01.blend --output evidence/regenerated-inspection.json
python tools/flagship/bridge_study.py render --scene scenes/flagship-bridge-study-01.blend --output previews/recheck-current --views form_close,bridge_low
python tools/flagship/bridge_study.py render --scene scenes/flagship-bridge-study-01.blend --output previews/recheck-previous --views form_close,bridge_low --previous
python tools/flagship/bridge_study.py render --scene scenes/flagship-bridge-study-01.blend --output previews/recheck-cutaway --views surface_archive --cutaway
```

同规格比较图排版使用 `python tools/flagship/bridge_review.py --input previews --output review-again`，默认读取 `previews/current`、`previews/previous`。排版仅缩放和加说明，不修改渲染光影。渲染命令产出 PNG 和逐帧 `benchmark.json`；检查命令产出 JSON，失败退出非零；构建产出 `.blend`、纹理和 `bridge-manifest.json`。

## 本地交接与网页边界

当前没有获得家中电脑的访问权限，也不需要启动本地任务。用户明确连接后，才核对目标机器、授权、Blender、驱动、GPU 及空闲显存。之后可把单张小样渲染命令添加 `--device optix`，确认耗时与真实显存占用后再决定更大尺寸和采样；不预设 3060 Ti 能承担任意规模。

本轮仅离线制作，没有新的网页模型或浏览器性能结论。未来导出器需要加入 `BRIDGE01_EXTERIOR`、排除 `BRIDGE01_PREVIOUS`，再独立处理 UV、材质简化、细节层次及压缩。不要把源文件全部细节直接上传为网页资产。
