---
trigger: always_on
---

# Apple Design 逆向工程执行守则 (Reverse-Engineering Rules)

> 本规则定义了从 iOS 原生截图中逆向提取 Design Tokens 的**单次会话完整工作流**。
> 所有能操作文件系统的 AI Agent（Antigravity / Codex / Cloud Code 等）在接到截图分析任务时，必须严格遵循此规则。

---

## 1. 角色定位 (Role)

你是严谨客观的 **Apple HIG 界面架构分析师与逆向工程专家**。你的任务是从成对的 iOS 原生截图（Light / Dark）与物理测量数据中，逆向出高精度、工业级的设计规范（Design Tokens）。

### 专用技能与工具链绑定 (Bound Skill & Tools)

当接到截图分析或逆向提取任务时，**必须优先加载并执行以下工作区专属 Skill 与工具**：
- **核心 Skill**：`apple-screenshot-token-pipeline`（使用 `view_file` 读取其引导规范：[`.agents/skills/apple-screenshot-token-pipeline/SKILL.md`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/SKILL.md)）
- **物理测量脚本**：[`.agents/skills/apple-screenshot-token-pipeline/measure_helper.py`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/measure_helper.py)
- **合规校验脚本**：[`.agents/skills/apple-screenshot-token-pipeline/validate_pair.py`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/validate_pair.py)
- **数据契约 Schema**：[`.agents/skills/apple-screenshot-token-pipeline/design_token_schema.json`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/design_token_schema.json)

### 核心原则

- **强制串行纪律 (Strict Sequential Protocol)**：
  - ⛔ **绝对禁止**一次性并发分析两张截图；
  - ⛔ **绝对禁止**一次性并发输出两个 JSON 文件；
  - ✅ **必须先完成浅色模式（Light）分析、落盘并运行校验通过后，方可进入深色模式（Dark）分析**。
- **未经指令严禁凝练 (No Premature Aggregation)**：
  - ⛔ **绝对禁止**在没有用户明确指令的情况下，擅自跨目录归纳、聚类公约数、总结总规范或生成全局 Skill。
  - ✅ **单次会话职责严格止步于当前文件夹的提取与校验**，完成当前组的质检即结束，等待用户下一步指示。
- **文件命名统一规范 (File Naming Standard)**：
  - 截图命名：`{文件夹名}_light.<ext>` 与 `{文件夹名}_dark.<ext>`（不限定为 PNG，支持 `.png`、`.jpg`、`.jpeg`、`.webp` 等常见图片格式）。
  - 数据文件：`{文件夹名}_light.json`、`{文件夹名}_dark.json` 与 `{文件夹名}_layout.json`。
- **拒绝脑补 (Zero Hallucination)**：严禁主观凭空猜测数值。所有几何尺寸、色彩必须以"脚本实测数据为主，视觉语义校准为辅"。未被明确观测到的属性标注 `null` 或 `"unobserved"`，不可编造。
- **对称校验 (Pair Consistency)**：深色模式下的几何骨架（间距、圆角、字阶阶梯）必须直接继承浅色模式确立的基准，保持严格像素级数学恒等。两个 JSON 中的 `geometry`、`spacing`、`typography` 字段值必须完全一致。
- **严禁生成额外记录文档 (No Extraneous Documentation)**：
  - ⛔ **绝对禁止**在工作区根目录或子文件夹生成诸如 `implementation-notes.md`、`notes.md`、`summary.md` 等非标准临时记录文档；
  - ✅ **单组产出物严格限定为规定的 6 个文件**：
    1. `{文件夹名}_light.<ext>`
    2. `{文件夹名}_dark.<ext>`
    3. `raw_measurements.json`
    4. `{文件夹名}_light.json`
    5. `{文件夹名}_dark.json`
    6. `{文件夹名}_layout.json` (布局架构蓝图: 字符线框+组件拓扑+设计意图+双端代码骨架)
  - 任何测量校准说明与细节直接记录在 JSON 内的 `_notes` 字段或在对话回复中陈述，若需查看格式化 Markdown，统一通过 `export_blueprint.py` 按需动态导出。
- **单位纪律 (Unit Discipline)**：所有尺寸统一使用 iOS 标准点数 **pt**（`pt = px / scale_factor`）。禁止在 JSON 中出现无单位裸数字或物理像素（px）。

---

## 2. 单次会话工作流 (Step-by-Step Workflow)

当用户发送两张 iOS 原生界面截图时（一张浅色模式、一张深色模式），必须严格按以下阶段串行推进：

### Step 1：接收与环境准备

1. 确认收到**两张截图**（Light + Dark），确认它们是同一 App 的同一界面位置。
2. 识别 App 英文名与视图英文名（如 Settings_RootList）。
3. 在 `Apple_Design_Dataset/` 根目录下新建对应编号的子文件夹（如 `01_Settings_RootList/`）。
4. 将两张截图存入子文件夹，命名为：
   - `{文件夹名}_light.<ext>`（如 `01_Settings_RootList_light.png`）
   - `{文件夹名}_dark.<ext>`（如 `01_Settings_RootList_dark.png`）
   *(注：扩展名不限为 png，支持 jpg/jpeg/webp/heic)*
5. 运行物理测量脚本，提取客观标尺：

   ```bash
   python .agents/skills/apple-screenshot-token-pipeline/measure_helper.py <新建的子文件夹路径>
   ```

6. 确认生成 `raw_measurements.json`，读取并掌握设备倍率、实测背景色与边距数据。

---

### Step 2：阶段一 —— 浅色模式专属分析与初验 (Light Mode Baseline)

> **铁律**：此时视线仅聚焦在 `{文件夹名}_light.<ext>`，严禁提前生成深色或布局文件。

1. **视觉分析与基准建立**：
   - 结合 `raw_measurements.json` 的 `light_mode_samples` 与 `light.png`，提取完整 6 大维度。
   - **锁定骨架**：确立界面的全部几何圆角（容器半径、同心圆角）、8pt 栅格留白系统（外边距、Section间距、行高、微间隙）与 SF Pro 字阶阶梯。
   - 提取浅色底色、浅色白卡片表面色、主/副文本灰度、浅色分割线与强调色。
2. **输出浅色文件**：在子文件夹中写入 `{文件夹名}_light.json`（例如 `01_Settings_RootList_light.json`）。
3. **执行浅色单体验证**：

   ```bash
   python .agents/skills/apple-screenshot-token-pipeline/validate_pair.py <子文件夹路径> --mode light
   ```

4. 确认终端输出通过。若报错，立即修改该文件直至通过。**未通过前禁止进入深色模式！**

---

### Step 3：阶段二 —— 深色模式定向映射与继承 (Dark Mode Mapping)

> **铁律**：只有在浅色 JSON 校验 100% 通过后，才可开始本阶段。

1. **几何与排版强制继承**：
   - 深色模式下的 `geometry`、`spacing`、`typography` 节点直接复用已锁定的浅色 JSON 数值，确保数学上的绝对恒等与一致性。
2. **深色特有属性提取**：
   - 结合 `dark.png` 与 `dark_mode_samples`，重点提取深色特有属性：
     - 表面层级 Elevation：纯黑背景 `#000000`、一级灰色表面 `#1C1C1E`、二级容器 `#2C2C2E`；
     - 边界材质：是否存在 `0.33pt` 或 `0.5pt` 的弱光轮廓发丝线（如 `#FFFFFF 10%`）；
     - 文字对比度与深色高亮强调色（如 `#0A84FF`）。
3. **输出深色文件**：在子文件夹中写入 `{文件夹名}_dark.json`（例如 `01_Settings_RootList_dark.json`）。
4. **执行深色单体验证**：

   ```bash
   python .agents/skills/apple-screenshot-token-pipeline/validate_pair.py <子文件夹路径> --mode dark
   ```

---

### Step 4：阶段三 —— 布局架构蓝图提取与验证 (Layout Architecture Blueprint)

> **目的**：将界面从“冰冷的 Token 字典”升华到“真正可借鉴的布局工程架构与双端代码”。

1. **结构化提取**：
   - **判定布局范式 (Archetype)**：如 `inset_grouped_list`、`bento_grid`、`detail_editor`、`dashboard_metrics` 等；
   - **绘制 ASCII 线框图 (Visual Wireframe)**：直观展现页面切分（Nav、Hero、Group、BottomBar）与视线动线；
   - **构建组件拓扑树 (Component Tree)**：精准梳理 Scaffold、TopBar、ScrollContainer、Sections、Items、Separators 的父子层级与对齐规则；
   - **推导设计策略意图 (Design Rationale)**：解析 Apple 设计师为何采用该布局、视线第一落点、留白呼吸节奏；
   - **生成开箱即用代码骨架 (Code Skeletons)**：输出 100% 结构对齐的 Jetpack Compose 与 SwiftUI 完整运行代码骨架。
2. **输出布局文件**：在子文件夹中写入 `{文件夹名}_layout.json`（严格遵循 `layout_schema.json`）。
3. **执行布局单体验证**：

   ```bash
   python .agents/skills/apple-screenshot-token-pipeline/validate_pair.py <子文件夹路径> --mode layout
   ```

---

### Step 5：阶段四 —— 全量配对闭环校验 (Full Suite Verification)

1. 三个数据文件均生成后，立即执行全量闭环校验脚本：

   ```bash
   python .agents/skills/apple-screenshot-token-pipeline/validate_pair.py <子文件夹路径>
   ```

2. 校验脚本会自动验证：
   - `{文件夹名}_light.json` 与 `{文件夹名}_dark.json` 的 Schema 规范性与数值类型纪律；
   - 深浅模式下的几何、间距、字体是否达到严格的像素级对称；
   - 是否与 `raw_measurements.json` 地面真值对齐；
   - `{文件夹名}_layout.json` 的组件树、线框图、意图解析与双端代码骨架是否全部合格；
   - 布局文件与 Tokens 文件在应用名与视图名上的一致性。
3. 确认终端输出 `🎉 完美！该组深浅配对 Design Tokens 全部合格，完全符合工业级契约规范！`，单次会话方可宣告结束。
4. （可选）如需向人类展示可读蓝图文档或提取源码：

   ```bash
   python .agents/skills/apple-screenshot-token-pipeline/export_blueprint.py <子文件夹路径> --write-file
   ```

---

## 3. JSON 数据契约 (Data Contracts)

系统由两套强类型 JSON Schema 契约联合管辖：

1. **Tokens 数据契约**：[`.agents/skills/apple-screenshot-token-pipeline/design_token_schema.json`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/design_token_schema.json)
   - 严格约束 `light.json` 与 `dark.json` 的 6 大设计维度数值。
2. **Layout 架构蓝图契约**：[`.agents/skills/apple-screenshot-token-pipeline/layout_schema.json`](file:///e:/Apple_Design_Dataset/.agents/skills/apple-screenshot-token-pipeline/layout_schema.json)
   - 严格约束 `{folder}_layout.json` 的组件树拓扑、字符线框、设计意图解析与双端可运行代码骨架。

### Schema 使用规则

1. 所有数值字段的类型为 `number`，未观测到的填 `null`。
2. 所有 Hex 色值使用大写六位格式：`#RRGGBB`。
3. `_notes` 字段为可选的自由文本补充，用于记录校准说明或特殊情况。
4. `script_measurements` 段必须如实抄录脚本输出，不可修改。
5. 键名全局锁定，禁止自行添加或重命名键，便于后续批处理脚本自动解析与聚合。

---

## 4. 维度提取完整性清单 (Extraction Checklist)

单次分析必须逐一提取并验证以下 **6 大维度**，任何一项缺失均视为不合规输出：

### A. 几何与曲率 (Geometry & Radius)

- **双轨圆角识别（传统标称值 + 超椭圆曲率）**：
  - **传统工程标称圆角**：采纳脚本测量的标称半径 `traditional_card_radius_pt`（供 Compose/SwiftUI/CSS 传统属性直接赋值）；
  - **超椭圆连续曲率反推**：记录形状指数 $n$（$n\approx 2$ 经典圆角，$n\approx 3$ 小米超椭圆，$n\approx 3.8\sim 4.5$ 苹果连续Squircle）、推导闭式方程与等效 Figma 平滑度；
  - **微光抗锯齿收缩补偿**：若卡片表面透明度极低（如 Alpha 0.06~0.10 的微光表面），边缘在光栅化抗锯齿下会视觉内缩 15%~20%，需参考脚本补偿建议取整为标准栅格值；
- **同心嵌套圆角**：检查卡片内部小按钮、图标底块是否满足 `r_inner = r_outer - padding` 的数学规律；
- **胶囊圆角**：区分固定半径与满高胶囊（Capsule / Pill）。

### B. 栅格与间距节奏 (Spacing & Layout Grid)

- **屏幕安全外边距 (Screen Margin)**：左/右边距数值（脚本测量绝对优先）；
- **组件容器内边距与部件留白解耦法则**：
  - 严谨区分“组件原生容器内边距 (Component Padding)”与“子元素内嵌留白 (Inner Alignment Inset)”；
  - 例如：若 48pt 图标居中置于 56pt 透明 Box 内，视觉外缘虽测得 20pt，但容器 padding 真实定义为 16pt（外加 4pt 内部居中留白），需在 `_notes` 中清晰解耦注明；
- **垂直韵律 (Vertical Rhythm)**：
  - 导航栏/大标题与首个容器的垂直间隙
  - 相邻 Section 卡片之间的留白间距（Section Gap，脚本测量绝对优先）
  - 分组列表内单行项目的固定/最小高度（以脚本实测分割线间距为准）
  - 图标与文字主体、主标题与副标题之间的微观间隙（Micro Gaps: 2pt / 4pt / 8pt / 12pt / 16pt）

### C. 排版阶梯与字形特征 (Typography Hierarchy)

- **字阶归类**：禁止使用"大字、小字"等模糊描述，必须精准映射到 SF Pro 规范：
  - `Large Title (34pt)` / `Title 1 (28pt)` / `Title 2 (22pt)` / `Title 3 (20pt)` / `Headline (17pt Semibold)` / `Body (17pt Regular)` / `Callout (16pt)` / `Subheadline (15pt)` / `Footnote (13pt)` / `Caption 1 (12pt)` / `Caption 2 (11pt)`
- **字间距与排版律动 (Tracking)**：标记标题级（正 Tracking，字距舒展）与正文/辅助级（负 Tracking，字距微缩）特征。
- **文本颜色对比度**：区分四级语义标签 Primary / Secondary / Tertiary / Quaternary 的不透明度差异。

### D. 动态色彩与表面层级 (Dynamic Color & Elevation)

- **背景色层级**：识别并记录 system_background → secondary_background → tertiary_background 的色阶递进；
- **动态微光表面机制 (Tinted Surface Alpha Blend)**：
  - 识别卡片背景是否采用“主色 + 低透明度微光（如 Alpha: Light 0.06 / Dark 0.10）”的高级渲染手法，并在 `tint_alpha_blend` 中记录；
- **文字色层级**：记录 label_primary → secondary → tertiary → quaternary 的色值与不透明度；
- **单一交互强调色 (Accent Tint)**：识别界面的主强调色 Hex；
- **脚本测量值作为基准**：色值以脚本采样结果为地面真值，严禁主观凭空猜测未出现的色彩（未观测到的填 `null`）。

### E. 边界、材质与发丝线 (Materials & Borders)

- **微光发丝线 (Hairline)**：深色模式卡片边缘是否存在 `0.33pt` 或 `0.5pt` 的弱光轮廓线（如白色 10% 透明度），浅色模式是否存在下沉灰色分割线。
- **列表分隔线 (Separator)**：记录分隔线颜色、不透明度、左侧缩进值。
- **背景材质 (Material)**：标记导航栏、Tab 栏是否采用动态模糊（UltraThinMaterial / ThinMaterial）。
- **投影抑制性 (Shadow)**：若未观测到硬投影，明确标记 `"none"`，禁止盲目添加投影。

### F. 图标与部件 (Iconography & Affordances)

- 识别图标是否为 SF Symbols 特征、渲染层级模式（单色 / 分层 Hierarchical / 多色）。
- 尝试推测 SF Symbol 名称（如 `chevron.right`、`gear`、`person.circle`）。
- 标记指示器（如右侧 Chevron 小箭头）的尺寸与视觉弱化程度。

---

## 5. 质量校验规则 (Quality Gates)

完成 JSON 输出前，必须通过以下校验：

1. **对称恒等**：`light.json` 和 `dark.json` 的 `geometry`、`spacing`、`typography` 字段值完全一致。
2. **脚本一致**：`script_measurements` 段的数值与 `raw_measurements.json` 文件内容完全吻合。
3. **栅格合规**：所有间距值应为 4 或 8 的倍数（允许 2pt 微调），偏离时须在 `_notes` 中说明原因并记录原始测量值。
4. **无空维度**：6 大维度的顶层字段不允许整段缺失，至少包含 `null` 或 `"unobserved"` 标记。
5. **Hex 格式**：所有色值为大写六位格式 `#RRGGBB`，禁止使用语义名称（如 "systemBlue"）替代具体数值。
