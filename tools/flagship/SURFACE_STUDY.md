# 局部装甲与检修口任务包 · surface-study-02

本轮以 form-study-03 为输入，在舰首上面、前肩和档案室可移除顶盖制作局部装甲样板。是可编辑的制作样本，未达到最终整舰材质或发布质量。

## 先看与打开

- `previews/surface-study-02.webp`：四处局部近景。
- `previews/surface-study-02-comparison.webp`：三组同相机、同光照前后对照。
- `previews/surface-study-02-structure.webp`：档案室顶盖关闭/移除，室内未改动。
- `scenes/flagship-surface-study-02.blend`：Blender 4.5.14 LTS 可编辑源场景；输入保留在 `inputs/form-03/`。
- `web-panel/archive-maintenance-cover.glb`：从源场景中提取的**单个 4 × 3.2 × 0.2 m 检修盖**，包括真实倒角与烘焙材质。锁扣、螺栓、格栅仍是源场景中的独立对象，不在此 GLB 中。
- `evidence/`：模型检查、运行环境、CPU 耗时及跨目录验证；`web-panel/` 还有烘焙和 glTF 检查记录。

`SURFACE02_HULL` 是新增舰体板件；`SURFACE02_ARCHIVE` 属于 `ARCHIVE_SHELL` 的子集合。隐藏父集合即可连同新细节一起移除屋顶。隐藏两个 `SURFACE02_*` 集合则恢复本轮之前的可见外观。原 `ARCHIVE_INTERIOR`、环境、灯光和原相机保留。

## 材质、尺寸与资源

新漆面使用程序化颜色/粗糙度和轻微凹凸，金属度为 0。少量露出的锁扣接触面使用原合金材质。三种面板漆色表示维护批次差异，未添加全舰污垢、锈蚀或弹坑。板缝、厚度、标记和检修盖大小均是视觉推演，未获官方工程图支持。

场景单位米，Z 向上、舰首 -X、左舷 -Y；暂定整舰尺度沿用约 500 m。单盖 GLB 为 **1 单位 = 1 米、Y 向上、保留原舰体世界位置**。原网页审阅整舰采用 100 m/单位；未来整合时需要明确换算，不能直接替换既有归一化舰体网格。

3 张 1024² 贴图内嵌 GLB：sRGB 颜色、非颜色 ORM、切线法线。ORM 的 R=1，G=粗糙度，B=0；没有声称烘焙 AO。独立的粗糙度 PNG 也随包保留。旧场景沿用 Rob Tuytel / Poly Haven 的 CC0 粗糙度图片，1K 版本已内嵌并随场景保存，4K 来源在 `textures/source/`，详见 `ATTRIBUTION.md`。没有新增下载游戏贴图或二创模型。

## 依赖与启动

已测试 Blender 4.5.14 LTS / 构建 `62c1db4208e8`、Python 3.11.17、numpy 1.26.4。桌面 Blender 自带渲染脚本依赖，不用安装 bpy。云端依赖为 `requirements-cloud.txt`；排版对比板额外使用 `Pillow==12.3.0`（`requirements-review.txt`）。

以下从任务包根目录执行。Windows 的 Blender 路径是示例，尚未核实用户电脑。所有命令默认 CPU，已有输出默认拒绝覆盖；手工修改请另存文件。

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/inspect_surface_study.py -- --scene scenes/flagship-surface-study-02.blend --baseline inputs/form-03/flagship-form-study-03.blend --output evidence/inspection-local.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/surface_study.py -- render --scene scenes/flagship-surface-study-02.blend --output previews/local-cpu --views surface_archive --width 640 --height 400 --samples 16
```

Linux/macOS 可用 `blender -b --python-exit-code 1 --python ... -- ...`；固定版本的云端 bpy 环境可直接运行 `python tools/flagship/<脚本>.py ...`。

```bash
blender -b --python-exit-code 1 --python tools/flagship/surface_study.py -- build --scene inputs/form-03/flagship-form-study-03.blend --output regenerated
blender -b --python-exit-code 1 --python tools/flagship/surface_study.py -- render --scene regenerated/flagship-surface-study-02.blend --output previews/new --views surface_bow,surface_shoulder,surface_archive,surface_hatch
blender -b --python-exit-code 1 --python tools/flagship/surface_study.py -- render --scene regenerated/flagship-surface-study-02.blend --output previews/old --views surface_bow,surface_shoulder,surface_archive --baseline
blender -b --python-exit-code 1 --python tools/flagship/surface_study.py -- render --scene regenerated/flagship-surface-study-02.blend --output previews/open --views surface_archive --cutaway
blender -b --python-exit-code 1 --python tools/flagship/bake_surface_panel.py -- --scene scenes/flagship-surface-study-02.blend --output web-panel-rebuilt --size 1024
```

预期产物分别为新 `.blend` 和 manifest、逐帧 PNG/耗时 JSON、独立单盖 GLB/贴图/回读图/烘焙报告。生成器核对上一版 SHA256，避免把手工修改后的源文件当作固定基线。

已有原始帧可用独立 Python 环境重新排版；只缩放和排列，不修改材质、颜色或光影：

```bash
python tools/flagship/surface_review.py --input previews --output previews/boards-rebuilt
```

## 性能与后续边界

云端 CPU、6 线程：960×600 / 32 采样局部帧约 12–17 秒，峰值进程 RSS 约 1.2 GiB；三个烘焙通道合计约 3 秒。单盖 GLB 147,928 字节、108 三角形，glTF Validator 0 错误 / 0 警告。单盖大小不能外推为整舰大小，也没有测得访客浏览器 FPS。

本轮源模型新增 71 个网格、11,988 个求值三角形，另有一个可编辑文字对象。制作源文件和网页资产继续分离。暂不发布到现有网页审阅站点或替换博客。

尚无必须转移到本地 GPU 的瓶颈。用户明确连接家中电脑后才核对机器、授权、Blender、驱动和实际可用显存，再做小样。没有访问或运行用户的 RTX 3060 Ti，也没有租用 GPU。下一步优先检查远近镜头中的细节密度与尺度，再决定整舰推广范围。
