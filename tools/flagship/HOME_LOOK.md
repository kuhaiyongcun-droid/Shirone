# 整舰首页质感 · home-look-01

基于 stern-study-01 的离线美术研究。新增冷灰漆面、裸金属区分、暖色恒星逆光与冷色补光，调整星球大小和位置，并保存横屏与竖屏固定机位。几何形体、档案室内部和已有灯窗继续保留。它是可继续精修的制作源文件，还不是正式网页资产或最终美术定稿。

## 包内入口

- `scenes/flagship-home-look-01.blend`：选定的 `rim` 逆光方案。
- `inputs/stern-study-01.blend`：不可变输入，SHA-256 `b141b562047614d2a5819a1a67936fa6af81ba611d7e292890ed95cee5f0254c`。
- `previews/home-look-01.webp`：1280×800 首页视角样片。
- `previews/home-look-01-comparison.webp`：原版、只改材质、日照、选定逆光四组对照。
- `previews/home-look-01-views.webp`：竖屏、局部漆面与舰尾检查图。
- `previews/{baseline,materials,day,current,details,portrait,hero}/`：未经修饰的 PNG 与逐帧耗时。
- `evidence/`：环境、保留约定、资源、构图和迁移检查。
- `tools/flagship/`：生成、检查、渲染、排版脚本及依赖和配置。

在 Blender 中直接打开源场景。`CAMERAS` 中的 `home` 为横屏、`home_portrait` 为竖屏、`finish_detail` 为局部漆面；原机位仍保留。竖屏是另一个固定起始构图，不是鼠标悬停触发的旋转或镜头动画。新材质以 `HOME01 / ` 开头，通过对象材质槽覆盖应用，网格原材质与节点保留。不要只读取 `mesh.materials` 导出，否则会遗漏对象覆盖。

## 资源与版本

已验证 Blender **4.5.14 LTS**，build `62c1db4208e8`、Python 3.11.17；云端使用 `bpy==4.5.14`、`numpy==1.26.4`。桌面 Blender 直接打开文件无需 pip。排版工具独立使用 Pillow 12.3.0，可用 DejaVu Sans，缺失时回退 Pillow 默认字体。其他版本和用户电脑尚未实测。

本轮没有新增第三方资产。沿用 Rob Tuytel / Poly Haven [Blue Metal Plate](https://polyhaven.com/a/blue_metal_plate) 的 [CC0](https://polyhaven.com/license) 粗糙度。原始 4K JPG 与归属记录在 `textures/`；场景使用的 1K PNG 位于每份 `.blend` 旁的 `textures/`，使用相对路径且同时打包。星体、云层和星场继续采用已有程序化素材。

## 从任务包根目录运行

默认 CPU、6 线程。输出已存在会拒绝覆盖；手工精修应另存。`--overwrite` 只用于明确可再生成的输出。

Linux / macOS，Blender 已在 PATH：

```bash
blender --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-new-machine.json
blender --background --python-exit-code 1 --python tools/flagship/home_look.py -- inspect --baseline inputs/stern-study-01.blend --scene scenes/flagship-home-look-01.blend --output evidence/inspection-new-machine.json
blender --background --python-exit-code 1 --python tools/flagship/home_look.py -- render --scene scenes/flagship-home-look-01.blend --output previews/cpu-sample --views home --width 720 --height 450 --samples 16
```

Windows PowerShell，先按实际安装位置设置：

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/preflight.py -- --output evidence/preflight-new-machine.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/home_look.py -- inspect --baseline inputs/stern-study-01.blend --scene scenes/flagship-home-look-01.blend --output evidence/inspection-new-machine.json
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/home_look.py -- render --scene scenes/flagship-home-look-01.blend --output previews/cpu-sample --views home --width 720 --height 450 --samples 16
```

已配置 pinned `bpy` 的 Python 可直接运行；桌面 Blender 可使用以上命令前缀加 `--` 传递同样的参数：

```bash
python tools/flagship/home_look.py build --scene inputs/stern-study-01.blend --output regenerated --profile rim
python tools/flagship/home_look.py build --scene inputs/stern-study-01.blend --output variants/day --profile day
python tools/flagship/home_look.py build --scene inputs/stern-study-01.blend --output variants/materials --profile materials
python tools/flagship/home_look.py render --scene scenes/flagship-home-look-01.blend --output previews/recheck-current --views home,finish_detail,stern
python tools/flagship/home_look.py render --scene scenes/flagship-home-look-01.blend --output previews/recheck-portrait --views home_portrait --width 600 --height 960
python tools/flagship/home_look.py render --scene inputs/stern-study-01.blend --output previews/recheck-baseline --views home
python tools/flagship/home_look_review.py --input previews --output review-again
```

生成产出 `.blend`、贴图和 `look-manifest.json`；渲染产出 PNG、机位投影范围与耗时 JSON，默认 960×600、32 samples；检查失败退出非零。`materials` 只改外部材质；`day` 和 `rim` 同时改外部材质、环境灯光、曝光、星球位置和尺度。渲染脚本不改写输入文件。

## 制作设置与实测

Cycles CPU、AgX、固定采样、去噪，沿用原场景反弹设置。主光与星球薄大气节点共享同一方向；薄大气是艺术近似，未做物理散射积分。两个 Area 补光仍是美术辅助，不作为真实行星反照率计算。已有青色引擎和暖色窗灯的发光材质没有改写。

本机 960×600、32 samples 的六帧实测约 8.49–16.83 秒；600×960 竖屏约 10.02 秒；1280×800、48 samples 约 24.92 秒。最高观测进程 RSS 为 1529.23 MiB。这些是当前 CPU 离线渲染记录，不能换算浏览器 FPS 或 GPU 显存。当前样片没有需要换本地 GPU 的瓶颈。

源文件、完整前版输入、贴图和脚本从新目录实际打开、检查与复渲染。检查覆盖 2342 个原有非星球网格记录、36 个原材质节点记录、档案室和局部灯光、旧相机、星光方向、星体同心性及相对贴图与打包字节。横屏和竖屏对整舰包围盒做投影边界检查；不代表所有自由旋转角度都已验收。

## 后续分工

用户明确连接家中电脑后，再核实机器、授权、Blender、驱动、显卡和空闲显存；仅在那之后考虑小样命令的 `--device optix`，据实测决定高清与批量设置。当前包没有启动本地任务或付费服务。

本轮没有更新整舰 GLB、网页灯光、浏览器交互、已发布站点或 Shirone 博客。先前网页漆面试片也不会自动获得新的配色；正式导出须独立烘焙、简化、压缩，并与这里的离线基准对照。后续优先补足侧舷、腹部和旋转中暴露的中尺度结构，再做网页资产优化与设备验收。
