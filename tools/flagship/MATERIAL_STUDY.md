# 局部材质任务包 · material-study-01

本包接续结构草模 02，单独制作左舷后肩与三处喷口的材质/结构样板。它不替代整舰结构稿，也不是完整休伯利安号模型或已接入网站的资产。

## 先查看

- `previews/material-study-01.webp`：相同局部机位、灯光下的旧草模与当前样板。
- `scenes/shoulder-material-study.blend`：可编辑肩部、喷口、程序化材质、打包粗糙度纹理和三台相机。
- `web-swatch/armor-material-swatch.glb`：**2.5 m 漆面样片**，2 个三角形、3 张内嵌 1024 贴图，约 332 KiB。它只验证材质转换，不能用来展示整个肩部。
- `web-swatch/textures/`：颜色、粗糙度、切线法线和 ORM。ORM 的 R 为常数 1，G 为粗糙度，B 为常数 0；没有声称烘焙了遮蔽。
- `textures/source/`：已采用的 4K CC0 粗糙度原文件；`ATTRIBUTION.md` 记录作者、出处和用途。
- `evidence/`：渲染、烘焙、导入回读、环境及跨目录检查记录。

这里的路径以下载任务包根目录为准。仓库中的源码和研究记录另行维护；源 `.blend` 和纹理通过版本化任务包交付。

## 依赖与资源闭合

实际验证版本：Blender **4.5.14 LTS** / `bpy==4.5.14`，Python 3.11.17。打开桌面 Blender `.blend` 无需额外安装 Python 包。可选对比图脚本依赖 Pillow 12.3.0。云端依赖见 `requirements-cloud.txt`；离线对比图依赖见 `requirements-review.txt`。

当前 `.blend` 只使用一张外部来源的粗糙度图，它的 1024 预览副本已经打包，旁边同时保存相对路径 `scenes/textures/blue_metal_plate_rough_1k.png`。原 4K 文件供重新生成和后续细化使用。生成器不会联网下载；所需输入缺失时会明确退出。

`SHIP_HULL` 是本轮保留的基础肩部，`MATERIAL_DETAILS` 是可编辑喷口/装甲细节，`BASELINE` 保存独立旧草模对照，默认隐藏。切换对照只改变可见性；镜头和物体变换不动。两组物体应择一显示，避免重叠。

Blender 坐标沿用草模 02：Z 向上，舰尾 +X，左舷 -Y。局部模型仍使用整舰坐标。原有整舰约 500 m 的尺度以及推进部件布置是设计假设；本轮没有推导真实推力、热流、材料寿命或官方引擎内部结构。

## 启动步骤

以下均从任务包根目录运行；先确认自己的 Blender 路径。默认全部为 **CPU**。

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/inspect_material_study.py -- --scene scenes/shoulder-material-study.blend --output evidence/validation-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/material_study.py -- render --scene scenes/shoulder-material-study.blend --output previews/local-cpu --views engine --width 640 --height 400 --samples 16
```

Linux/macOS 中以 `blender --background --python-exit-code 1 --python ... -- ...` 运行。已安装固定版本 `bpy` 的云端环境可以直接使用 `python tools/flagship/material_study.py ...`。脚本之间有相对导入，须保留整个 `tools/flagship` 文件夹。

重新生成样板和网页漆面样片：

```bash
blender -b --python-exit-code 1 --python tools/flagship/material_study.py -- build --output regenerated --roughness-texture textures/source/blue_metal_plate_rough_4k.jpg
blender -b --python-exit-code 1 --python tools/flagship/bake_material_swatch.py -- --scene regenerated/shoulder-material-study.blend --output regenerated-web-swatch --size 1024
```

制作同机位对照：

```bash
blender -b --python-exit-code 1 --python tools/flagship/material_study.py -- render --scene scenes/shoulder-material-study.blend --output previews/new --views shoulder,engine,armor
blender -b --python-exit-code 1 --python tools/flagship/material_study.py -- render --scene scenes/shoulder-material-study.blend --output previews/old --views shoulder,engine --baseline
python tools/flagship/material_review.py --baseline previews/old --current previews/new --output previews/comparison.webp
```

输出已存在时默认拒绝覆盖。需要重新试验时使用新目录；只有可再生成文件才使用 `--overwrite`，手工精修源文件应另存。

## 验证与后续本地交接

源资源打包、单个网格闭合/正向体积、对照集合分离和静态变换已经检查。仅把 `.blend` 复制到另一目录、不给旁置贴图，也能打开和渲染。漆面 GLB 已经真实导出并重新导入 Blender 渲染；不等于浏览器验收。

当前 960×600 / 32 次采样局部图约 11–17 秒，进程 RSS 高水位约 1002 MiB。未发现必须移交 GPU 的瓶颈，未连接家中电脑。用户明确连接后，才核对目标机器、授权状态、Blender、驱动和实际可用显存；先运行上面的小样，再考虑显式 `--device optix`。不默认租 GPU，且不因预览规格降低最终质量目标。

高精度源模型与网页资产继续分开。本轮只烘焙漆面，没有完成整个肩部的低模、UV 图集、几何细节烘焙、LOD、KTX2/Meshopt 或浏览器设备测试。
