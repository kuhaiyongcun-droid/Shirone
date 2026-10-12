# 舰桥侧后结构与漆面样板 · bridge-study-02

本轮在 bridge-study-01 的完整源场景上增加六片贴合舰脊侧面的装甲、两组检修盖及后侧设备护罩，并以其中一块真实检修盖验证材质烘焙。它是 kuhai 主舰的局部制作研究，尚未定稿。

## 包内入口

- `scenes/flagship-bridge-study-02.blend`：可编辑整舰源场景；新对象在 `BRIDGE02_DETAILS`。
- `inputs/bridge-study-01.blend`：前版完整输入，SHA-256 `3897040bdd78990d704e5b3ae0a82023e7c81f380762a2c72aa36d2b1d3e2bab`。
- `sample/bridge-coating-sample.blend`：独立材质样板，`SOURCE_COATING` 保存可编辑程序节点，默认隐藏；`BAKED_COATING` 显示实际 GLB 回读结果。比较时只显示一组。
- `sample/bridge-inspection-cover.glb`：仅检修盖本体，220 个三角形，3 张内嵌 1K 贴图，499,828 字节；不包含独立紧固件、标记或整舰。
- `sample/textures/`：颜色、粗糙度、金属度、切线法线和 ORM 图。ORM 的 R 恒为 1，没有烘焙 AO。
- `previews/`：同机位旧版／新版 PNG、材质对照和排版预览；无后期重打光。
- `evidence/`：几何检查、烘焙检查、环境、迁移渲染记录。
- `tools/flagship/`：生成、烘焙、检查、渲染、排版脚本，以及所需依赖模块和配置。

完整源场景使用 Blender Z 向上、舰首 -X、左舷 -Y。材质样板 GLB 保留原始世界位置，1 单位为 1 米，导出转换为 Y 向上；它与既有整舰网页样板的 100 米／单位约定不同，集成前必须明确换算。

## 环境与资源

已验证 Blender **4.5.14 LTS**，build `62c1db4208e8`，Python 3.11.17。桌面 Blender 直接打开场景无需安装 pip 依赖；云端 Python 路线见 `requirements-cloud.txt`。排版可单独安装 `requirements-review.txt`，使用 Pillow 12.3.0。

沿用 Rob Tuytel / Poly Haven 的 [Blue Metal Plate](https://polyhaven.com/a/blue_metal_plate) 粗糙度，许可 [CC0](https://polyhaven.com/license)。实际使用的 1K PNG 位于各 `.blend` 旁的 `textures/`，路径相对且资源已打包。原始 4K JPG 和来源记录在包根 `textures/`。没有附带官方／二创模型或参考图片。

材质区分介电漆层、底漆与裸露金属，边缘磨损由实际局部坐标生成；微凹凸保持克制。烘焙前对复制出的盖板三角化并展开 UV，不改原始场景。细节尺寸与布局均是本项目暂定美术推演。

## 从包根运行

所有脚本默认 CPU。先核实目标机器；示例不会自动使用显卡。已有输出拒绝覆盖，手工精修请另存。

Linux / macOS，已安装对应 Blender：

```bash
blender --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-new-machine.json
blender --background --python-exit-code 1 --python tools/flagship/bridge_finish.py -- inspect --baseline inputs/bridge-study-01.blend --scene scenes/flagship-bridge-study-02.blend --output evidence/inspection-new-machine.json
blender --background --python-exit-code 1 --python tools/flagship/bridge_finish.py -- render --scene scenes/flagship-bridge-study-02.blend --output previews/cpu-sample --views bridge_side --width 640 --height 400 --samples 16
blender --background --python-exit-code 1 --python tools/flagship/verify_bridge_sample.py -- --scene sample/bridge-coating-sample.blend --output evidence/sample-new-machine --render
```

Windows PowerShell，先确认实际安装路径：

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-new-machine.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/bridge_finish.py -- render --scene scenes/flagship-bridge-study-02.blend --output previews/cpu-sample --views bridge_side --width 640 --height 400 --samples 16
```

已配置 pinned `bpy` 的云端 Python 可直接运行：

```bash
python tools/flagship/bridge_finish.py build --scene inputs/bridge-study-01.blend --output regenerated
python tools/flagship/bridge_finish.py inspect --baseline inputs/bridge-study-01.blend --scene regenerated/flagship-bridge-study-02.blend --output evidence/regenerated-inspection.json
python tools/flagship/bridge_finish.py render --scene scenes/flagship-bridge-study-02.blend --output previews/recheck-current --views bridge_side,bridge_rear
python tools/flagship/bridge_finish.py render --scene scenes/flagship-bridge-study-02.blend --output previews/recheck-previous --views bridge_side,bridge_rear --previous
python tools/flagship/bake_bridge_finish.py --scene scenes/flagship-bridge-study-02.blend --output sample-rebaked --size 1024
python tools/flagship/bridge_finish_review.py --input previews --sample sample --output review-again
```

`--previous` 只隐藏本轮 `BRIDGE02_DETAILS`，其余源对象、机位和光照保持相同。新受光侧机位为 `bridge_side`、`bridge_rear`、`bridge_finish_lit`；`bridge_finish` 另保留背光侧近景。整舰旧机位不变。

检查失败时返回非零状态。渲染产出 PNG 和逐张耗时记录；烘焙产出 `.blend`、GLB、PNG、`bake-report.json`。迁移检查实际打开包内文件并渲染，不能只依赖路径字符串。

## 当前边界与下一步

这次是离线材质及局部模型交付，没有把整舰细节直接上传为网页模型，也没有浏览器 FPS 结论。后续先继续评估硬件尺度与远近景密度，再把确定的材质规则应用到重点部位；整舰 UV、细节分档、压缩和设备性能独立验收。

当前云端单帧 960×600、32 samples 的 CPU 预览约 14–22 秒，尚不需要连接本地 GPU。用户明确连接家用电脑后，再核对授权、Blender、驱动与空闲显存；先运行小样，依据实测决定是否使用 OptiX、更大分辨率或批次。3060 Ti 的能力不作为访客设备要求。
