# 整舰与星体光照任务包 · integration-study-01

本轮把结构草模 02 与局部材质样板 01 合成一套可编辑整舰预览。主舰造型、全部表面细节和最终光影仍待精修；本包没有新的整舰网页 GLB。

## 文件入口

- `scenes/flagship-orbit-study.blend`：当前整舰、两侧喷口、保留的档案室、星体、相机和照明。
- `previews/integration-study-01.webp`：正面斜视与舰尾。
- `previews/integration-study-01-comparison.webp`：同机位、同环境下的旧草模/当前整合稿。左侧也使用本轮星体和灯光，不是旧预览原图。
- `previews/current/`：四张 960×600 原始渲染；`previews/baseline/`：两张对照。
- `inputs/blockout-02/flagship-blockout.blend` 与 `inputs/material-01/shoulder-material-study.blend`：保持原校验值的前序输入，可重新生成当前场景。
- `textures/source/`：Rob Tuytel / Poly Haven 的 CC0 粗糙度 4K 原图。当前场景使用 `scenes/textures/` 的 1024 副本，同时已内嵌。
- `evidence/`：环境、单体网格、镜像、构图、舱室保留、迁移和 CPU 实测记录。

以上均以任务包根目录为基准。先阅读 `ATTRIBUTION.md`、`DELIVERY.json`；校验文件见 `SHA256SUMS`。

## 版本与场景组织

实测 Blender 4.5.14 LTS（`bpy==4.5.14`），云端 Python 3.11.17，numpy 1.26.4。桌面 Blender 自带脚本所需模块，无需另外安装 pip 包。只有可选对比图脚本使用 Pillow 12.3.0。依赖清单位于 `tools/flagship/requirements-*.txt`。

`SHIP_HULL` 和 `ARCHIVE_SHELL` 是整舰外部；`PORT_DETAILS` / `STARBOARD_DETAILS` 是可编辑左右肩部细节；`ARCHIVE_INTERIOR` 和 `ROOM_LIGHTS` 保留前序档案室。`SPACE` 是程序化环境，`LIGHTING` 是共享主光与明确标记的艺术补光。`BASELINE_SHIP` 默认隐藏，比较时与当前外部择一显示。

主舰坐标仍是 Z 向上、舰尾 +X、左舷 -Y。前序约 500 m 舰长是暂定创作值。星体半径 1050 km、位置与云层均为本轮构图假设，不代表真实天体或已验证的轨道。星体、相机不会在比较/剖视开关时移动。

## 启动和小样

从任务包根目录执行。默认使用 CPU，不会自动选择 GPU。

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/inspect_integration.py -- --scene scenes/flagship-orbit-study.blend --output evidence/validation-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/integration_study.py -- render --scene scenes/flagship-orbit-study.blend --output previews/local-cpu --views overview --width 640 --height 400 --samples 16
```

Linux/macOS 使用相同的 `blender -b --python-exit-code 1 --python ... -- ...` 形式。固定版本 `bpy` 环境也可直接运行 `python tools/flagship/integration_study.py render ...`。脚本使用相对导入，请保留完整 `tools/flagship` 目录。

重新生成：

```bash
blender -b --python-exit-code 1 --python tools/flagship/integration_study.py -- build --base-scene inputs/blockout-02/flagship-blockout.blend --material-scene inputs/material-01/shoulder-material-study.blend --output regenerated
blender -b --python-exit-code 1 --python tools/flagship/integration_study.py -- render --scene regenerated/flagship-orbit-study.blend --output previews/new --views overview,stern,port,detail
blender -b --python-exit-code 1 --python tools/flagship/integration_study.py -- render --scene regenerated/flagship-orbit-study.blend --output previews/old --views overview,stern --baseline
python tools/flagship/integration_review.py --baseline previews/old --current previews/new --output previews/review
```

输出存在时默认拒绝覆盖。对可再生成文件才使用 `--overwrite`；手工精修应另存文件。

## 制作与网页边界

本轮只验证离线制作场景：共享方向光、漆面/金属分工、喷口纵深与整舰距离下的表现。大气边缘采用按恒星方向衰减的表面效果，没有做真实散射积分。星体反照由同方向的区域补光近似，另有较弱的相机侧艺术补光；不是严格测光或空间环境仿真。

当前舰船网格含档案室约 21.86 万三角形，不含字体、环境和隐藏对照。后续网页另做低模、UV、细节烘焙、贴图压缩和实际设备测试。星体环境计划单独背景层处理，本场景的百万米坐标与远裁剪参数不作为网页参数直接套用。上一轮单片漆面 GLB 仍是独立流程样本。

云端 960×600、32 次采样约 6–18 秒一张；进程 RSS 高水位约 1172 MiB。目前没有必须移交本地 GPU 的瓶颈。待用户明确连接家中电脑后，才核对机器、授权、Blender、驱动和实际显存，再从 640×400 小样开始评估 `--device optix`。本包不授予任何本地访问权限，不默认付费 GPU，预览规格不改变最终质量目标。
