# 主舰结构草模任务包 · blockout-01

这是 kuhai 个人网站主舰的**结构验证草模**，不是最终造型、高精度母版或已上线首页。制作目标仍是高质量的休伯利安号式战舰；本轮以低成本检查比例、局部剖视、材质反应和迁移流程。

## 先看什么

- `previews/blockout-01.webp`：整舰、俯视、尾部、档案室和材质样板总览。
- `scenes/flagship-blockout.blend`：可编辑草模。主场景保留对象、倒角修改器、程序化材质、灯光和 8 个机位。
- `scenes/flagship-web-study.glb`：独立网页结构样本，约 4.08 MiB、64,400 三角形、18 个按角色/材质合并的网格。尚未做 UV、烘焙、LOD、压缩或浏览器性能验收。
- `scenes/scene-manifest.json`：坐标约定、舱室尺度、对象统计与缺失工作。
- `previews/renders/`：8 张 720×450 检查图；`evidence/` 包含环境记录、渲染耗时和迁移检查。

以上目录指下载的任务包根目录。GitHub 中维护生成脚本和研究记录；较大的可编辑场景通过版本化任务包交付。

## 依赖与资源

已验证：Blender **4.5.14 LTS** / Blender Foundation `bpy==4.5.14`，Python 3.11.17；云端 Linux、6 个渲染线程、CPU Cycles。桌面 Blender 内置 Python，直接打开 `.blend` **不用安装 pip 包**。其他 Blender 版本尚未验证。

- 所有材质和示意星体都是程序化节点，本包**没有外部图片贴图依赖**。
- 未打包游戏原始模型、社区二创模型、付费素材、第三方参考图或 Blender 安装程序。
- 参考来源仅记录链接及查阅状态。舰体全长约 500 m 的工程比例、36×18×5 m 的档案室和内部布局均为暂定创作假设，不是已核实的官方数据。
- 生成脚本默认输出到脚本旁的 `output/`。输出已存在时拒绝覆盖；确认是可再生成的文件后才能加 `--overwrite`。请另存手工修改后的 `.blend`。
- `textures/README.md` 说明当前无需外部贴图；以后使用图片时须同包保存并改为相对路径或打包进 `.blend`。

免费桌面软件下载：[Blender 官方](https://www.blender.org/download/)。云端可选 [Blender Foundation bpy](https://pypi.org/project/bpy/4.5.14/)，配合本目录的 `requirements-cloud.txt`。

## 在 Blender 中查看

1. 打开 `scenes/flagship-blockout.blend`，选择 `KUHAI — Structural Study 01` 场景。
2. `SHIP_HULL` 是外部舰体，`ARCHIVE_INTERIOR` 是独立舱室，`ARCHIVE_SHELL` 是可移除的局部屋顶和外壁。隐藏 `ARCHIVE_SHELL` 可检查剖视；舰体与相机保持原位。
3. `CAMERAS` 保存 `hero`、`top`、`side`、`rear`、`belly`、`archive_context`、`archive`、`coupon`。渲染脚本会设置每个机位所需的集合可见性。
4. `COUPON` / `COUPON_LIGHTS` 是局部装甲样板，默认隐藏，位于主舰旁的独立制作区域。
5. `WEB_EXPORT — simple PBR / no scene lighting` 是与母版对象分开的导出场景。网页样本材质是简化 PBR，不能期待与源场景的程序化金属完全一致。

坐标：Blender Z 向上、舰首 -X、舰尾 +X、左舷 -Y；glTF 导出器转换为 Y 向上。GLB 的 `extras.role` 为 `hull`、`archive_shell`、`archive_interior`；后两类带 `room_id=archive`。

## 可复现启动步骤

以下从**任务包根目录**运行。先手动确认 Blender 路径；示例路径不代表已检测到用户电脑。

Windows PowerShell：

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/inspect_scene.py -- --scene scenes/flagship-blockout.blend --output evidence/validation-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/render_study.py -- --scene scenes/flagship-blockout.blend --views coupon --width 720 --height 450 --samples 24 --output previews/local-cpu-sample
```

Linux / macOS（`blender` 已在 PATH）：

```bash
blender --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-local.json
blender --background --python-exit-code 1 --python tools/flagship/inspect_scene.py -- --scene scenes/flagship-blockout.blend --output evidence/validation-local.json
blender --background --python-exit-code 1 --python tools/flagship/render_study.py -- --scene scenes/flagship-blockout.blend --views coupon --output previews/local-cpu-sample
```

生成一份新草模（不覆盖手工修改过的源文件）：

```bash
blender --background --python-exit-code 1 --python tools/flagship/build_scene.py -- --output regenerated
```

已有 Python 3.11 的云端可在独立虚拟环境安装依赖，用 `python tools/flagship/build_scene.py --output regenerated` 替代 Blender 命令前缀；`render_study.py` 和 `inspect_scene.py` 同理。

## 本地 GPU 交接

**当前没有获得本地电脑访问权限，也没有在本地运行任务。** 用户明确说家里的电脑已连接后，才核对目标机器、授权状态、Blender、显卡驱动、实际 GPU 和剩余显存。用户提供的 RTX 3060 Ti 型号不代替这些检查。

先运行只读 `preflight.py`；它只清点环境，不渲染。确认唯一的目标 GPU 和任务范围后，运行单张小样：

```powershell
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/render_study.py -- --scene scenes/flagship-blockout.blend --views archive --width 960 --height 600 --samples 32 --device optix --output previews/local-optix-sample
```

脚本默认 CPU；OptiX 只有显式指定后才启用，多 GPU 时会拒绝自动挑选。小样记录耗时；显存使用另用任务管理器或 `nvidia-smi` 观测，不能拿 CPU 内存数字替代。小样之后再决定最终分辨率、采样、分块/分批、纹理大小和是否需分场景。

复杂舰体、高清材质、整舰高清静帧、批量烘焙可以进入本地候选队列；必须先有实际云端测试与瓶颈记录。云端慢不意味着降低最终质量，也不默认租 GPU 或购买服务。

## 预期产物与验证边界

| 操作 | 产物 |
| --- | --- |
| `build_scene.py` | 可编辑 `.blend`、独立 `.glb`、`scene-manifest.json` |
| `render_study.py --views hero,archive,coupon` | 三张 PNG、逐帧耗时 JSON；不改写源 `.blend` |
| `inspect_scene.py` | 外部依赖、剖视变换、舱室范围、GLB 角色与容器检查 |
| `preflight.py` | 目标机器、软件、CPU/容器限制、可发现的显卡与驱动信息 |

迁移测试已把 `.blend` 和 `.glb` 复制到另一目录重新打开、检查并渲染。此验证不等同于已在 Windows 或用户的 3060 Ti 上运行。

当前主要造型问题：侧面层次偏平、肩翼偏板状、舰桥仍为体块；内部只有一处占位档案室，未做全舰工程设计。下一轮先校正电影参考与多视角轮廓，再细化外壳结构和局部材质。全舰微细节、高清整舰渲染、真实星图与星体贴图留待结构方向确认后。
