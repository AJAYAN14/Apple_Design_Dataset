#!/usr/bin/env python3
"""
export_blueprint.py — 将 {folder}_layout.json 渲染导出为 Markdown 文档或原生代码骨架

用法:
    python export_blueprint.py <folder_path>
    python export_blueprint.py <folder_path> --format md --output <path>
    python export_blueprint.py <folder_path> --format compose
    python export_blueprint.py <folder_path> --format swiftui
"""

import sys
import json
import argparse
from pathlib import Path

# ── 确保 Windows 终端 UTF-8 编码兼容 ───────────────────────
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")


def render_markdown(layout_data: dict, light_data: dict = None, dark_data: dict = None) -> str:
    vi = layout_data.get("view_identity", {})
    app_name = vi.get("app_name", "App")
    view_name = vi.get("view_name", "View")
    archetype = vi.get("archetype", "Custom")

    wf = layout_data.get("wireframe_ascii", "").strip()
    ct = layout_data.get("component_tree", {})
    lcr = layout_data.get("layout_constraints_and_rhythm", {})
    di = layout_data.get("design_intent", {})
    cs = layout_data.get("code_skeletons", {})

    lines = [
        f"# {app_name} - {view_name} 界面工程蓝图 (Blueprint)",
        "",
        f"- **布局范式 (Archetype)**: `{archetype}`",
        f"- **设备基准**: {vi.get('device', {}).get('model', 'iPhone')} (@{vi.get('device', {}).get('scale_factor', 3)}x)",
        "",
        "## 1. 布局结构线框图 (Visual Wireframe)",
        "```text",
        wf if wf else "(未提供线框图)",
        "```",
        "",
        "## 2. 组件拓扑树与约束节奏 (Component Hierarchy & Spacing)",
        f"- **根容器**: `{ct.get('root', 'Scaffold')}`",
    ]

    top_bar = ct.get("top_app_bar")
    if top_bar:
        lines.append(f"  └── **TopBar**: `{top_bar.get('type')}` (标题: '{top_bar.get('title')}', 可折叠: {top_bar.get('collapsible')})")

    scroll = ct.get("scroll_container")
    if scroll:
        lines.append(f"  └── **ScrollContainer**: `{scroll.get('type')}` (外边距: {scroll.get('edge_margin_pt')}pt, 间隙: {scroll.get('section_gap_pt')}pt)")
        for sec in scroll.get("sections", []):
            lines.append(f"      ├── **Section** `[{sec.get('section_id')}]` (策略: `{sec.get('layout_strategy')}`, 圆角: {sec.get('corner_radius_pt')}pt)")
            for item in sec.get("items", []):
                lines.append(f"      │   ├── Item: `{item.get('item_type')}` (高度: {item.get('height_pt')}pt, 标题: '{item.get('content', {}).get('title')}')")
            sep = sec.get("separator_strategy", {})
            if sep.get("exists"):
                lines.append(f"      │   └── Separator: 左缩进 {sep.get('inset_left_pt')}pt ({sep.get('rule')})")

    lines.extend([
        "",
        "## 3. 设计策略与意图解剖 (Design Rationale)",
        f"- **视觉锚点 (Visual Anchor)**: {di.get('visual_anchor', '无')}",
        f"- **信息层级 (Hierarchy)**: {di.get('information_hierarchy', '无')}",
        f"- **排版意图推导 (Rationale)**: {di.get('rationale_for_layout', '无')}",
        "",
        "## 4. 开箱即用的代码骨架 (Ready-to-Run Code Skeletons)",
    ])

    compose_code = cs.get("jetpack_compose")
    if compose_code:
        lines.extend([
            "### Jetpack Compose",
            "```kotlin",
            compose_code.strip(),
            "```",
            "",
        ])

    swiftui_code = cs.get("swiftui")
    if swiftui_code:
        lines.extend([
            "### SwiftUI",
            "```swift",
            swiftui_code.strip(),
            "```",
            "",
        ])

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="将 {folder}_layout.json 导出为 Markdown 或原生代码骨架")
    parser.add_argument("folder", help="目标子文件夹路径 (如 01_Settings_RootList/)")
    parser.add_argument(
        "--format",
        choices=["md", "compose", "swiftui", "json"],
        default="md",
        help="导出目标格式: 'md' (默认 Markdown 完整蓝图), 'compose' (Kotlin 代码), 'swiftui' (Swift 代码), 'json' (原始 JSON)",
    )
    parser.add_argument("--output", "-o", help="输出文件路径 (默认输出到终端或写入 {folder}_blueprint.md)")
    parser.add_argument("--write-file", "-w", action="store_true", help="直接在文件夹内写入对应文件")

    args = parser.parse_args()
    folder = Path(args.folder)

    if not folder.exists() or not folder.is_dir():
        print(f"错误: 文件夹不存在: {folder}", file=sys.stderr)
        sys.exit(1)

    layout_file = folder / f"{folder.name}_layout.json"
    if not layout_file.exists():
        print(f"错误: 未找到布局文件 {layout_file.name}", file=sys.stderr)
        sys.exit(1)

    layout_data = json.loads(layout_file.read_text(encoding="utf-8"))

    light_file = folder / f"{folder.name}_light.json"
    light_data = json.loads(light_file.read_text(encoding="utf-8")) if light_file.exists() else None

    dark_file = folder / f"{folder.name}_dark.json"
    dark_data = json.loads(dark_file.read_text(encoding="utf-8")) if dark_file.exists() else None

    if args.format == "md":
        content = render_markdown(layout_data, light_data, dark_data)
        out_ext = ".md"
        default_out_name = f"{folder.name}_blueprint.md"
    elif args.format == "compose":
        content = layout_data.get("code_skeletons", {}).get("jetpack_compose", "// 未提供 Compose 代码")
        out_ext = ".kt"
        default_out_name = f"{folder.name}_Skeleton.kt"
    elif args.format == "swiftui":
        content = layout_data.get("code_skeletons", {}).get("swiftui", "// 未提供 SwiftUI 代码")
        out_ext = ".swift"
        default_out_name = f"{folder.name}_Skeleton.swift"
    elif args.format == "json":
        content = json.dumps(layout_data, ensure_ascii=False, indent=2)
        out_ext = ".json"
        default_out_name = f"{folder.name}_layout.json"

    if args.write_file:
        out_path = folder / default_out_name
        out_path.write_text(content, encoding="utf-8")
        print(f"🎉 已成功生成文件: {out_path.resolve()}")
    elif args.output:
        out_path = Path(args.output)
        out_path.write_text(content, encoding="utf-8")
        print(f"🎉 已成功生成文件: {out_path.resolve()}")
    else:
        print(content)


if __name__ == "__main__":
    main()
