#!/usr/bin/env python3
"""
measure_helper.py — 尺寸与色彩测量辅助工具（数字游标卡尺 & 吸色管）

仅提取最客观的物理数据（色值、像素距离），不做任何主观语义识别。
自动从截图分辨率匹配设备倍率，所有 px 同步换算为 pt。

用法:
    python measure_helper.py <folder_path>
    python measure_helper.py <folder_path> --scale 2.625
    python measure_helper.py <folder_path> --visualize

folder_path 中需包含成对截图：{folder_name}_light.<ext> 和 {folder_name}_dark.<ext>
输出: folder_path/raw_measurements.json
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

# 引入核心算法引擎包 (core/)
sys.path.insert(0, str(Path(__file__).resolve().parent))

import numpy as np
from PIL import Image

from core import (
    detect_device,
    sample_background,
    find_candidate_surface_color,
    generate_diagnostic_color_maps,
    rgb_to_hex,
    COLOR_QUANT,
    COLOR_MATCH,
    BG_DIFF_THRESH,
    MIN_GAP_PX,
    _build_content_mask,
    measure_horizontal_margin,
    measure_card_vertical_gap,
    measure_card_separator_inset,
    estimate_card_corner_radius,
    measure_inner_components,
)

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".heic")


def find_image(folder: Path, mode: str, required: bool = True) -> Path:
    """按规范查找截图：{folder_name}_{mode}.<ext> (支持 png, jpg, jpeg, webp, heic)"""
    prefix = f"{folder.name}_{mode}".lower()
    for f in folder.iterdir():
        if f.is_file() and f.stem.lower() == prefix and f.suffix.lower() in IMAGE_EXTENSIONS:
            return f
    if required:
        print(f"❌ 错误: 未在 '{folder.name}' 找到符合规范的截图 '{folder.name}_{mode}.<ext>'")
        print(f"   规范格式: {{文件夹名}}_{mode}.png / jpg / jpeg / webp")
        sys.exit(1)
    return None


def analyze_single(path: Path, scale: float):
    """分析单张截图，提取背景、表面色与内容掩码。"""
    img = np.array(Image.open(path).convert("RGB"))
    bg = sample_background(img)
    candidate = find_candidate_surface_color(img, bg)
    mask, kernel_params = _build_content_mask(img, bg, scale, BG_DIFF_THRESH)
    return rgb_to_hex(bg), candidate, mask, kernel_params, img.shape[:2], img, bg


def main():
    parser = argparse.ArgumentParser(
        description="iOS / Android 截图尺寸与色彩测量辅助工具（数字游标卡尺 & 吸色管）",
    )
    parser.add_argument(
        "folder",
        help="包含 {文件夹名}_light.* 和 {文件夹名}_dark.* 的子文件夹路径",
    )
    parser.add_argument(
        "--scale", type=float, default=None,
        help="强制指定缩放倍率（覆盖自动检测）。例: --scale 2 或 --scale 2.625",
    )
    parser.add_argument(
        "--visualize", action="store_true", default=False,
        help="生成梯度彩虹伪彩染色图与 CLAHE 增强图，辅助多模态 AI 与人工直观审视",
    )
    args = parser.parse_args()

    folder = Path(args.folder)
    if not folder.exists() or not folder.is_dir():
        print(f"❌ 错误: 目录不存在: {folder}")
        sys.exit(1)

    light_path = find_image(folder, "light", required=True)
    dark_path = find_image(folder, "dark", required=False)

    probe_l = Image.open(light_path)
    img_w, img_h = probe_l.size
    probe_l.close()

    if dark_path:
        probe_d = Image.open(dark_path)
        if (img_w, img_h) != probe_d.size:
            print(f"❌ 错误: 浅色与深色截图物理分辨率不一致！")
            print(f"   浅色 ({light_path.name}): {img_w}×{img_h} px")
            print(f"   深色 ({dark_path.name}): {probe_d.size[0]}×{probe_d.size[1]} px")
            print(f"   成对截图必须来自同一设备并在同一缩放状态下截取。")
            probe_d.close()
            sys.exit(1)
        probe_d.close()

    device = detect_device(img_w, img_h, args.scale)
    scale = device["scale"]

    if scale is None:
        print(f"❌ 无法识别设备 ({img_w}×{img_h} px)，且未指定 --scale。")
        print(f"   请使用 --scale 2 或 --scale 3 手动指定倍率。")
        sys.exit(1)

    pt_info = device["logical_size_pt"]
    print(f"📐 正在分析 {folder.resolve()}")
    if dark_path:
        print(f"   截图文件: {light_path.name} & {dark_path.name} (深浅双模配对)")
    else:
        print(f"   截图文件: {light_path.name} (单浅色模式)")
    print(f"   匹配设备: {device['model']}  |  "
          f"{img_w}×{img_h} px  @{scale}x  →  "
          f"{pt_info['w']}×{pt_info['h']} pt")
    print(f"   倍率来源: {device['scale_source']}\n")

    # ── 浅色与深色模式表面采样 ─────────────────────────────
    l_bg, l_cand, l_mask, l_kparams, _, l_img, l_raw_bg = analyze_single(light_path, scale)
    print(f"  [Light] 背景 {l_bg}  候选表面色 {l_cand['color_hex']}"
          f" (面积 {l_cand['area_ratio']}, 置信度 {l_cand['confidence']})")

    if dark_path:
        d_bg, d_cand, d_mask, d_kparams, _, d_img, d_raw_bg = analyze_single(dark_path, scale)
        print(f"  [Dark]  背景 {d_bg}  候选表面色 {d_cand['color_hex']}"
              f" (面积 {d_cand['area_ratio']}, 置信度 {d_cand['confidence']})")
    else:
        d_bg, d_cand, d_mask, d_kparams, d_img, d_raw_bg = None, None, None, None, None, None

    # ── 诊断与预处理伪彩染色图 (智驾与 CV 增强) ─────────
    if args.visualize:
        print("\n🎨 正在生成伪彩色与对比度诊断染色图...")
        maps_l = generate_diagnostic_color_maps(l_img, folder, "light")
        maps_d = generate_diagnostic_color_maps(d_img, folder, "dark")
        if maps_l.get("rainbow"):
            print(f"  [Light 染色] 彩虹伪彩: {maps_l['rainbow']}")
            print(f"  [Light 增强] CLAHE:    {maps_l['clahe']}")
        if maps_d.get("rainbow"):
            print(f"  [Dark 染色]  彩虹伪彩: {maps_d['rainbow']}")
            print(f"  [Dark 增强]  CLAHE:    {maps_d['clahe']}")

    # ── 间距测量 ─────────────────────────────────────────
    margin_l = measure_horizontal_margin(l_mask, scale)
    margin_d = measure_horizontal_margin(d_mask, scale) if d_mask is not None else margin_l

    ml = margin_l["margin_pt"]
    md = margin_d["margin_pt"] if dark_path else None
    if ml is not None and md is not None:
        margin_pt = round((ml + md) / 2, 1) if abs(ml - md) <= max(ml, md, 1) * 0.3 else None
    else:
        margin_pt = ml or md

    gap_l = measure_card_vertical_gap(l_mask, scale)
    gap_d = measure_card_vertical_gap(d_mask, scale) if d_mask is not None else gap_l

    gl = gap_l["gap_pt"]
    gd = gap_d["gap_pt"] if dark_path else None
    if gl is not None and gd is not None:
        gap_pt = round((gl + gd) / 2, 1) if abs(gl - gd) <= max(gl, gd, 1) * 0.3 else None
    else:
        gap_pt = gl or gd

    sgl = gap_l.get("section_gap_pt")
    sgd = gap_d.get("section_gap_pt") if dark_path else None
    if sgl is not None and sgd is not None:
        section_gap_pt = round((sgl + sgd) / 2, 1)
    else:
        section_gap_pt = sgl or sgd

    # ── 列表分隔线探测 (拓扑解耦与连续性防假阳性过滤) ──
    sep_l = measure_card_separator_inset(l_img, gap_l["card_bounds_px"], margin_l, scale, gap_l.get("gap_pt"))
    sep_d = measure_card_separator_inset(d_img, gap_d["card_bounds_px"], margin_d, scale, gap_d.get("gap_pt")) if d_img is not None else sep_l

    sl = sep_l["inset_left_pt"]
    sd = sep_d["inset_left_pt"] if dark_path else None
    if sl is not None and sd is not None:
        separator_inset_pt = round((sl + sd) / 2, 1)
    else:
        separator_inset_pt = sl or sd

    # ── 卡片圆角拟合 (多角巡检与抗遮挡纯度自适应拟合) ────
    radius_l = estimate_card_corner_radius(l_img, l_raw_bg, gap_l["card_bounds_px"], margin_l, scale)
    radius_d = estimate_card_corner_radius(d_img, d_raw_bg, gap_d["card_bounds_px"], margin_d, scale) if d_img is not None else radius_l

    trad_r_l = radius_l["traditional_circle"]["radius_pt"]
    comp_r_l = radius_l["traditional_circle"]["compensated_radius_pt"]
    se_l = radius_l["superellipse"]
    corner_sel_l = radius_l.get("corner_selected", "TL")

    # ── 卡片内部组件与内边距自动探测 (借鉴 UIED Component 分解) ──
    inner_l = measure_inner_components(l_img, gap_l["card_bounds_px"], margin_l, scale)
    inner_d = measure_inner_components(d_img, gap_d["card_bounds_px"], margin_d, scale) if d_img is not None else inner_l

    # ── 终端结果输出 ─────────────────────────────────────
    print(f"\n  水平外边距 ≈ {margin_pt} pt  (Light {ml}" + (f" / Dark {md})" if dark_path else ")"))
    print(f"  卡片垂直间距 ≈ {gap_pt} pt  (Light {gl}" + (f" / Dark {gd})" if dark_path else ")"))
    if section_gap_pt is not None:
        print(f"  跨 Section 宏观留白 ≈ {section_gap_pt} pt  (Light {sgl}" + (f" / Dark {sgd})" if dark_path else ")"))
    if separator_inset_pt is not None:
        print(f"  列表分隔线左缩进 ≈ {separator_inset_pt} pt  (Light {sl}" + (f" / Dark {sd})" if dark_path else ")"))
    else:
        print(f"  列表分隔线 ≈ 未检测到有效行间分割线 (独立卡片容器/无分割线)")
    if trad_r_l is not None:
        comp_str = f" (微光补偿建议: ~{comp_r_l} pt)" if comp_r_l else ""
        print(f"  传统圆角拟合 ≈ {trad_r_l} pt{comp_str} (自适应最优角: {corner_sel_l})")
    if se_l.get("shape_exponent_n") is not None:
        print(f"  超椭圆曲率拟合 ≈ 指数 n={se_l['shape_exponent_n']} ({se_l['curve_style']})")
        print(f"  推导数学方程 ≈ {se_l['exact_formula']}")
    if inner_l.get("detected"):
        r_str = f", 部件圆角: ~{inner_l['inner_radius_pt']} pt" if inner_l.get("inner_radius_pt") else ""
        print(f"  内部独立部件检测 ≈ 尺寸 {inner_l['item_size_pt']} pt (左内边距: {inner_l['padding_left_pt']} pt, 上内边距: {inner_l['padding_top_pt']} pt{r_str})")
    dark_cards_str = f"  Dark {len(gap_d['card_bounds_px'])} 个" if dark_path else ""
    print(f"  检测到卡片: Light {len(gap_l['card_bounds_px'])} 个{dark_cards_str}")

    # ── 格式化输出 raw_measurements.json ─────────────────
    result = {
        "device_info": device,
        "analysis_params": {
            "color_quant": COLOR_QUANT,
            "color_match": COLOR_MATCH,
            "bg_diff_thresh": BG_DIFF_THRESH,
            "min_gap_px": MIN_GAP_PX,
            "kernel_params_light": l_kparams,
            "kernel_params_dark": d_kparams or l_kparams,
        },
        "light_mode_samples": {
            "background_hex": l_bg,
            "candidate_surface": l_cand,
        },
        "dark_mode_samples": {
            "background_hex": d_bg,
            "candidate_surface": d_cand,
        },
        "measured_metrics_pt": {
            "screen_horizontal_margin_pt": margin_pt,
            "card_vertical_gap_pt": gap_pt,
            "section_vertical_gap_pt": section_gap_pt,
            "separator_inset_left_pt": separator_inset_pt,
            "traditional_card_radius_pt": trad_r_l,
            "compensated_card_radius_pt": comp_r_l,
            "superellipse_curvature": se_l,
            "inner_item_metrics": {
                "detected": inner_l.get("detected", False),
                "item_size_pt": inner_l.get("item_size_pt"),
                "padding_left_pt": inner_l.get("padding_left_pt"),
                "padding_top_pt": inner_l.get("padding_top_pt"),
                "inner_radius_pt": inner_l.get("inner_radius_pt")
            },
            "margin_consensus": "valid" if margin_pt is not None else "missing_or_inconsistent",
            "gap_consensus": "valid" if gap_pt is not None else "missing_or_inconsistent",
        },
        "per_mode_details": {
            "light": {
                "margin": margin_l,
                "gap": gap_l,
                "radius": radius_l,
                "separator": sep_l,
                "inner_components": inner_l,
            },
            "dark": {
                "margin": margin_d,
                "gap": gap_d,
                "radius": radius_d,
                "separator": sep_d,
                "inner_components": inner_d,
            },
        },
    }

    out_path = folder / "raw_measurements.json"
    out_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n✅ 已输出 → {out_path}")


if __name__ == "__main__":
    main()
