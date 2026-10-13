# kuhai — fore-root-11

本轮深化左前肩根部。可编辑主文件是 `scenes/flagship-fore-root-11.blend`。这是局部结构样板：三段厚装甲、共同支座、真实检查开口和销轴连接件。表面沿用当前舰体色系；全舰造型、这一新区域的最终材质、网页与手机验收仍未完成。

## 实际改动

原根部装甲岛与覆盖其上的五块 SURFACE03 薄装甲片，共六个旧对象，完整移入隐藏的 `FORE11_PREVIOUS` 对照集合。原始网格、材质、相机和灯光保留。没有删去旧对象来掩盖交接缺口。

新增 `FORE11_STRUCTURE` 共 38 个实体网格：

- 三段大面积装甲保持原根部轮廓和原炮座的支承面，接缝落在共同支座上，接缝下可以看到支承层。
- 中段装甲具有贯穿自身厚度的检查开口，底部坐落在现有前肩壳体上。开口有真实壁厚、底盘、压边和两条底盘加强筋。
- 两端各有固定底座、成对吊耳、横向销轴与保持件，中间连接件由销轴捕获。连接件与吊耳之间保留可见间隙，各个底座与固定件都有明确落点。
- 锁扣集中在装甲接缝与底座附近。没有增加新流体或电气线路，没有给空白区域铺满螺丝、亮条或小方块。

当前静态模型在声明的连接处采用实体接触/嵌合表达。它不是可制造的机械 CAD：没有进行销轴配合公差、轴承、应力、疲劳或真实飞行结构认证。内部结构是项目原创解释，不是官方休伯利安复原声明。

## 基线和保留内容

- 不可变输入：`inputs/fore-lighting-10.blend`，SHA-256 `993d1dfada15902cc4d5d208986fbc0756a9463d771919bcd487deddfae867b2`。
- 本轮主文件：`a1dd93fddd59a605ad4d7c2788d218542874a8386b0cf0e9bbb27f9454654970`。
- 配置 `tools/flagship/fore-root-11.json`：`0e4da9afafd90a68daaab3bf37efc602420d8d4c28fb8e0d792610f34e0bc179`。
- FORE09 的 100 个前肩设备槽对象、SIDE06 的 342 个舰桥样板对象、FORE10 的 18 个灯具对象保持评估几何与法线；前肩连接声明、灯具元数据及已有灯光保持。
- 旧相机、档案室、全局太空光、曝光和背景保持；新增两台根部检查相机。`root11_joint` 近景相机由预览脚本临时创建，不修改母版，参数随预览记录保存。
- `FORE11_CUTTERS` 保存分段和开口工具，必须保持链接。网页副本同样保留它和旧 `FORE08_CUTTERS`，避免导出后开口被封住。

关闭 `FORE11_STRUCTURE`、显示 `FORE11_PREVIOUS` 可观察前一版。不要同时打开旧件和新件。历史集合、源材质及其他舱室不属于本轮替换范围。

旧 side03 原始母版的历史字节依然没有取回；包内 `inputs/recovered-side03.blend` 沿用已披露的恢复版本，不冒充原 side03 文件。home-look-01 等不可变输入继续保留，历史条件见 `evidence/recovery-provenance.json`。

## 检查及返工预防

`evidence/check-c.json` 将本轮源文件、配置和 fore10 输入证明绑定到精确 SHA。18 项检查覆盖历史内容保留、38 个新网格的封闭体积、47 处声明接触、所有新件通向舰体的连接关系、与旧几何的功能件间隙、吊耳间隙、销轴对齐、接缝下方支座、炮座支承面、图片打包和可见性。

- 既有舰桥与前肩设备的 22 组固定观察面，共 2,662 条视线，深度保持。
- 新连接件在正反两机位均为 85/85 抽样点可见；槽底为 9/10 和 10/10。厚装甲口沿在斜视时仍会产生正常遮挡，这不等于保证任意角度都能看见槽底。
- 第一版被检查拒绝：五块旧薄装甲片挡住开口，并与新锁扣相交。现已明确纳入替换集合并保留对照；接触、遮挡和缝隙阈值没有放宽。初始反向机位过低，之后抬高检查机位以观察底座。记录见 `evidence/overlay-regression.json`。
- 炮座下方的原圆周抽样深度保持。前段装甲先复制原评估几何，再分段，避免重新倒角改变已有支承边缘。

这些检查针对已声明的连接与观察范围，不是全舰碰撞或机械认证。后续改变孔洞、盖板、连接、可见性或观察范围，应重新运行对应检查；不能只沿用旧版“通过”。

## 图像和网页资产

所有交付图片均来自实际 Blender 模型的 CPU 渲染，960×600、32 samples、6 线程。比较图只排版和缩放，没有图像生成或涂改结构。相同机位下比较修改前后，提供中性光正反视角、连接近景、太空光近中远景和 GLB 回读核对。各图来源、相机和成本记录位于 `previews/`。

现有太空光下，根部大部分仍落在舰桥投影里，内部连接件在中景的可读性有限。本轮没有为此改变全局灯光或给新开口增加发光条；中性光用于审阅结构，统一环境补光和区域材质仍是后续工作。

`web-source/` 在已核验的 fore10 网页副本上加入本轮结构，`web-assets/` 包含主舰、档案室、六灯附件与已有灯光适配器。

- 九张已烘焙的舰桥/设备槽贴图逐字节保留。档案室 GLB、六灯 GLB 和灯光适配器逐字节保留；灯光配置中的模型绑定更新为新主舰哈希。
- 新结构使用现有色系的基础 PBR 近似，尚未完成区域纹理烘焙。整体原有的清漆近似、缺少烘焙 AO、缺少运行时 LOD/纹理压缩等边界保持；不是全舰材质完成声明。
- 实际 Draco 解码后的模型，与母版比较 748 条视线：覆盖既有设备槽、新连接件、槽底和四处装甲接缝。独立核对实际贴图字节、法线、材质批次、六灯位置与方向。精确资源数据见 `web-assets/model-manifest.json` 和 `evidence/web-*.json`。
- 当前主舰 GLB 为 5,029,972 字节、238,480 三角面、45 个材质批次，较 fore10 增加 53,172 字节、4,519 三角面和 4 个批次。748 条视线的最大位置差约 0.0000484 源场景米；这不代替浏览器验收。
- `previews/web-decoded/root11_detail.png` 是实际主舰与灯光 GLB 回读到 Blender 后的 CPU 图。glTF punctual lights 不保留离线灯的面积半径，阴影会有差异；该图不代表 WebGL 截图。
- `browser_tested=false`，`published=false`。真实网页光照、触控、资源释放和手机 FPS/内存仍未验收。九张纹理原先约 80 MiB 的 RGBA8+mipmap 粗估占用没有因此消失；材质批次不等于浏览器 draw calls。

未安装新依赖、未启用家中 GPU、未租用付费资源；未发布或覆盖审阅站、未改变原双语博客、未推送或合并 GitHub。

## 复现入口

在已配置的 Blender 4.5.14 bpy 环境执行，`PYTHON_BPY` 指向该解释器。输出必须使用新目录；不得覆盖 `inputs/`。新保存的 .blend 可能有不同容器字节，应重新验证并绑定新 SHA。

```bash
"$PYTHON_BPY" tools/flagship/fore_root.py --source inputs/fore-lighting-10.blend --validation evidence/input-fore10-check.json --output reproduce/scenes/flagship-fore-root-11.blend
"$PYTHON_BPY" tools/flagship/fore_root_check.py --baseline inputs/fore-lighting-10.blend --input-validation evidence/input-fore10-check.json --scene reproduce/scenes/flagship-fore-root-11.blend --output reproduce/check.json
"$PYTHON_BPY" tools/flagship/fore_root_render.py --scene reproduce/scenes/flagship-fore-root-11.blend --validation reproduce/check.json --output reproduce/neutral --neutral --views root11_detail,root11_reverse,root11_joint
"$PYTHON_BPY" tools/flagship/export_fore_root.py --source reproduce/scenes/flagship-fore-root-11.blend --validation reproduce/check.json --web-source inputs/fore10-web-source/flagship-fore-lighting-10-web.blend --previous-assets inputs/fore10-web-assets --derivative reproduce/web-source/flagship-fore-root-11-web.blend --output reproduce/web-assets
"$PYTHON_BPY" tools/flagship/fore_root_web_check.py --source reproduce/scenes/flagship-fore-root-11.blend --validation reproduce/check.json --assets reproduce/web-assets --output reproduce/web-geometry.json
"$PYTHON_BPY" tools/flagship/inspect_fore_lights.py --assets reproduce/web-assets --output reproduce/web-lights.json
```

继续完善时，先核对相邻区域的所有旧覆盖层和真实装配关系，再扩展舰首外缘与前肩腹部的过渡。该新区域的涂层、合理磨损和标记仍可深化；不以加暗、强辉光或新碎件代替结构。
