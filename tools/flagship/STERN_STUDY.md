# 舰尾连接与推进段 · stern-study-01

本包是 kuhai 主舰的可编辑局部研究，基于 bridge-study-02 增加主喷口根部连接、侧肩检修护板、甲板支撑、分瓣外护板和少量管路。六个喷口布局、原有内衬、光源与整舰轮廓继续保留。它不是最终美术或经过物理验证的推进系统。

## 包内入口

- `scenes/flagship-stern-study-01.blend`：本轮完整源场景，新对象在 `STERN01_DETAILS`。
- `inputs/bridge-study-02.blend`：不可变前版输入，SHA-256 `1902afeb0228679ff5f8027f8a5adcf86cd4b4e07cfb4c4b1ba6c21b5a786e95`。
- `previews/stern-study-01.webp`：全舰尾视、根部连接和喷口近景。
- `previews/stern-study-01-comparison.webp`：同机位、同灯光前后对照。
- `previews/current/`、`previews/previous/`：未经修饰的 PNG 和渲染记录。
- `evidence/`：几何、资源、喷口抽样射线、环境与迁移检查。
- `tools/flagship/`：生成、检查、渲染和排版脚本、依赖模块、配置及版本要求。

在 Blender 中隐藏 `STERN01_DETAILS` 可查看前版外观，其他集合保持当前默认可见性。新增 `stern_connection`、`stern_nozzle` 两个透视机位；旧机位保持原参数。Blender Z 向上、舰首 -X、左舷 -Y，所有尺寸仍为暂定制作尺度。

## 资源和版本

已验证 Blender **4.5.14 LTS**，build `62c1db4208e8`，Python 3.11.17。桌面 Blender 打开 `.blend` 无需安装 pip 包；云端 `bpy` 环境按 `requirements-cloud.txt` 配置。排版工具单独使用 `requirements-review.txt`，Pillow 12.3.0。

本轮沿用已有材质：Rob Tuytel / Poly Haven [Blue Metal Plate](https://polyhaven.com/a/blue_metal_plate) 的 [CC0](https://polyhaven.com/license) 粗糙度及程序化材质。原始 4K JPG 和归属记录在 `textures/`；场景使用的 1K PNG 在各 `.blend` 旁的 `textures/`，使用相对路径并打包。没有新下载或附带第三方模型、参考图片、安装包或付费资产。

## 从包根目录运行

以下默认 CPU，不会自动启用 GPU。已有输出拒绝覆盖；手工精修另存，`--overwrite` 仅用于可再生成输出。

Linux / macOS，先确认 Blender 安装版本：

```bash
blender --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-new-machine.json
blender --background --python-exit-code 1 --python tools/flagship/stern_study.py -- inspect --baseline inputs/bridge-study-02.blend --scene scenes/flagship-stern-study-01.blend --output evidence/inspection-new-machine.json
blender --background --python-exit-code 1 --python tools/flagship/stern_study.py -- render --scene scenes/flagship-stern-study-01.blend --output previews/cpu-sample --views stern_connection --width 720 --height 450 --samples 16
```

Windows PowerShell，按真实安装位置设置路径：

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-new-machine.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/stern_study.py -- inspect --baseline inputs/bridge-study-02.blend --scene scenes/flagship-stern-study-01.blend --output evidence/inspection-new-machine.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/stern_study.py -- render --scene scenes/flagship-stern-study-01.blend --output previews/cpu-sample --views stern_connection --width 720 --height 450 --samples 16
```

已配置 pinned `bpy` 的 Python 可直接执行：

```bash
python tools/flagship/stern_study.py build --scene inputs/bridge-study-02.blend --output regenerated
python tools/flagship/stern_study.py inspect --baseline inputs/bridge-study-02.blend --scene regenerated/flagship-stern-study-01.blend --output evidence/regenerated-inspection.json
python tools/flagship/stern_study.py render --scene scenes/flagship-stern-study-01.blend --output previews/recheck-current --views stern,stern_connection
python tools/flagship/stern_study.py render --scene scenes/flagship-stern-study-01.blend --output previews/recheck-previous --views stern,stern_connection --previous
python tools/flagship/stern_review.py --input previews --output review-again
```

构建产出 `.blend`、贴图和清单；渲染产出 PNG 与逐帧耗时；检查产出 JSON，失败退出非零。`--previous` 仅隐藏新增集合。排版脚本预期同规格 960×600 原图，默认渲染 32 samples；只缩放和加说明，不重打光。

## 验证边界与交接

检查覆盖原对象记录、档案室、星体／灯光／原机位、新增网格的有限坐标、闭合性和正体积、相对路径及打包资源。对六个喷口各发射 13 条轴向射线，检查新增几何是否遮挡抽样区域；这不是排气流体、热、应力或全场碰撞分析。

当前环境只有 CPU，本轮小样仍能完成，没有启动本地工作。用户明确连接家中电脑后，再核实目标、授权、Blender、驱动、显卡和空闲显存；可在单帧小样命令中显式加 `--device optix`，据实测决定更高分辨率和批次，不预设 3060 Ti 能处理任意场景。

本轮没有生成新的整舰网页模型，也没有发布网页或测试浏览器 FPS。源文件保留可编辑结构；后续网页导出需要独立合并材质、简化细节、烘焙、压缩和设备验收。源模型面数不作为网页交付预算。
