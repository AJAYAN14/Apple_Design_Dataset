---
trigger: always_on
---

# Apple Design System 逆向工程项目简报 (Project Brief)

## 项目目标

通过对 iOS 原生系统应用（设置、健康、备忘录、天气、播客、App Store 等 Apple 第一方 App）的真实界面截图进行**逆向工程**，提取出像素级精确的 Design Tokens（设计变量），最终汇聚为一套完整、工业级的 **Apple Design System 规范数据库**。

## 为什么要做这个项目

Apple 官方的 HIG（Human Interface Guidelines）偏概念与原则，缺少具体的像素级实现参数。通过真实原生 App 截图逆向，能精准捕获官方文档里没有明说的**实际像素规律、间距节奏、色彩层级与材质细节**——这些正是复刻出"果味"界面的命门。

## 核心方法论

采用 **"代码测硬数据 + AI 归纳软语义"** 的组合拳：

1. **Python 脚本**（`.agents/skills/apple-screenshot-token-pipeline/measure_helper.py`）充当"数字游标卡尺与吸色管"，提供客观的物理测量数据（精确色值、边距像素、间距像素），消除 AI 在数值上的估算幻觉。
2. **多模态 AI** 负责语义理解与体系构建：识别界面结构类型、判定排版层级、梳理设计哲学、映射 SF Pro 字阶体系。
3. 每次分析一对**深浅模式截图**（Light / Dark），利用同一界面的深浅对比来：
   - 交叉校验几何参数（间距、圆角在深浅模式下必须数学恒等）
   - 精准捕获 Apple 的"动态语义色彩系统"与"表面层级（Elevation）"映射关系

## 关键约束

- **只截取 Apple 第一方系统应用**，不截第三方 App，避免混入非标准设计。
- 默认设备为 iPhone @3x 分辨率（所有像素值除以 3 换算为 iOS 标准 pt 点数）。
- 脚本只做最不会出错的物理测量（取色、量边距），**不做语义识别**——语义由 AI 完成。

## 工具链

| 工具 / 资源 | 路径 | 用途 |
|---|---|---|
| **专用 Skill** | [`.agents/skills/apple-screenshot-token-pipeline/SKILL.md`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/SKILL.md) | Agent 逆向工程流水线专有技能定义与操作手册 |
| **测量辅助脚本** | [`.agents/skills/apple-screenshot-token-pipeline/measure_helper.py`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/measure_helper.py) | 本地 Python 脚本，提取物理精确色值与间距，输出 `raw_measurements.json` |
| **合规校验脚本** | [`.agents/skills/apple-screenshot-token-pipeline/validate_pair.py`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/validate_pair.py) | 本地 Python 脚本，自动化校验 Tokens 与 Layout 语法、类型纪律、深浅对称性与真值一致性 |
| **导出辅助脚本** | [`.agents/skills/apple-screenshot-token-pipeline/export_blueprint.py`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/export_blueprint.py) | 本地 Python 脚本，将结构化 Layout JSON 一键渲染为 Markdown 蓝图或提取 Compose/SwiftUI 代码 |
| **Token 数据契约** | [`.agents/skills/apple-screenshot-token-pipeline/design_token_schema.json`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/design_token_schema.json) | 统一规范 `light.json` 与 `dark.json` 的字段与结构定义 |
| **Layout 蓝图契约** | [`.agents/skills/apple-screenshot-token-pipeline/layout_schema.json`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/layout_schema.json) | 统一规范 `{folder}_layout.json` 的组件树、线框图、约束与代码骨架定义 |
| **多模态 AI Agent** | 工作区执行核心 | 结合脚本测量数据 + 视觉分析，逆向提取完整 Tokens 与 Layout 架构 |

### `measure_helper.py` 能力范围

- ✅ 精确色彩采样：背景底色 Hex、候选卡片表面色 Hex、动态透明度微光特征
- ✅ 水平外边距测量：屏幕边缘到内容边界的像素距离（→ pt / dp）
- ✅ 卡片垂直间距测量：相邻内容区块间的留白高度（→ pt / dp）
- ✅ 双轨圆角与连续曲率拟合：
  - 传统正圆标称半径拟合（工程落地直接赋参）
  - 基于 SciPy 的超椭圆连续曲率反推（求解形状指数 $n$、闭式数学方程、Figma 平滑度）
  - 低对比度微光卡片抗锯齿收缩补偿建议
- ✅ 跨设备倍率自适应：自动适配 iPhone 经典倍率 (@2x/@3x) 及 Android/HyperOS 浮点高密度倍率 (@2.625x/@3.5x)
- ❌ 不做：语义组件分类、设计规范文字撰写（由 AI 完成）

## 目录结构（每组标准 6 件套产出物）

```
Apple_Design_Dataset/
├── .agents/
│   ├── rules/
│   │   ├── project-brief.md        ← 本文件（项目简报）
│   │   └── rules.md                ← 逆向工程执行规则
│   └── skills/
│       └── apple-screenshot-token-pipeline/
│           ├── measure_helper.py           ← 测量辅助脚本
│           ├── validate_pair.py            ← 合规校验脚本
│           ├── export_blueprint.py         ← 蓝图渲染与代码提取脚本
│           ├── design_token_schema.json    ← Design Token 结构规范
│           └── layout_schema.json          ← Layout 架构蓝图结构规范
├── 01_Settings_RootList/           ← 子文件夹：编号_App名_视图名
│   ├── 01_Settings_RootList_light.png   ← 浅色模式截图 (支持 png/jpg/jpeg/webp)
│   ├── 01_Settings_RootList_dark.png    ← 深色模式截图 (支持 png/jpg/jpeg/webp)
│   ├── raw_measurements.json            ← 脚本输出的测量数据
│   ├── 01_Settings_RootList_light.json  ← AI 输出的浅色模式 Design Tokens
│   ├── 01_Settings_RootList_dark.json   ← AI 输出的深色模式 Design Tokens
│   └── 01_Settings_RootList_layout.json ← AI 输出的布局架构蓝图 (组件拓扑+意图+可运行双端代码骨架)
├── 02_Notes_DetailEditor/
│   ├── ...
└── ...
```

## 最终产出物（需用户显式指令触发）

> ⚠️ **硬性纪律**：**没有用户的明确指令，绝对不可以擅自进行跨文件夹数据凝练或生成总规范！**

当样本积累充分且**接到用户明确指令后**，方可启动数据聚合流水线：
- 一份完整的 **Apple Design System 规范文档**（总结共同视觉语法与数学公理）
- 一个可供 AI Agent 调用的专有 **Skill**（让任何 Agent 都能按照纯正 Apple 规范输出 UI）

## 当前状态

- [x] 项目目录结构已建立
- [x] `measure_helper.py` 测量脚本已完成（支持多种图片格式与严格命名）
- [x] `validate_pair.py` 合规校验脚本已完成（支持分阶段独立校核与严格命名校验）
- [x] 逆向工程执行规则（`rules.md`）已定义（强制串行单步过审，未经指令严禁凝练）
- [ ] 逐组截图采集与单次会话分析中
- [ ] 数据聚合与规范提炼（待用户明确指令唤醒）
