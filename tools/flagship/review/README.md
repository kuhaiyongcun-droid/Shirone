# kuhai 主舰交互审阅 02

基于 `home-look-01` 的独立审阅页面。Shirone 仍是档案室的博客框架，本目录没有接入博客路由、改变博客页面或复制文章。

## 使用

- 拖动绕舰旋转，滚轮或双指缩放；没有自动旋转、惯性或鼠标跟随。
- 鼠标停在实际档案室外壳或光点上，加载内部后隐藏局部外壳、显示轮廓和内部。舰体及相机不因悬停移动。
- 鼠标点击该区域直接进入。触屏和键盘先选择，再激活进入；底部档案室入口先定位，再进入。
- 舱内仅为 3D 空间审阅，返回主舰恢复先前视角；没有跨舱导航。`#archive` 支持直接访问，浏览器前进后退可恢复所在空间。
- 设置提供自动、标准、轻量和静态模式。轻量降低像素预算、关闭阴影及抗锯齿，当前没有几何 LOD。节省流量偏好默认静态；WebGL/模型加载失败使用静态图。
- 中英文切换保留房间、选择状态和相机。聚焦场景后方向键旋转，`+` / `-` 缩放；Esc 收起设置、取消选择或返回。

## 构建和数据检查

需要 Node 22.12+、pnpm。代码和资产清单在 GitHub；模型上传 GitHub 时工具审批返回「调用被拒绝」，因此本轮不将生成的模型和预览图提交到仓库，也未更换上传方式重试。

先登录自己的私有审阅站点，下载 [review-assets.zip](https://kuhai-flagship-review.kuhaiyongcun.chatgpt.site/review-assets.zip)，解压后把 `assets/` 的内容放入本目录 `public/assets/`，保留同名文件。校验值见 `model-manifest.json`。使用这些资源不需要 Blender 或独立显卡；也可以按后文用已有 `.blend` 源包重新导出模型。

```sh
cd tools/flagship/review
pnpm install --frozen-lockfile
pnpm test
pnpm build
```

Windows 使用 `pnpm.cmd`。输出 `dist/`，应通过 HTTP 静态服务打开，不能用 `file://` 加载模型。Three.js、Draco 解码器、模型和字体回退均在本地资源范围内，不请求 CDN。制作代码、依赖和网页资产单独放在本目录，不进入 Shirone 的默认包依赖或博客入口。

构建时从仓库的 `src/i18n/i18nKey.ts`、十种语言注册表和 `i18n()` 生成中英文子集。不能仅移动本目录的源码来重建；需要完整仓库。已构建 `dist/` 可单独迁移。

## 从制作源模型重新导出

制作源保存在既有 `kuhai-flagship-home-look-01.zip`，SHA256 和获取记录见 `docs/kuhai/assets/home-look-01-delivery.json`。本轮不修改源 `.blend`。

在仓库根目录，使用已安装 `bpy==4.5.14` 的 Python 环境：

```sh
python tools/flagship/export_review.py --source /path/to/scenes/flagship-home-look-01.blend --output tools/flagship/review/public/assets
python tools/flagship/inspect_review.py --assets tools/flagship/review/public/assets --output decoder-check.json --decoded /path/to/temporary-decoded
node tools/flagship/review/tests/raycast-check.mjs /path/to/temporary-decoded
```

源指纹不符会停止导出。按可见集合递归提取舰体、装甲板层、舰桥、推进段、档案室外壳和内部，排除隐藏历史几何，尊重 HOME01 对象级材质覆盖；在内存中把倒角改为一段、合并顶点与材质批次、移除数值小面、压缩几何。保留自定义拐角法线，按实际压缩后的面数记录指标。单位为 100 米源尺度对应一个网页单位；网页 Y 向上、舰首 -X、左舷 +Z。`inspect_review.py` 的回读边界使用 Blender 的 Z 向上坐标。

## 资产与质量边界

`public/assets/model-manifest.json` 记录模型版本、文件大小、面数和校验值。网页主舰 159,603 三角面、31 批次、1,286,648 字节；档案室延迟加载 10,107 三角面、9 批次、132,040 字节。轮廓线、星体和阴影另有绘制开销，不能把批次直接当浏览器总 draw calls。

当前使用简化 PBR，尚未烘焙制作源的漆面/粗糙度节点。星体、云层和大气为轻量程序化近似，沿用源场景恒星方向；星体距离压缩只服务画面和深度精度，不作为真实轨道模拟。当前整舰静态预览来自 home-look-01 的 CPU 渲染，档案室静态预览沿用此前渲染；它们不是浏览器截图；其中粗糙度纹理的 CC0 来源沿用该阶段登记。

Three.js 为 MIT；Draco 为 Apache-2.0。构建复制各自许可文件。字体使用系统回退，不加载外部字体。

## 验证边界

Node 手势与像素预算测试、Khronos glTF 校验、Blender 实际解码、法线检查、桌面/窄屏投影与射线遮挡计算已运行。真实浏览器 WebGL 着色、鼠标/触控事件顺序、可访问性扫描及帧率尚未验收。本环境的 Sites 流程缺少指定浏览器工具，因此没有绕过限制启动服务器或浏览器。

待在可用浏览器中检查：1440×900、390×844；拖动跨舱区和双指抬起不能进入；悬停前后相机与舰体矩阵不变；返回精确恢复视角；中英文和前进后退；失败/静态模式；键盘焦点和减少动效；离开页面释放资源。测试设备分别记录 GPU、分辨率、加载量、实际 draw calls、帧时和内存，之后再定 LOD 和最终纹理预算。

## 本轮更新

纳入舰桥 01/02、舰尾 01、装甲分区 03 和首页漆面 01 的制作结果。主光与星球共享新的逆光方向，采用 AgX；材质仍为未经全舰烘焙的轻量近似。起始视角按当前画幅和舰体包围盒求解，保留顶部和底部界面空间，避免只用包围球导致主舰显示过小。前述检查已用当前导出重跑，浏览器验证边界仍不变。
