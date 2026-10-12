# 舰桥左舷结构样板 03 使用说明

可编辑源以 home-look-01 为输入。`SIDE03_STRUCTURE` 是本轮结构，`SIDE03_PREVIOUS` 保留原左舷支撑，`SIDE03_CUTTERS` 保存布尔工具。旧对象、灯光、档案室和材质节点保留；仅替换支撑的可见状态发生变化。开口处为虚构的外部设备凹舱，不代表已确认的官方内部布局。

## 任务包

- `scenes/flagship-side-study-03.blend`：新源场景，SHA-256 `14a58708c990193d989f298f3f628b5a89dc7b2b82c476281630187a5494d57a`。
- `inputs/home-look-01.blend`：不可变输入，SHA-256 `e05803fd34da6ccff0fb680bf3953165aabf742bd659342f5680de1022d0e9a7`。
- `previews/`：原始中性光前后、气氛光与网页 GLB 离线回读图及耗时记录。
- `web-assets/`：新版 GLB 与清单；制作单位为米，网页按 100 米／单位导出。
- `textures/`：继承贴图与来源记录。场景旁的 `textures/` 使用相对路径，图片也已打包在 `.blend` 内。
- `tools/flagship/`：重建、CPU 渲染、导出、检查与排版脚本及配置。
- `evidence/`：检查和迁移记录。`manifest.json`：文件校验表。

环境沿用 Blender 4.5.14 LTS、Python 3.11.17、numpy 1.26.4；排版工具另用 Pillow 12.3.0。桌面 Blender 打开源文件无需安装 pip 包。已安装 pinned bpy 的 Python 可直接执行脚本；桌面 Blender 使用 `blender --background --python-exit-code 1 --python SCRIPT -- ARGS`。相机 `side03_detail`、`side03_context`、`side03_reverse` 用于本轮，`home` 保留整舰视角。

## 从任务包根目录运行

```sh
python tools/flagship/preflight.py --output evidence/new-machine.json
python tools/flagship/side_study.py inspect --baseline inputs/home-look-01.blend --scene scenes/flagship-side-study-03.blend --output evidence/recheck.json
python tools/flagship/side_study.py render --scene scenes/flagship-side-study-03.blend --output previews/recheck --views side03_detail --neutral --width 720 --height 450 --samples 16
python tools/flagship/side_study.py render --scene scenes/flagship-side-study-03.blend --output previews/recheck-previous --views side03_detail --neutral --previous --width 720 --height 450 --samples 16
python tools/flagship/export_review.py --source scenes/flagship-side-study-03.blend --output regenerated-web
python tools/flagship/inspect_review.py --assets regenerated-web --output evidence/web-recheck.json
```

生成新源文件使用 `python tools/flagship/side_study.py build --scene inputs/home-look-01.blend --output regenerated-scene`。已有模型或渲染输出会拒绝覆盖。生成器重建的 `.blend` 字节可能不同；网页导出使用已登记的不可变场景，重建源需完成检查并登记指纹后再用于发布，不能关闭指纹检查。

Windows PowerShell 示例，先核实实际 Blender 安装位置：

```powershell
$BlenderPath = "C:\Program Files\Blender Foundation\Blender 4.5\blender.exe"
& $BlenderPath --background --python-exit-code 1 --python tools/flagship/side_study.py -- render --scene scenes/flagship-side-study-03.blend --output previews/windows-cpu-sample --views side03_detail --neutral --width 720 --height 450 --samples 16
```

默认 CPU、6 线程。只有用户明确连接家中电脑并核实目标机器、授权、驱动与空闲显存后，才考虑显式传入 `--device optix` 做小样；此参数不会自动回退其他机器。当前云端 CPU 预览仍足够，不需要本地 GPU。

`--previous` 恢复本轮替换前的结构，机位与照明不变；`--neutral` 仅在渲染进程内创建中性检查灯光，不写回源文件。`--web-model web-assets/flagship.glb` 隐藏原舰体并回读实际网页模型，以对应尺度进行离线检查；不能与 `--previous` 同用，也不能称为浏览器截图。

网页页面源码仍在 GitHub 的 `tools/flagship/review`。完整页面构建需要仓库 i18n 文件，任务包里的 GLB 可在现有网页工程中替换；它不是完整博客或独立 HTML 下载包。当前程序化旧化没有完整转入网页，浏览器性能尚待实测。
