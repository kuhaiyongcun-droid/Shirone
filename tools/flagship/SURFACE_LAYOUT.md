# 远近景与装甲分区任务包 · surface-study-03

本轮在 surface-study-02 上调整板件节奏，并检查整舰远景、局部近景和小尺寸静态画面。源模型继续保留全部检修细节，尚未作为最终美术或新网页版本发布。

## 文件与改动

- `scenes/flagship-surface-study-03.blend`：当前可编辑源场景。
- `inputs/surface-02/flagship-surface-study-02.blend`：保持原 SHA256 的上一版，可重建当前版本。
- `previews/surface-study-03.webp`：整舰与两个局部；`surface-study-03-comparison.webp`：同机位前后对照；`surface-study-03-small-width.webp`：384×240 原始像素大小的微细节省略对照。
- `previews/current/`、`previous/`、`cutaway/`、`small-full/`、`small-far/`：未修图的原始帧与逐帧耗时。
- `evidence/`：环境、源模型检查、跨目录检查和小尺寸像素差；`DELIVERY.json`、`SHA256SUMS`：包内版本与校验值。

原 47 片局部装甲改为 23 片：舰首 4、左右前肩各 5、档案室顶盖 9。纵向分区和连续维护带减少重复方格，名义同平面接缝统一为 0.20 m；曲面转折处仍需要后续艺术检查。当前尺度是视觉推演，不是官方尺寸或工程验算。

`SURFACE03_HULL` / `SURFACE03_ARCHIVE` 是新板件。旧 47 片留在默认隐藏的 `SURFACE03_PREVIOUS_HULL` / `SURFACE03_PREVIOUS_ROOF`；前后对比只切换这四个集合。两个屋顶集合都由 `ARCHIVE_SHELL` 管理，原有锁扣、检修口与格栅也继续随舱区剖视移除。原舰体、舱内、硬件、相机位置与照明保持原数据。

坐标沿用米制、Z 向上、舰首 -X、左舷 -Y。板层顶部高度保持原位，以免检修盖、格栅和标记出现漂浮。源场景的程序化材质可编辑；已有 CC0 粗糙度图片同时内嵌并保留相对路径，来源及使用条件见 `ATTRIBUTION.md`。

## 依赖与启动

已验证 Blender 4.5.14 LTS（构建 `62c1db4208e8`）、Python 3.11.17、numpy 1.26.4，云端 CPU Cycles / 6 线程。桌面 Blender 自带脚本依赖；云端 bpy 依赖见 `tools/flagship/requirements-cloud.txt`。对比图工具单独需要 `Pillow==12.3.0`，见 `requirements-review.txt`。

从任务包根目录执行；默认 CPU，已有模型和渲染默认拒绝覆盖。Windows 路径只是启动示例，不代表用户电脑已连接或核实。

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/surface_layout.py -- inspect --scene scenes/flagship-surface-study-03.blend --baseline inputs/surface-02/flagship-surface-study-02.blend --output evidence/inspection-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/surface_layout.py -- render --scene scenes/flagship-surface-study-03.blend --output previews/local-cpu --views overview --width 640 --height 400 --samples 16
```

Linux/macOS 使用 `blender -b --python-exit-code 1 --python ... -- ...`；固定 bpy 环境可以直接运行 `python tools/flagship/surface_layout.py ...`。

```bash
blender -b --python-exit-code 1 --python tools/flagship/surface_layout.py -- build --scene inputs/surface-02/flagship-surface-study-02.blend --output regenerated
blender -b --python-exit-code 1 --python tools/flagship/surface_layout.py -- render --scene regenerated/flagship-surface-study-03.blend --output previews/rebuilt --views overview,form_close,surface_bow,surface_shoulder,surface_archive
blender -b --python-exit-code 1 --python tools/flagship/surface_layout.py -- render --scene regenerated/flagship-surface-study-03.blend --output previews/rebuilt-previous --views overview,surface_bow,surface_archive --previous
blender -b --python-exit-code 1 --python tools/flagship/surface_layout.py -- render --scene regenerated/flagship-surface-study-03.blend --output previews/rebuilt-open --views surface_archive --cutaway
blender -b --python-exit-code 1 --python tools/flagship/surface_layout.py -- render --scene scenes/flagship-surface-study-03.blend --output previews/small-test --views overview --width 384 --height 240 --samples 32 --far-detail-preview
python tools/flagship/surface_layout_review.py --input previews --output previews/boards-rebuilt
```

`build` 产出新 `.blend` 和 manifest；`render` 产出 PNG 与逐帧 benchmark；`inspect` 产出几何、资源、舱室归属与投影尺寸 JSON。`--far-detail-preview` 只在当次渲染省略 22 个小物件，不改写源场景。它是可视性试验，没有实现浏览器运行时的 LOD 切换。

## 实测与边界

960×600 / 32 采样帧约 10.4–17.6 秒，进程 RSS 峰值约 1.17 GiB；两张 384×240 小样各约 2.7 秒。新板件 4,372 个求值三角形，旧板件 9,268 个；这些只是局部板件统计，不能外推整舰网页性能。

小尺寸对照中，92,160 个像素仅 4 个的最大通道差超过 2/255；最大差 5/255。这是一个固定相机的静态 Cycles 对照，含采样噪声，不是手机实测、浏览器 FPS 或移动过程中的 LOD 跳变验收。源模型保留全部细节；后续网页资产需要单独处理拓扑、烘焙与距离分档。

当前没有新整舰 GLB，也没有更新已发布审阅站点或博客。无需转移到本地 GPU；用户明确连接家中电脑后，仍须核实目标机器、授权、Blender、驱动和可用显存，再做单张小样。未访问用户的 RTX 3060 Ti，未租用算力。最终质量目标保持不变。
