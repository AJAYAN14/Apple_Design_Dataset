#!/usr/bin/env python3
"""
validate_pair.py — Apple Design Token 深浅配对合规性与数据契约校验脚本

单次会话执行闭环的质检工具：
1. 校验 light.json 与 dark.json 语法有效性与必要字段完整性；
2. 校验字段类型纪律（严禁裸字符串替代数值，如 "16pt" 应为 16）；
3. 校验 Hex 色值格式（必须为 #RRGGBB 大写六位）；
4. 校验深浅模式下的几何骨架恒等性（Geometry、Spacing、Typography 像素级对称）；
5. 校验与 raw_measurements.json 物理测量数据的一致性。

用法:
    python validate_pair.py <folder_path>
    python validate_pair.py 01_Settings_RootList/
    python validate_pair.py --all
"""

import sys
import json
import re
import argparse
from pathlib import Path
from typing import Any, List, Tuple, Dict

# ── 确保 Windows 终端 UTF-8 编码兼容 ───────────────────────
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# ── ANSI 颜色输出 ─────────────────────────────────────────
class Colors:
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    RESET = "\033[0m"

def success(msg: str) -> str:
    return f"{Colors.GREEN}[OK] {msg}{Colors.RESET}"

def failure(msg: str) -> str:
    return f"{Colors.RED}[FAIL] {msg}{Colors.RESET}"

def warning(msg: str) -> str:
    return f"{Colors.YELLOW}[WARN] {msg}{Colors.RESET}"

def info(msg: str) -> str:
    return f"{Colors.CYAN}{msg}{Colors.RESET}"

HEX_REGEX = re.compile(r"^#[0-9A-Fa-f]{6}$")

# ── 辅助检查函数 ──────────────────────────────────────────
def is_number(val: Any) -> bool:
    return isinstance(val, (int, float)) and not isinstance(val, bool)

def check_hex(val: Any, path: str, errors: List[str], allow_null: bool = True):
    if val is None:
        if not allow_null:
            errors.append(f"[{path}] 不允许为 null")
        return
    if not isinstance(val, str) or not HEX_REGEX.match(val):
        errors.append(f"[{path}] 色值非法: '{val}' (必须为 #RRGGBB 格式十六进制)")

def check_num(val: Any, path: str, errors: List[str], allow_null: bool = True, min_val: float = None, max_val: float = None):
    if val is None:
        if not allow_null:
            errors.append(f"[{path}] 不允许为 null")
        return
    if not is_number(val):
        errors.append(f"[{path}] 类型错误: 必须为数值 (数字 pt/比例)，当前值为: {repr(val)}")
        return
    if min_val is not None and val < min_val:
        errors.append(f"[{path}] 数值越界: 当前值 {val} < 最小值 {min_val}")
    if max_val is not None and val > max_val:
        errors.append(f"[{path}] 数值越界: 当前值 {val} > 最大值 {max_val}")


# ── 单文件 Schema 结构校验 ────────────────────────────────
def validate_single_token_schema(data: dict, expected_mode: str, filename: str) -> Tuple[List[str], List[str]]:
    errors = []
    warnings_list = []
    prefix = f"{filename}"

    # 1. 顶层根键检查
    required_roots = [
        "view_identity", "geometry", "spacing", "typography",
        "colors", "materials_and_effects", "iconography", "script_measurements"
    ]
    for k in required_roots:
        if k not in data:
            errors.append(f"[{prefix}] 缺少顶层关键节点: '{k}'")

    if errors:
        return errors, warnings_list

    # 2. view_identity
    vi = data.get("view_identity", {})
    if not vi.get("app_name"):
        errors.append(f"[{prefix}.view_identity] app_name 不能为空")
    if not vi.get("view_name"):
        errors.append(f"[{prefix}.view_identity] view_name 不能为空")
    if vi.get("theme_mode") != expected_mode:
        errors.append(f"[{prefix}.view_identity] theme_mode 期望为 '{expected_mode}'，实际为 '{vi.get('theme_mode')}'")

    device = vi.get("device", {})
    check_num(device.get("scale_factor"), f"{prefix}.view_identity.device.scale_factor", errors, allow_null=False, min_val=1, max_val=5)

    # 3. geometry
    geo = data.get("geometry", {})
    if geo.get("curve_type") not in ["continuous", "circular", "unobserved"]:
        warnings_list.append(f"[{prefix}.geometry.curve_type] 建议标注为 'continuous' (Squircle) 或 'circular'，当前为: '{geo.get('curve_type')}'")
    check_num(geo.get("container_card_radius_pt"), f"{prefix}.geometry.container_card_radius_pt", errors)
    check_num(geo.get("inner_item_radius_pt"), f"{prefix}.geometry.inner_item_radius_pt", errors)
    check_num(geo.get("modal_sheet_radius_pt"), f"{prefix}.geometry.modal_sheet_radius_pt", errors)

    # 校验超椭圆连续曲率块 (可选)
    se = geo.get("superellipse")
    if isinstance(se, dict):
        check_num(se.get("shape_exponent_n"), f"{prefix}.geometry.superellipse.shape_exponent_n", errors, allow_null=True)
        check_num(se.get("figma_corner_smoothing"), f"{prefix}.geometry.superellipse.figma_corner_smoothing", errors, allow_null=True, min_val=0.0, max_val=1.0)

    # 4. spacing
    sp = data.get("spacing", {})
    check_num(sp.get("grid_base_pt"), f"{prefix}.spacing.grid_base_pt", errors)
    check_num(sp.get("screen_edge_margin_pt"), f"{prefix}.spacing.screen_edge_margin_pt", errors)
    check_num(sp.get("card_vertical_gap_pt"), f"{prefix}.spacing.card_vertical_gap_pt", errors)

    cip = sp.get("card_interior_padding", {})
    for side in ["top_pt", "bottom_pt", "left_pt", "right_pt"]:
        check_num(cip.get(side), f"{prefix}.spacing.card_interior_padding.{side}", errors)

    vg = sp.get("vertical_gaps", {})
    for gap_k in ["nav_title_to_content_pt", "section_to_section_pt", "row_min_height_pt", "icon_to_text_pt", "title_to_subtitle_pt"]:
        check_num(vg.get(gap_k), f"{prefix}.spacing.vertical_gaps.{gap_k}", errors)

    # 5. typography
    ty = data.get("typography", {})
    styles = ty.get("observed_styles", [])
    if not isinstance(styles, list):
        errors.append(f"[{prefix}.typography.observed_styles] 必须为列表")
    else:
        for idx, item in enumerate(styles):
            s_p = f"{prefix}.typography.observed_styles[{idx}]"
            check_num(item.get("size_pt"), f"{s_p}.size_pt", errors, allow_null=False)
            check_num(item.get("tracking_pt"), f"{s_p}.tracking_pt", errors, allow_null=True)
            check_num(item.get("line_height_pt"), f"{s_p}.line_height_pt", errors, allow_null=True)

    op = ty.get("text_opacity_hierarchy", {})
    for op_k in ["primary", "secondary", "tertiary", "quaternary"]:
        check_num(op.get(op_k), f"{prefix}.typography.text_opacity_hierarchy.{op_k}", errors, allow_null=True, min_val=0.0, max_val=1.0)

    # 6. colors
    col = data.get("colors", {})
    bg_h = col.get("background_hierarchy", {})
    check_hex(bg_h.get("system_background"), f"{prefix}.colors.background_hierarchy.system_background", errors, allow_null=False)
    check_hex(bg_h.get("secondary_background"), f"{prefix}.colors.background_hierarchy.secondary_background", errors, allow_null=True)
    check_hex(bg_h.get("tertiary_background"), f"{prefix}.colors.background_hierarchy.tertiary_background", errors, allow_null=True)

    txt_c = col.get("text_colors", {})
    check_hex(txt_c.get("label_primary"), f"{prefix}.colors.text_colors.label_primary", errors, allow_null=False)
    check_hex(txt_c.get("label_secondary"), f"{prefix}.colors.text_colors.label_secondary", errors, allow_null=True)
    check_hex(txt_c.get("label_tertiary"), f"{prefix}.colors.text_colors.label_tertiary", errors, allow_null=True)
    check_hex(txt_c.get("label_quaternary"), f"{prefix}.colors.text_colors.label_quaternary", errors, allow_null=True)

    check_hex(col.get("accent_tint"), f"{prefix}.colors.accent_tint", errors, allow_null=False)

    tab = col.get("tint_alpha_blend", {})
    if isinstance(tab, dict) and tab.get("exists") is True:
        check_hex(tab.get("base_color_hex"), f"{prefix}.colors.tint_alpha_blend.base_color_hex", errors, allow_null=True)
        check_num(tab.get("alpha_light"), f"{prefix}.colors.tint_alpha_blend.alpha_light", errors, allow_null=True, min_val=0.0, max_val=1.0)
        check_num(tab.get("alpha_dark"), f"{prefix}.colors.tint_alpha_blend.alpha_dark", errors, allow_null=True, min_val=0.0, max_val=1.0)

    # 7. materials_and_effects
    mat = data.get("materials_and_effects", {})
    hairline = mat.get("hairline_border", {})
    if isinstance(hairline, dict) and hairline.get("exists") is True:
        check_num(hairline.get("width_pt"), f"{prefix}.materials.hairline_border.width_pt", errors, allow_null=False)
        check_hex(hairline.get("color_hex"), f"{prefix}.materials.hairline_border.color_hex", errors, allow_null=False)
        check_num(hairline.get("opacity"), f"{prefix}.materials.hairline_border.opacity", errors, allow_null=True, min_val=0.0, max_val=1.0)

    separator = mat.get("separator", {})
    if isinstance(separator, dict) and separator.get("exists") is True:
        check_hex(separator.get("color_hex"), f"{prefix}.materials.separator.color_hex", errors, allow_null=False)
        check_num(separator.get("opacity"), f"{prefix}.materials.separator.opacity", errors, allow_null=True, min_val=0.0, max_val=1.0)
        check_num(separator.get("inset_left_pt"), f"{prefix}.materials.separator.inset_left_pt", errors, allow_null=True)

    # 8. script_measurements
    sm = data.get("script_measurements", {})
    check_hex(sm.get("background_hex_measured"), f"{prefix}.script_measurements.background_hex_measured", errors)
    check_hex(sm.get("candidate_surface_hex_measured"), f"{prefix}.script_measurements.candidate_surface_hex_measured", errors, allow_null=True)
    check_num(sm.get("screen_margin_pt_measured"), f"{prefix}.script_measurements.screen_margin_pt_measured", errors, allow_null=True)
    check_num(sm.get("card_gap_pt_measured"), f"{prefix}.script_measurements.card_gap_pt_measured", errors, allow_null=True)
    check_num(sm.get("section_gap_pt_measured"), f"{prefix}.script_measurements.section_gap_pt_measured", errors, allow_null=True)
    check_num(sm.get("separator_inset_left_pt_measured"), f"{prefix}.script_measurements.separator_inset_left_pt_measured", errors, allow_null=True)
    check_num(sm.get("traditional_card_radius_pt_measured"), f"{prefix}.script_measurements.traditional_card_radius_pt_measured", errors, allow_null=True)
    check_num(sm.get("superellipse_exponent_measured"), f"{prefix}.script_measurements.superellipse_exponent_measured", errors, allow_null=True)

    return errors, warnings_list


# ── 布局架构蓝图 Schema 结构校验 ────────────────────────────
def validate_single_layout_schema(data: dict, filename: str) -> Tuple[List[str], List[str]]:
    """验证 {folder}_layout.json 的结构合法性与关键约束。"""
    errors = []
    warnings_list = []
    prefix = f"{filename}"

    # 1. 顶层根键检查
    required_roots = [
        "view_identity", "wireframe_ascii", "component_tree",
        "layout_constraints_and_rhythm", "design_intent", "code_skeletons"
    ]
    for k in required_roots:
        if k not in data:
            errors.append(f"[{prefix}] 缺少顶层关键节点: '{k}'")

    if errors:
        return errors, warnings_list

    # 2. view_identity
    vi = data.get("view_identity", {})
    if not vi.get("app_name"):
        errors.append(f"[{prefix}.view_identity] app_name 不能为空")
    if not vi.get("view_name"):
        errors.append(f"[{prefix}.view_identity] view_name 不能为空")
    if not vi.get("archetype"):
        errors.append(f"[{prefix}.view_identity] archetype 不能为空 (如 inset_grouped_list / bento_grid / detail_editor 等)")

    device = vi.get("device", {})
    if isinstance(device, dict):
        check_num(device.get("scale_factor"), f"{prefix}.view_identity.device.scale_factor", errors, allow_null=True)

    # 3. wireframe_ascii
    wf = data.get("wireframe_ascii")
    if not isinstance(wf, str) or not wf.strip():
        errors.append(f"[{prefix}.wireframe_ascii] 必须提供非空的 ASCII 布局示意图")

    # 4. component_tree
    ct = data.get("component_tree", {})
    if not isinstance(ct, dict):
        errors.append(f"[{prefix}.component_tree] 必须为字典对象")
    else:
        if not ct.get("root"):
            warnings_list.append(f"[{prefix}.component_tree.root] 建议标注根容器 (如 'Scaffold')")
        sc = ct.get("scroll_container", {})
        if isinstance(sc, dict):
            check_num(sc.get("edge_margin_pt"), f"{prefix}.component_tree.scroll_container.edge_margin_pt", errors, allow_null=True)
            check_num(sc.get("section_gap_pt"), f"{prefix}.component_tree.scroll_container.section_gap_pt", errors, allow_null=True)
            sections = sc.get("sections", [])
            if isinstance(sections, list):
                for idx, sec in enumerate(sections):
                    s_p = f"{prefix}.component_tree.scroll_container.sections[{idx}]"
                    if isinstance(sec, dict):
                        check_num(sec.get("corner_radius_pt"), f"{s_p}.corner_radius_pt", errors, allow_null=True)
                        cp = sec.get("card_padding", {})
                        if isinstance(cp, dict):
                            for side in ["top_pt", "bottom_pt", "left_pt", "right_pt"]:
                                check_num(cp.get(side), f"{s_p}.card_padding.{side}", errors, allow_null=True)
                        sep_strat = sec.get("separator_strategy", {})
                        if isinstance(sep_strat, dict) and sep_strat.get("exists"):
                            check_num(sep_strat.get("inset_left_pt"), f"{s_p}.separator_strategy.inset_left_pt", errors, allow_null=True)

    # 5. layout_constraints_and_rhythm
    lcr = data.get("layout_constraints_and_rhythm", {})
    if isinstance(lcr, dict):
        da = lcr.get("density_and_alignment", {})
        if isinstance(da, dict):
            check_num(da.get("screen_margin_pt"), f"{prefix}.layout_constraints_and_rhythm.density_and_alignment.screen_margin_pt", errors, allow_null=True)
            check_num(da.get("touch_target_min_height_pt"), f"{prefix}.layout_constraints_and_rhythm.density_and_alignment.touch_target_min_height_pt", errors, allow_null=True)

    # 6. design_intent
    di = data.get("design_intent", {})
    if not isinstance(di, dict):
        errors.append(f"[{prefix}.design_intent] 必须为字典对象")
    else:
        for k in ["visual_anchor", "information_hierarchy", "rationale_for_layout"]:
            if not di.get(k):
                warnings_list.append(f"[{prefix}.design_intent.{k}] 建议填写详细的设计意图解析")

    # 7. code_skeletons
    cs = data.get("code_skeletons", {})
    if not isinstance(cs, dict):
        errors.append(f"[{prefix}.code_skeletons] 必须为字典对象 (包含 jetpack_compose 与 swiftui)")
    else:
        jc = cs.get("jetpack_compose")
        sw = cs.get("swiftui")
        if not jc and not sw:
            errors.append(f"[{prefix}.code_skeletons] 必须提供至少一个代码骨架 (jetpack_compose 或 swiftui)")

    return errors, warnings_list


# ── 深浅对称性校验 (Pair Consistency) ────────────────────
def validate_pair_symmetry(light: dict, dark: dict) -> Tuple[List[str], List[str]]:
    """验证同一界面的 Light 和 Dark 在几何、间距、字体上保持像素级数学恒等。"""
    errors = []
    warnings_list = []

    # 1. 基础元信息一致
    for k in ["app_name", "view_name"]:
        l_v = light.get("view_identity", {}).get(k)
        d_v = dark.get("view_identity", {}).get(k)
        if l_v != d_v:
            errors.append(f"[对称性校验] view_identity.{k} 不一致: light='{l_v}', dark='{d_v}'")

    # 设备信息一致
    l_dev = light.get("view_identity", {}).get("device", {})
    d_dev = dark.get("view_identity", {}).get("device", {})
    if l_dev.get("model") != d_dev.get("model") or l_dev.get("scale_factor") != d_dev.get("scale_factor"):
        errors.append(f"[对称性校验] device 规格不一致: light={l_dev}, dark={d_dev}")

    # 2. 几何骨架一致 (Geometry)
    l_geo = light.get("geometry", {})
    d_geo = dark.get("geometry", {})
    geo_keys = ["curve_type", "container_card_radius_pt", "inner_item_radius_pt", "capsule_radius_pt", "modal_sheet_radius_pt"]
    for k in geo_keys:
        if l_geo.get(k) != d_geo.get(k):
            errors.append(f"[对称性校验 - 几何] geometry.{k} 不相等: light={repr(l_geo.get(k))}, dark={repr(d_geo.get(k))}")

    if l_geo.get("superellipse") != d_geo.get("superellipse"):
        errors.append(f"[对称性校验 - 超椭圆曲率] geometry.superellipse 不相等: light={repr(l_geo.get('superellipse'))}, dark={repr(d_geo.get('superellipse'))}")

    # 3. 间距节奏一致 (Spacing)
    l_sp = light.get("spacing", {})
    d_sp = dark.get("spacing", {})
    sp_keys = ["grid_base_pt", "screen_edge_margin_pt", "card_vertical_gap_pt"]
    for k in sp_keys:
        if l_sp.get(k) != d_sp.get(k):
            errors.append(f"[对称性校验 - 间距] spacing.{k} 不相等: light={repr(l_sp.get(k))}, dark={repr(d_sp.get(k))}")

    # 内边距一致
    l_cip = l_sp.get("card_interior_padding", {})
    d_cip = d_sp.get("card_interior_padding", {})
    for side in ["top_pt", "bottom_pt", "left_pt", "right_pt"]:
        if l_cip.get(side) != d_cip.get(side):
            errors.append(f"[对称性校验 - 卡片内边距] card_interior_padding.{side} 不相等: light={l_cip.get(side)}, dark={d_cip.get(side)}")

    # 垂直微间隙一致
    l_vg = l_sp.get("vertical_gaps", {})
    d_vg = d_sp.get("vertical_gaps", {})
    for k in ["nav_title_to_content_pt", "section_to_section_pt", "row_min_height_pt", "icon_to_text_pt", "title_to_subtitle_pt"]:
        if l_vg.get(k) != d_vg.get(k):
            errors.append(f"[对称性校验 - 垂直间距] vertical_gaps.{k} 不相等: light={l_vg.get(k)}, dark={d_vg.get(k)}")

    # 4. 字体字阶排版一致 (Typography)
    l_ty = light.get("typography", {})
    d_ty = dark.get("typography", {})
    if l_ty.get("font_family") != d_ty.get("font_family"):
        errors.append(f"[对称性校验 - 字体] font_family 不一致: light='{l_ty.get('font_family')}', dark='{d_ty.get('font_family')}'")

    l_styles = l_ty.get("observed_styles", [])
    d_styles = d_ty.get("observed_styles", [])
    if len(l_styles) != len(d_styles):
        errors.append(f"[对称性校验 - 字体层级] observed_styles 条目数不一致: light({len(l_styles)}) != dark({len(d_styles)})")
    else:
        for i in range(len(l_styles)):
            ls, ds = l_styles[i], d_styles[i]
            for check_k in ["mapped_style", "size_pt", "weight"]:
                if ls.get(check_k) != ds.get(check_k):
                    errors.append(f"[对称性校验 - 字体样式] style[{i}].{check_k} 不一致: light={ls.get(check_k)}, dark={ds.get(check_k)}")

    # 5. 材质中的几何尺寸一致性 (如分隔线左缩进)
    l_sep = light.get("materials_and_effects", {}).get("separator", {})
    d_sep = dark.get("materials_and_effects", {}).get("separator", {})
    if l_sep.get("exists") and d_sep.get("exists"):
        if l_sep.get("inset_left_pt") != d_sep.get("inset_left_pt"):
            errors.append(f"[对称性校验 - 分隔线] separator.inset_left_pt 不相等: light={l_sep.get('inset_left_pt')}, dark={d_sep.get('inset_left_pt')}")

    return errors, warnings_list


# ── 与脚本物理测量数据对照校验 (Ground Truth) ─────────────
def validate_ground_truth(light: dict, dark: dict, raw: dict) -> Tuple[List[str], List[str]]:
    errors = []
    warnings_list = []

    l_sm = light.get("script_measurements", {})
    d_sm = dark.get("script_measurements", {})

    raw_l_bg = raw.get("light_mode_samples", {}).get("background_hex")
    raw_d_bg = raw.get("dark_mode_samples", {}).get("background_hex")
    raw_metrics = raw.get("measured_metrics_pt", {})
    raw_margin = raw_metrics.get("screen_horizontal_margin_pt")
    raw_gap = raw_metrics.get("card_vertical_gap_pt")
    raw_section_gap = raw_metrics.get("section_vertical_gap_pt")
    raw_sep_inset = raw_metrics.get("separator_inset_left_pt")
    raw_radius = raw_metrics.get("traditional_card_radius_pt")

    # 对照 background_hex_measured
    if l_sm.get("background_hex_measured") != raw_l_bg:
        errors.append(f"[地面真值] light.json 中的 background_hex_measured ({l_sm.get('background_hex_measured')}) 与 raw_measurements.json ({raw_l_bg}) 不符")
    if d_sm.get("background_hex_measured") != raw_d_bg:
        errors.append(f"[地面真值] dark.json 中的 background_hex_measured ({d_sm.get('background_hex_measured')}) 与 raw_measurements.json ({raw_d_bg}) 不符")

    # 对照 margin
    if raw_margin is not None:
        if l_sm.get("screen_margin_pt_measured") != raw_margin:
            errors.append(f"[地面真值] light.json 中的 screen_margin_pt_measured ({l_sm.get('screen_margin_pt_measured')}) 与 raw ({raw_margin}) 不符")
        if d_sm.get("screen_margin_pt_measured") != raw_margin:
            errors.append(f"[地面真值] dark.json 中的 screen_margin_pt_measured ({d_sm.get('screen_margin_pt_measured')}) 与 raw ({raw_margin}) 不符")

    # 对照 gap
    if raw_gap is not None:
        if l_sm.get("card_gap_pt_measured") != raw_gap:
            errors.append(f"[地面真值] light.json 中的 card_gap_pt_measured ({l_sm.get('card_gap_pt_measured')}) 与 raw ({raw_gap}) 不符")
        if d_sm.get("card_gap_pt_measured") != raw_gap:
            errors.append(f"[地面真值] dark.json 中的 card_gap_pt_measured ({d_sm.get('card_gap_pt_measured')}) 与 raw ({raw_gap}) 不符")

    # 对照 section_gap
    if raw_section_gap is not None:
        if l_sm.get("section_gap_pt_measured") != raw_section_gap:
            errors.append(f"[地面真值] light.json 中的 section_gap_pt_measured ({l_sm.get('section_gap_pt_measured')}) 与 raw ({raw_section_gap}) 不符")
        if d_sm.get("section_gap_pt_measured") != raw_section_gap:
            errors.append(f"[地面真值] dark.json 中的 section_gap_pt_measured ({d_sm.get('section_gap_pt_measured')}) 与 raw ({raw_section_gap}) 不符")

    # 对照 separator_inset
    if raw_sep_inset is not None:
        if l_sm.get("separator_inset_left_pt_measured") != raw_sep_inset:
            errors.append(f"[地面真值] light.json 中的 separator_inset_left_pt_measured ({l_sm.get('separator_inset_left_pt_measured')}) 与 raw ({raw_sep_inset}) 不符")
        if d_sm.get("separator_inset_left_pt_measured") != raw_sep_inset:
            errors.append(f"[地面真值] dark.json 中的 separator_inset_left_pt_measured ({d_sm.get('separator_inset_left_pt_measured')}) 与 raw ({raw_sep_inset}) 不符")

    # 对照 traditional_radius
    if raw_radius is not None:
        if l_sm.get("traditional_card_radius_pt_measured") != raw_radius:
            errors.append(f"[地面真值] light.json 中的 traditional_card_radius_pt_measured ({l_sm.get('traditional_card_radius_pt_measured')}) 与 raw ({raw_radius}) 不符")
        if d_sm.get("traditional_card_radius_pt_measured") != raw_radius:
            errors.append(f"[地面真值] dark.json 中的 traditional_card_radius_pt_measured ({d_sm.get('traditional_card_radius_pt_measured')}) 与 raw ({raw_radius}) 不符")

    return errors, warnings_list


# ── JSON 文件命名解析 ────────────────────────────────────
def resolve_json_path(folder: Path, mode: str) -> Path:
    """严格按照规范定义解析 JSON 文件路径：{folder_name}_{mode}.json"""
    return folder / f"{folder.name}_{mode}.json"


# ── 单模式独立校验 (用于串行阶段性检查) ───────────────────────
def validate_single_mode(folder: Path, mode: str, verbose: bool = False) -> bool:
    target_file = resolve_json_path(folder, mode)
    print(f"\n{Colors.BOLD}🔍 正在校验单模式 ({mode}):{Colors.RESET} {target_file.name} in {folder.resolve()}")
    raw_path = folder / "raw_measurements.json"

    all_errors = []
    all_warnings = []

    # 检查是否存在旧的非标准命名
    legacy_file = folder / f"{mode}.json"
    if legacy_file.exists() and not target_file.exists():
        all_errors.append(f"发现违规命名文件 '{legacy_file.name}'！本项目严格要求文件命名必须为 '{target_file.name}'，请立即重命名。")

    if not target_file.exists():
        all_errors.append(f"未找到目标文件 '{target_file.name}' (命名规则: {{文件夹名}}_{mode}.json)")
        for err in all_errors:
            print(f"  {failure(err)}")
        return False

    try:
        data = json.loads(target_file.read_text(encoding="utf-8"))
    except Exception as e:
        all_errors.append(f"{target_file.name} JSON 解析失败: {e}")
        for err in all_errors:
            print(f"  {failure(err)}")
        return False

    if mode == "layout":
        errs, warns = validate_single_layout_schema(data, target_file.name)
        all_errors.extend(errs)
        all_warnings.extend(warns)

        # 尝试与已有 light.json 对照 view_identity 一致性
        light_file = resolve_json_path(folder, "light")
        if light_file.exists():
            try:
                l_data = json.loads(light_file.read_text(encoding="utf-8"))
                l_app = l_data.get("view_identity", {}).get("app_name")
                l_view = l_data.get("view_identity", {}).get("view_name")
                lay_app = data.get("view_identity", {}).get("app_name")
                lay_view = data.get("view_identity", {}).get("view_name")
                if lay_app and l_app and lay_app != l_app:
                    all_errors.append(f"[布局一致性] {target_file.name} app_name ('{lay_app}') 与 light.json ('{l_app}') 不一致")
                if lay_view and l_view and lay_view != l_view:
                    all_errors.append(f"[布局一致性] {target_file.name} view_name ('{lay_view}') 与 light.json ('{l_view}') 不一致")
            except Exception:
                pass
    else:
        # Schema 校验 (light/dark tokens)
        errs, warns = validate_single_token_schema(data, mode, target_file.name)
        all_errors.extend(errs)
        all_warnings.extend(warns)

        # 地面真值比对 (单模)
        if raw_path.exists():
            try:
                raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
                sm = data.get("script_measurements", {})
                raw_sample_bg = raw_data.get(f"{mode}_mode_samples", {}).get("background_hex")
                raw_metrics = raw_data.get("measured_metrics_pt", {})
                raw_margin = raw_metrics.get("screen_horizontal_margin_pt")
                raw_gap = raw_metrics.get("card_vertical_gap_pt")
                raw_section_gap = raw_metrics.get("section_vertical_gap_pt")
                raw_sep_inset = raw_metrics.get("separator_inset_left_pt")
                raw_radius = raw_metrics.get("traditional_card_radius_pt")

                if raw_sample_bg and sm.get("background_hex_measured") != raw_sample_bg:
                    all_errors.append(f"[地面真值] {target_file.name} 中的 background_hex_measured ({sm.get('background_hex_measured')}) 与 raw ({raw_sample_bg}) 不符")
                if raw_margin is not None and sm.get("screen_margin_pt_measured") != raw_margin:
                    all_errors.append(f"[地面真值] {target_file.name} 中的 screen_margin_pt_measured ({sm.get('screen_margin_pt_measured')}) 与 raw ({raw_margin}) 不符")
                if raw_gap is not None and sm.get("card_gap_pt_measured") != raw_gap:
                    all_errors.append(f"[地面真值] {target_file.name} 中的 card_gap_pt_measured ({sm.get('card_gap_pt_measured')}) 与 raw ({raw_gap}) 不符")
                if raw_section_gap is not None and sm.get("section_gap_pt_measured") != raw_section_gap:
                    all_errors.append(f"[地面真值] {target_file.name} 中的 section_gap_pt_measured ({sm.get('section_gap_pt_measured')}) 与 raw ({raw_section_gap}) 不符")
                if raw_sep_inset is not None and sm.get("separator_inset_left_pt_measured") != raw_sep_inset:
                    all_errors.append(f"[地面真值] {target_file.name} 中的 separator_inset_left_pt_measured ({sm.get('separator_inset_left_pt_measured')}) 与 raw ({raw_sep_inset}) 不符")
                if raw_radius is not None and sm.get("traditional_card_radius_pt_measured") != raw_radius:
                    all_errors.append(f"[地面真值] {target_file.name} 中的 traditional_card_radius_pt_measured ({sm.get('traditional_card_radius_pt_measured')}) 与 raw ({raw_radius}) 不符")
            except Exception as e:
                all_warnings.append(f"raw_measurements.json 比对异常: {e}")

    if all_errors:
        print(f"\n  {failure(f'发现 {len(all_errors)} 项错误 ({target_file.name} 不合格):')}")
        for err in all_errors:
            print(f"    • {Colors.RED}{err}{Colors.RESET}")
    else:
        print(f"  {success(f'{target_file.name} Schema 结构与字段类型纪律通过')}")
        if mode != "layout" and raw_path.exists():
            print(f"  {success('物理测量地面真值比对一致通过')}")

    if all_warnings:
        print(f"\n  {warning(f'提示信息 ({len(all_warnings)} 项):')}")
        for w in all_warnings:
            print(f"    • {Colors.YELLOW}{w}{Colors.RESET}")

    is_valid = len(all_errors) == 0
    if is_valid:
        if mode == "light":
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 阶段一成功！{target_file.name} 校验合格并确立几何骨架。接下来请继续分析深色模式。{Colors.RESET}\n")
        elif mode == "dark":
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 阶段二成功！{target_file.name} 校验合格。接下来请继续提取布局架构蓝图。{Colors.RESET}\n")
        elif mode == "layout":
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 阶段三成功！{target_file.name} 布局架构蓝图校验合格！{Colors.RESET}\n")
        else:
            print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 {target_file.name} 校验合格！{Colors.RESET}\n")
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}⛔ 校验未通过，请根据提示修正 {target_file.name}。{Colors.RESET}\n")

    return is_valid


# ── 单文件夹总体验证入口 ──────────────────────────────────
def validate_directory(folder: Path, verbose: bool = False) -> bool:
    light_path = resolve_json_path(folder, "light")
    dark_path = resolve_json_path(folder, "dark")
    raw_path = folder / "raw_measurements.json"

    print(f"\n{Colors.BOLD}🔍 正在校验目录 (深浅配对双模):{Colors.RESET} {folder.resolve()}")
    print(f"   目标文件: {light_path.name} & {dark_path.name}")

    all_errors = []
    all_warnings = []

    # 1. 存在性检查
    if not light_path.exists():
        all_errors.append(f"未找到 {folder.name}_light.json (请先完成阶段一：浅色模式分析与校核)")
    if not dark_path.exists():
        all_errors.append(f"未找到 {folder.name}_dark.json (请在完成浅色校验后继续完成深色模式分析)")

    if all_errors:
        for err in all_errors:
            print(f"  {failure(err)}")
        return False

    # 2. 读取与语法检查
    try:
        light_data = json.loads(light_path.read_text(encoding="utf-8"))
    except Exception as e:
        all_errors.append(f"{light_path.name} JSON 解析失败: {e}")
        light_data = None

    try:
        dark_data = json.loads(dark_path.read_text(encoding="utf-8"))
    except Exception as e:
        all_errors.append(f"{dark_path.name} JSON 解析失败: {e}")
        dark_data = None

    if light_data is None or dark_data is None:
        for err in all_errors:
            print(f"  {failure(err)}")
        return False

    # 3. 独立 Schema 校验
    l_errs, l_warns = validate_single_token_schema(light_data, "light", light_path.name)
    d_errs, d_warns = validate_single_token_schema(dark_data, "dark", dark_path.name)
    all_errors.extend(l_errs)
    all_errors.extend(d_errs)
    all_warnings.extend(l_warns)
    all_warnings.extend(d_warns)

    # 4. 深浅对称恒等校验
    sym_errs, sym_warns = validate_pair_symmetry(light_data, dark_data)
    all_errors.extend(sym_errs)
    all_warnings.extend(sym_warns)

    # 5. 地面真值比对 (若存在 raw_measurements.json)
    if raw_path.exists():
        try:
            raw_data = json.loads(raw_path.read_text(encoding="utf-8"))
            gt_errs, gt_warns = validate_ground_truth(light_data, dark_data, raw_data)
            all_errors.extend(gt_errs)
            all_warnings.extend(gt_warns)
        except Exception as e:
            all_warnings.append(f"raw_measurements.json 读取异常，跳过地面真值比对: {e}")
    else:
        all_warnings.append("未发现 raw_measurements.json，跳过地面真值比对")

    # 6. 布局架构蓝图校验 (若存在 {folder.name}_layout.json 则严格校验；若不存在则提示跳过，保持向前兼容)
    layout_path = resolve_json_path(folder, "layout")
    if layout_path.exists():
        try:
            layout_data = json.loads(layout_path.read_text(encoding="utf-8"))
            lay_errs, lay_warns = validate_single_layout_schema(layout_data, layout_path.name)
            all_errors.extend(lay_errs)
            all_warnings.extend(lay_warns)

            # 跨文件一致性检查
            l_app = light_data.get("view_identity", {}).get("app_name")
            l_view = light_data.get("view_identity", {}).get("view_name")
            lay_app = layout_data.get("view_identity", {}).get("app_name")
            lay_view = layout_data.get("view_identity", {}).get("view_name")
            if lay_app and l_app and lay_app != l_app:
                all_errors.append(f"[布局一致性] {layout_path.name} app_name ('{lay_app}') 与 light.json ('{l_app}') 不一致")
            if lay_view and l_view and lay_view != l_view:
                all_errors.append(f"[布局一致性] {layout_path.name} view_name ('{lay_view}') 与 light.json ('{l_view}') 不一致")
        except Exception as e:
            all_errors.append(f"{layout_path.name} JSON 解析失败: {e}")

    # ── 结果输出 ─────────────────────────────────────────
    if all_errors:
        print(f"\n  {failure(f'发现 {len(all_errors)} 项错误 (校验不合格):')}")
        for err in all_errors:
            print(f"    • {Colors.RED}{err}{Colors.RESET}")
    else:
        print(f"  {success('Schema 结构与数据类型纪律通过')}")
        print(f"  {success('深浅模式几何/间距/排版对称恒等通过')}")
        if raw_path.exists():
            print(f"  {success('物理测量地面真值比对一致通过')}")
        if layout_path.exists():
            print(f"  {success(f'{layout_path.name} 布局架构蓝图校验通过')}")
        else:
            all_warnings.append(f"未检测到 {layout_path.name} (可选布局蓝图)，跳过布局架构校验")

    if all_warnings:
        print(f"\n  {warning(f'提示信息 ({len(all_warnings)} 项):')}")
        for w in all_warnings:
            print(f"    • {Colors.YELLOW}{w}{Colors.RESET}")

    is_valid = len(all_errors) == 0
    if is_valid:
        print(f"\n{Colors.GREEN}{Colors.BOLD}🎉 完美！该组深浅配对 Design Tokens 全部合格，完全符合工业级契约规范！{Colors.RESET}\n")
    else:
        print(f"\n{Colors.RED}{Colors.BOLD}⛔ 双模校验未通过，请根据上述提示修正。{Colors.RESET}\n")

    return is_valid


# ── 主入口 ────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="Apple Design Token 深浅配对合规性与数据契约校验工具",
    )
    parser.add_argument(
        "folder",
        nargs="?",
        default=None,
        help="待校验的目标子文件夹路径 (如 01_Settings_RootList/)",
    )
    parser.add_argument(
        "--mode",
        choices=["pair", "light", "dark", "layout"],
        default="pair",
        help="校验模式: 'light' (仅校核浅色阶段), 'dark' (仅校核深色), 'layout' (仅校核布局蓝图), 'pair' (默认，完整双模配对校验)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="扫描并校验工作区内所有编号子目录 (如 01_*, 02_*)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="输出详细诊断信息",
    )
    args = parser.parse_args()

    root_dir = Path.cwd()

    if args.all:
        pattern_dirs = sorted([d for d in root_dir.glob("[0-9][0-9]_*") if d.is_dir()])
        if not pattern_dirs:
            print(f"{warning('工作区当前未发现任何 [0-9][0-9]_* 样本子目录。')}")
            sys.exit(0)

        total_pass = 0
        total_fail = 0
        for d in pattern_dirs:
            ok = validate_directory(d, verbose=args.verbose)
            if ok:
                total_pass += 1
            else:
                total_fail += 1

        print(f"\n{'='*50}")
        print(f"全部校验完成: 共 {len(pattern_dirs)} 组, {Colors.GREEN}{total_pass} 组通过{Colors.RESET}, {Colors.RED}{total_fail} 组失败{Colors.RESET}")
        print(f"{'='*50}\n")
        sys.exit(0 if total_fail == 0 else 1)

    if not args.folder:
        parser.print_help()
        sys.exit(1)

    target_folder = Path(args.folder)
    if not target_folder.exists() or not target_folder.is_dir():
        print(failure(f"指定的目录不存在: {args.folder}"))
        sys.exit(1)

    if args.mode in ["light", "dark", "layout"]:
        ok = validate_single_mode(target_folder, args.mode, verbose=args.verbose)
    else:
        ok = validate_directory(target_folder, verbose=args.verbose)

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
