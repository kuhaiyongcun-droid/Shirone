# 个人博客中文化与部署

原项目有 10 个语言字典，但语言由 `siteConfig.lang` 在构建时决定。本 fork 默认使用简体中文，并在顶栏加入中文 / English 切换。

- `/`：中文界面。
- `/en/`：英文界面。
- 切换保留当前页面、查询条件和锚点，并完整加载对应语言的界面与交互组件。
- 正文、文章标题、分类名等内容保持原始语言；界面切换不会自动翻译文章。
- 翻译文件位于 `src/i18n/languages/`，新增界面文案要在全部 10 个字典注册。

## 本地开发

```sh
pnpm install --frozen-lockfile
pnpm dev
```

默认开发中文界面。英文开发可设置 `PUBLIC_SHIRONE_LOCALE=en` 和 `PUBLIC_SHIRONE_BASE=/en/` 后运行 `pnpm dev`。

## 构建和预览

```sh
pnpm check
node --test tests/language-switch.test.mjs
pnpm check:manifest
pnpm type-check
pnpm build
pnpm preview
```

`pnpm build` 在两个独立进程中构建中文与英文，分别生成全文搜索索引并检查字体，然后合并到 `dist/`。它也会检查全部语言字典的键与占位符、每个语言页面的切换地址，以及生成资源是否存在。

`pnpm build:single` 保留上游单语言构建。只部署单语言时，先把 `siteConfig.languageSwitch` 设为 `false`，避免显示没有对应构建页面的入口。

## 修改自己的站点

- 核心设置：`src/config/siteConfig.ts`（站点域名、标题、简介、横幅、默认语言）。
- 作者资料：`src/config/profileConfig.ts`（头像、名称、简介、社交链接）。
- 导航：`src/config/navBarConfig.ts`。
- 文章：`src/content/posts/`。
- 页面示例数据：`src/data/`。

当前 `site` 指向 ChatGPT Sites 地址。迁移到自己的域名时更新它，再重新执行 `pnpm build`。托管输出目录为 `dist`。

GitHub 是这个个人博客 fork 的代码仓；ChatGPT Sites 发布相同源代码的快照。单独推送 GitHub 不会自动更新 ChatGPT Sites，后续修改后需要重新发布站点。
