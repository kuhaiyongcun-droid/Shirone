# 主舰／档案室

kuhai 的个人网站源码：主舰提供按需开启的三维入口，档案室连接独立构建的 Shirone 博客。站点配置位于 `site.json`，公开站点为 [kuhaiyongcun.com](https://kuhaiyongcun.com)。GitHub 分支内容与线上部署版本分别管理，推送本分支不会自动更新网站。

当前源码对应 `3d-loading-20261028-v2`：修复慢速模型下载被固定 30 秒超时中断的问题，增加真实下载进度、取消和重试，保留失败后的文章入口。新版静态包已在本地构建，服务器尚未更新。更新操作见 [本次发布说明](发布更新-三维加载修复-20261028.txt)，公开核验结果见 [验证记录](验证记录-三维加载修复-20261028.json)。

本轮单元检查 83 项通过、1 项历史备案基线按条件跳过；Astro 检查 283 个文件，0 错误、0 警告。受控限速下，主舰下载 67.167 秒、内舱下载 22.870 秒后均进入真实 WebGL 场景；桌面取消、重试、文章导航、503 恢复与焦点，以及 390×844 视口的真实触摸事件检查通过。这些结果属于本地无头 Firefox 和触控模拟，尚不替代新版公网部署及实体手机验收。

## 来源和分支

本分支从当前 fork 的真实提交 `998c68d85b21e86e7cbfa05ec170fc1ac1d298e0` 延续，保留 [Shirone 上游](https://github.com/LyraVoid/Shirone) 的祖先历史。完整博客主题放入 `blog/`，并与当前主舰、内容及发布工具组成同一工作区。

本次同步不合并既有 PR1/PR2，也不表示恢复了缺失的历史提交 `6f8ad2b`。较早的部分网页源码没有被用于覆盖完整博客。

## 目录

| 路径 | 用途 |
| --- | --- |
| `blog/` | 完整 Shirone 博客源码、测试、主题文档与许可证 |
| `ship/` | 独立主舰网页源码、相机与加载逻辑、固定网页资源 |
| `content/` | 公开文章、图片、配置；正文入口为 `content/content/posts/` |
| `authoring/` | 写作指南和模板 |
| `scripts/` | 写作预览、配置、核验、构建与本地发布打包工具 |
| `deployment/` | 静态服务器配置模板、部署及回滚说明 |
| `release-plan/` | 固定资源和构建输入的校验计划 |
| `site.json` | 站名、域名、作者、博客路径和备案展示配置 |

`blog/src/content/` 等目录由公开内容同步生成，日常写作请编辑 `content/`。未发布私稿由写作工具保存到被 Git 忽略的 `authoring-private/`，本地草稿预览在 `preview-work/`；二者不属于公开源码。

## 本地使用

需要 Python 3.12 或更新版本、Node.js 22.12 或更新版本，以及与各自锁文件匹配的 pnpm 依赖。博客声明 pnpm 11.28.2，主舰声明 pnpm 11.25.0。当前修复工作使用已有 Node.js 24.22.1、pnpm 11.25.0；版本差异应保留在核验记录中。此仓库不包含 Node/Python 运行时或 `node_modules`，也没有替用户执行安装。

源码克隆后仍需安装锁定依赖，并通过 PATH、环境变量或本机配置提供实际工具链；仓库根目录不是可直接部署的静态目录。先运行 `python scripts/runtime_paths.py` 检查已有工具。需要指定本机路径时，根据 `toolchain-local.example.json` 建立被 Git 忽略的 `toolchain-local.json`，其中只保存工具路径。

确认允许获取依赖后，可分别执行以下显式安装命令；它们使用已有锁文件并禁用安装脚本：

```text
python scripts/run-pnpm.py install
python scripts/run-pnpm.py install --project ship
```

安装与系统差异的详细说明见 [开发与发布说明](开发与发布说明-v2.txt)。常规检查和发布命令不会联网安装依赖。

首次克隆还需创建 Git 不保存的空目录，并按下面顺序初始化；每一步成功后再执行下一步：

```text
python -c "from pathlib import Path; [Path(p).mkdir(parents=True, exist_ok=True) for p in ('evidence', 'delivery-packages', 'blog/public/assets')]"
python scripts/run-pnpm.py configure
python scripts/run-pnpm.py content-validate
python scripts/run-pnpm.py content-sync
python scripts/run-pnpm.py build
```

首次 `build` 会在 Vite 的 `buildStart` 阶段生成 `blog/src/generated/local-icon-collections.ts`，然后才处理组件对它的导入；字体子集也在构建中从原始字体生成。这些生成物不提交到 Git。**第一次不能跳过上述初始化，直接运行 `check` 或 `release.py`**：Astro 的 `check` 不执行 Vite `buildStart`，而发布流程会先检查再构建。首次构建成功后，日常使用下面的发布命令即可。

准备公开的文章写在 `content/content/posts/`；新增私稿、插图与本地预览的操作见 [写作指南](authoring/写作指南.txt)。确认文章可以公开后，再显式执行写作工具的 `prepare-publish` 步骤。

在仓库根目录使用全新的版本名生成本地发布包：

```text
python scripts/release.py --version my-release-01 --check-only
python scripts/release.py --version my-release-01 --mode shared
```

检查通过后，第二条命令重新构建主舰与博客并打包。已有版本目录不会被覆盖。输出位置、文件哈希、检查结果以命令生成的报告为准；打包不等于服务器上线或真实手机验收。服务器仅使用新部署包的 `dist/` 内容作为站点根目录，具体切换及回滚见 [部署与更新说明](deployment/部署与更新说明.txt)。

## 三维资源范围

当前网页资源固定在 P26–P27，模型源母版标识为 `dd35a7b43c94ba22a03aa0f27e0b88de549cce594971829c9e0e6913e04d0339`。入口默认展示静态海报，用户开启三维后才加载相应资源。

`ship/public-p26p27-final-20261022-r1/` 保存网页所需 GLB、相机、灯光、参考图片和校验证据。RESERVED 区域保持封闭，其余规划舱室尚未装舰；当前室内浏览是有限机位和受约束的相机操作，不是全舰自由行走系统。

`ship/dist-p26p27-final-20261022-r1/` 是发布工具要求保留的冻结校验基线，**不能当作当前版本直接上线**。它用来核对固定资产与历史构建输入；当前源码修复必须经重新构建生成新发布包。快照证据中的少量历史源路径属于哈希校验记录，不用作本机运行路径。

`.gitattributes` 为本次源码快照禁用 Git 的文本换行转换，保证固定资产、部署文件和许可证等按原始字节通过 SHA256 校验。不要对这些校验输入做批量换行规范化后沿用旧清单。

完整 Blender 母版、历史制作包、模型生成过程、离线依赖包及旧预览仍由本地单独备份，未纳入此 Git 分支。克隆仓库能取得网站维护源码和固定网页资源，不等于取得全部三维制作工程。

## 许可与第三方来源

Shirone 的 MIT 许可证和原作者版权保留在根目录 [LICENSE](LICENSE) 及 [blog/LICENSE](blog/LICENSE)：Copyright © 2024 saicaca、© 2026 matsuzaka-yuki。主题文档、上游来源与署名继续保留。

Three.js、Draco、Outfit、JetBrains Mono 及 Yozai 的原许可证随相应文件保存，Yozai 许可证见 [Yozai-OFL.txt](Yozai-OFL.txt)。已采用的 Poly Haven 粗糙度贴图来源和参考资料范围记录在 [素材登记表](blog/docs/kuhai/assets/registry.csv)。代码的 MIT 许可证不应被当作所有第三方图像、字体或参考素材的统一许可。

主题原工作流保留在 `blog/.github/`；此分支没有新增仓库根部署工作流。开发和维护时请继续遵守 `blog/AGENTS.md` 中适用的主题规则。
