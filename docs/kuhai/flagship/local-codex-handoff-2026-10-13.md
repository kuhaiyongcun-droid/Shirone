# 主舰制作冻结与本地 Codex 交接（2026-10-13）

本轮只收尾、归档与提交，不继续复杂建模，不部署、不合并。最新真实制作版为 **fore-root-11**，不是全站完成。先取得完整包并校验，再接手模型；主线旧审阅网页仍是 study03，不能直接换 GLB 就宣称新版网页完成。

## 来源与分支边界

来源会话： https://chatgpt.com/c/6acd90b3-1638-83ec-b273-b2704549a619 。源任务 `01a132fd-81ab-75fe-9a10-bce83171d0a3`；最新完成轮次 `01a1347f-2886-7640-8767-32698a5817c6`（用户交接提供，任务状态未在本轮重新查询）。结果缺失不触发重做，旧会话保留。

核对时 GitHub `main` 为 `9fac8402a09effaadef454450859dd9f8199778e`（study03）。博客 PR #1 仍 open/draft、未合并，`sync/localized-blog` 为 `ceb6959c2b1b71dffd35baf898b74e48f0abded3`；不处理该 PR 的冲突、不合并。收尾分支 `chore/flagship-local-handoff-20261013` 从上述 main 建立。

制作沿革：完整 home-look-01 + study03 脚本 → 经许可恢复的 study04 → assembly05 → surface06 → lighting07 → fore08 → fore09 材质 → fore-lighting10 → fore-root11。旧 study03 ZIP 损坏，原母版字节没有恢复；包内 `recovered-side03.blend` 是披露过的重建版，不能冒充原母版。

## 最新成果与未完成项

fore-root11 新增 38 个实体网格：三段厚装甲、跨缝共同支座、贯穿装甲检查开口、真实底盘、底座、吊耳、销轴与保持件。旧 6 个遮挡对象移入隐藏 `FORE11_PREVIOUS`，不是删除历史。47 处声明接合；100 个前肩设备、342 个舰桥样板、18 个灯具保持。源检查、GLB 回读和光照适配器检查见冻结证据与本轮复核记录。

这不是机械 CAD 或全舰碰撞认证。漆面、合理磨损、根部区域烘焙、接缝视觉、太空光可读性、全舰结构一致性仍待完成。原太空光下根部偏暗；中性光能验证结构，不能替代正式环境可读性验收。真实浏览器阴影/交互、触控、移动性能与资源释放均未验收。`browser_tested=false`、`published=false`。

最新主舰 GLB：5,029,972 字节，238,480 三角面，45 个材质批次。批次不等于 draw calls；9 张纹理原先约 80 MiB 的 RGBA8+mipmap 粗估仍需优化，无运行时 LOD/纹理压缩完成声明。

## 取得资源与主入口

完整制作包沿用现有持久任务包规则（见历史 `docs/kuhai/assets/*-delivery.json`）；不把 131 MB ZIP 推进普通 Git，不引入 LFS、Release 或新存储权限。

在 ChatGPT 文件中找到 **kuhai-side-finish-04.zip**，必须下载 **版本 7 / fore-root-11**。该文件沿用旧名称并被多次更新，文件名不能证明版本。持久文件标识 `libfile_2603ebe18aa0819190ab432551cbd521`，第 7 版，131,330,853 字节，SHA256：

`e3e9eeebf9661f2ffbc44ba952bebd2c3aa51832301a0672d796bccaaaba0e69`

如后续版本改变，通过版本历史取得第 7 版并校验；不能用最新同名文件代替冻结版。没有持久公开下载 URL，本地 Codex 无法凭标识直接访问 ChatGPT 文件，需用户先下载到本地。sandbox 路径只是本轮可下载入口，不是永久交付地址。

解压后的根目录为 `kuhai-fore-root-11/`：

| 路径 | 用途 |
| --- | --- |
| `scenes/flagship-fore-root-11.blend` | **可编辑母版／首选打开入口** |
| `scenes/textures/` | 母版相对路径纹理；同时检查打包图像 |
| `web-source/flagship-fore-root-11-web.blend` | 轻量网页派生源；不能当母版继续高精度制作 |
| `web-source/textures/` | 网页派生源 9 张贴图 |
| `web-assets/` | flagship、archive、灯光 GLB、灯光配置与适配器 |
| `inputs/`、`bridge-baked/`、`fore-baked/` | 不可变前版、恢复基线与烘焙依赖 |
| `tools/flagship/`、`tools/fore09/` | 全链生成、检查、渲染、导出脚本及源印刷图 |
| `evidence/`、`previews/` | 原验证记录与同机位对照；不是 WebGL 截图 |
| `MANIFEST.json`、`SOURCE-LICENSE.txt`、`textures/ATTRIBUTION.md` | 逐文件大小/SHA256与许可 |

母版 SHA256 `a1dd93fddd59a605ad4d7c2788d218542874a8386b0cf0e9bbb27f9454654970`。完整逐文件索引在 Git 的 `docs/kuhai/assets/fore-root-11-manifest.json`。Git 的 `tools/flagship/frozen/fore-root-11/` 保存包内文本工具和证据快照；避免覆写历史 `tools/flagship/`。PNG、GLB、blend、历史输入在完整包中，不需从 Git 拼凑。

## 环境与 Windows 命令

已用环境：Linux / Python 3.11.17 / bpy 4.5.14 LTS，Blender build `62c1db4208e8`，numpy 1.26.4。渲染为 CPU、6 线程、960×600、32 samples。Pillow 12.3.0 仅用于拼图；锁定文件位于包内 `tools/flagship/requirements-*.txt`。桌面 Blender 自带 bpy，通常不需要 pip 安装。Windows 桌面 Blender 和本地 GPU 复现尚未实测；先核对版本，不自动改驱动或安装依赖。

PowerShell，先把 ZIP 放到 `C:\kuhai\`（可自行选择路径）：

```powershell
$package = 'C:\kuhai\kuhai-side-finish-04.zip'
if ((Get-FileHash $package -Algorithm SHA256).Hash.ToLower() -ne 'e3e9eeebf9661f2ffbc44ba952bebd2c3aa51832301a0672d796bccaaaba0e69') { throw '冻结包校验失败' }
Expand-Archive -LiteralPath $package -DestinationPath 'C:\kuhai\frozen11'
Set-Location 'C:\kuhai\frozen11\kuhai-fore-root-11'
$blender = 'C:\Program Files\Blender Foundation\Blender 4.5\blender.exe'
& $blender --version
& $blender 'scenes/flagship-fore-root-11.blend'
```

打开后核对缺失纹理，`FORE11_STRUCTURE` 可见、`FORE11_PREVIOUS` 隐藏、`FORE11_CUTTERS` 与 `FORE08_CUTTERS` 保持链接；不要同时显示新旧覆盖层。另存工作版，绝不覆盖 inputs。以下 Python 脚本需要参数被完整传入 argparse，建议使用已锁定的 Python+bpy 路线（桌面 Blender `--python` 的 argv 带 Blender 自身参数，不能直接照搬）。

```powershell
# 使用 Python 3.11，并在独立虚拟环境中安装包内 requirements-cloud.txt 后
$py = 'C:\kuhai\bpy45\Scripts\python.exe'
& $py tools/flagship/fore_root_check.py --baseline inputs/fore-lighting-10.blend --input-validation evidence/input-fore10-check.json --scene scenes/flagship-fore-root-11.blend --output reproduce/check.json
& $py tools/flagship/fore_root_render.py --scene scenes/flagship-fore-root-11.blend --validation reproduce/check.json --output reproduce/neutral --neutral --views root11_detail,root11_reverse,root11_joint
& $py tools/flagship/export_fore_root.py --source scenes/flagship-fore-root-11.blend --validation reproduce/check.json --web-source inputs/fore10-web-source/flagship-fore-lighting-10-web.blend --previous-assets inputs/fore10-web-assets --derivative reproduce/web-source/flagship-fore-root-11-web.blend --output reproduce/web-assets
& $py tools/flagship/fore_root_web_check.py --source scenes/flagship-fore-root-11.blend --validation reproduce/check.json --assets reproduce/web-assets --output reproduce/web-geometry.json
& $py tools/flagship/inspect_fore_lights.py --assets reproduce/web-assets --output reproduce/web-lights.json
```

需要从 fore10 重建时执行包 README 的 `fore_root.py` 命令，输出使用新目录。重新保存 blend 的容器 SHA 可能改变，应重新绑定检查记录，不以旧哈希证明新文件。生成文件不默认提交 Git。

独立审阅网页仍参考仓库 `tools/flagship/review/README.md`（Node 22.12+、pnpm.cmd）。新版包含六灯适配器且原网页未接入，需本地 Codex 先审查灯光配置、比例、分层和加载契约，再更新独立本地审阅页面；不能只复制 flagship.glb。博客、私有审阅站保持隔离，直接访问文章不应下载模型。

## 接手顺序与验收门槛

1. 校验 ZIP 和 MANIFEST，在新目录打开母版；复核纹理、隐藏集合和旧版来源。
2. 重跑结构检查和实际 GLB 解码，确认声明接合、旧设备视线、开口和灯具不退化。检查所有覆盖层，管线有起终点；新增部件先证明安装和可见性。
3. 固定机位对比中性光与太空光、远中近景和正反向；之后由本地 Codex 做区域材质/照明及下一处结构深化，每轮一个明确目标。
4. 独立本地网页接入后再做浏览器：1440×900、390×844，hover 前后相机矩阵不变、拖拽不误进入、双指不误触、返回恢复、键盘、减少动效、失败回退。
5. 核显/独显/手机至少五分钟实测；记录配置、冷暖加载、帧耗时中位数/高分位、draw calls、内存与释放。60/30 FPS 与 10 MiB 是预算目标，尚未达成。

现有 `development-plan.md` 继续作为最终目标。其“云端继续制作”和“最近一轮”是旧阶段安排，本交接覆盖当前执行分工：复杂建模由本地 Codex 接手；本轮收尾不继续制作。发布需另外授权和整体验收，不因 draft PR 创建而部署或自动合并。

## 给本地 Codex 的接手提示词

> 接手 kuhai 主舰入口制作，先读仓库 AGENTS.md、docs/kuhai/flagship/local-codex-handoff-2026-10-13.md、development-plan.md 和 fore-root-11 冻结证据。用户提供的完整 ZIP 第7版是最新真实资产，母版 scenes/flagship-fore-root-11.blend；先核对校验值、依赖和可见集合，再报告你能复现的结果。保留原博客与 PR1，不自动合并、不部署、不修改网络或客户端、不复制密钥。旧 study03 母版未恢复，recovered-side03 是已披露重建。先复核结构和 GLB，再以明确小范围推进材质/太空光可读性和下一处结构；保持中性/气氛光与固定机位对照，杜绝悬空管线和覆盖遮挡。不要宣称源渲染等于真实浏览器验收。建模后更新源、脚本、校验索引、检查与交接，独立分支提交。先核实本机 Blender 4.5 LTS、Python/bpy和GPU，再决定渲染；Windows 命令用 pnpm.cmd/npx.cmd。当前新版网页六灯适配器尚未接入，先审查接口再更新本地独立审阅站，直接博客不得加载模型。首轮先完成复现和一个可验收改进，避免一次铺开全舰。

## 本轮验证记录

见 `validation/closeout-2026-10-13.json` 和同目录复核 JSON。所有源文件来自 ZIP 的实际字节，229 个索引项逐个大小/SHA256匹配，ZIP CRC通过。脚本快照通过 Python AST 解析，未提交二进制、密钥、缓存、临时目录或网站改动。真实浏览器、Windows、本地GPU仍未验证。
