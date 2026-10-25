#!/usr/bin/env python3
"""
measure_helper.py — 尺寸与色彩测量辅助脚本（数字游标卡尺 & 吸色管）

仅提取最客观的物理数据（色值、像素距离），不做任何语义识别。
自动从截图分辨率匹配设备倍率，所有 px 同步换算为 pt。

用法:
    python measure_helper.py <folder_path>
    python measure_helper.py <folder_path> --scale 2

folder_path 中需包含 light.png 和 dark.png 两张成对截图。
输出: folder_path/raw_measurements.json
"""

import sys
import json
import argparse
from pathlib import Path
from collections import Counter

# ── 确保 Windows 终端 UTF-8 编码兼容 ───────────────────────
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
from PIL import Image
import cv2
from scipy.optimize import least_squares

# ── 设备分辨率数据库 ──────────────────────────────────────
# 键: (宽px, 高px)  值: (机型名, 缩放倍率, 逻辑宽pt, 逻辑高pt)
DEVICE_DB = {
    # @2x 设备
    (640,  1136): ("iPhone SE 1st",           2, 320, 568),
    (750,  1334): ("iPhone 6/7/8/SE2/SE3",    2, 375, 667),
    (828,  1792): ("iPhone XR/11",            2, 414, 896),
    # @3x 设备
    (1242, 2208): ("iPhone 6+/7+/8+",         3, 414, 736),
    (1125, 2436): ("iPhone X/XS/11 Pro",      3, 375, 812),
    (1242, 2688): ("iPhone XS Max/11 Pro Max", 3, 414, 896),
    (1080, 2340): ("iPhone 12/13 mini",       3, 360, 780),
    (1170, 2532): ("iPhone 12/13/14",         3, 390, 844),
    (1284, 2778): ("iPhone 12/13 Pro Max/14+", 3, 428, 926),
    (1179, 2556): ("iPhone 14/15/16 Pro",     3, 393, 852),
    (1290, 2796): ("iPhone 14/15 Pro Max/16+", 3, 430, 932),
    (1320, 2868): ("iPhone 16 Pro Max",       3, 440, 956),
    # Android / 小米设备
    (1080, 2400): ("Xiaomi 14 Pro (FHD+)",    2.625, 411, 914),
    (1440, 3200): ("Xiaomi 14 Pro (2K)",      3.5,   411, 914),
}

# ── 可调参数 ──────────────────────────────────────────────
COLOR_QUANT = 4         # 色值量化步长，抗锯齿 / 压缩噪声
COLOR_MATCH = 6         # 量化后色值匹配容差（±6 per channel）
BG_DIFF_THRESH = 10     # 最小通道差：低于此值视为"与背景同色"
MIN_GAP_PX = 6          # 忽略 < 2pt(@3x) 的微缝（噪声 / 分割线）


# ══════════════════════════════════════════════════════════
#  设备检测
# ══════════════════════════════════════════════════════════

def detect_device(w: int, h: int, override_scale: int = None) -> dict:
    """从截图像素尺寸自动匹配设备信息。

    返回 dict:
      model        — 机型名（或 "Unknown"）
      scale        — 缩放倍率 (1/2/3)
      image_size_px — {"w": ..., "h": ...}
      logical_size_pt — {"w": ..., "h": ...}
    """
    key = (w, h)
    if key in DEVICE_DB:
        model, scale, pt_w, pt_h = DEVICE_DB[key]
        scale_source = "device_db"
    else:
        model = f"Unknown ({w}x{h})"
        scale = None
        pt_w = None
        pt_h = None
        scale_source = "unknown"

    # CLI --scale 覆盖
    if override_scale is not None:
        scale = override_scale
        pt_w = round(w / scale)
        pt_h = round(h / scale)
        scale_source = "user_override"

    return {
        "model": model,
        "scale": scale,
        "scale_source": scale_source,
        "image_size_px": {"w": w, "h": h},
        "logical_size_pt": {"w": pt_w, "h": pt_h} if pt_w is not None else None,
    }


# ══════════════════════════════════════════════════════════
#  色彩采样
# ══════════════════════════════════════════════════════════

def _most_frequent_color(pixels: np.ndarray) -> tuple:
    """量化聚类后取最高频色，再回算匹配像素的真实均值以提高精度。"""
    quantized = (pixels // COLOR_QUANT) * COLOR_QUANT
    counts = Counter(map(tuple, quantized.tolist()))
    top_q = np.array(counts.most_common(1)[0][0])

    mask = np.all(np.abs(pixels.astype(int) - top_q) <= COLOR_MATCH, axis=1)
    if mask.sum() == 0:
        return tuple(int(c) for c in top_q)
    avg = np.round(pixels[mask].mean(axis=0)).astype(int)
    return tuple(int(c) for c in avg)


def sample_background(img: np.ndarray) -> tuple:
    """从屏幕四周边缘窄条采样，提取主体背景色。

    取顶部 2% 横条 + 左右各 2% 竖条的像素集合做频率统计。
    """
    h, w = img.shape[:2]
    sw = max(2, int(w * 0.02))   # 竖条宽度
    sh = max(2, int(h * 0.02))   # 横条高度

    strips = [
        img[:sh, :],              # 顶部横条
        img[:, :sw],              # 左侧竖条
        img[:, w - sw:],          # 右侧竖条
    ]
    pixels = np.vstack([s.reshape(-1, 3) for s in strips])
    return _most_frequent_color(pixels)


def find_candidate_surface_color(img: np.ndarray, bg: tuple) -> dict:
    """在中央区域寻找与背景色差异 >= BG_DIFF_THRESH 的最高频非背景色。

    遍历量化色频表前 30 名，取第一个与 bg 有足够差异的色值。
    注意：此结果仅为候选值，可能来自大图、图表或插画，不必然是卡片表面。
    仅当下游验证矩形边界和足够面积后才应视为 card_surface。

    返回 dict:
      color       — (R, G, B) 元组
      color_hex   — "#RRGGBB"
      area_ratio  — 该色在中央区域占比 (0.0~1.0)
      confidence  — 置信度: "high" / "medium" / "low"
    """
    h, w = img.shape[:2]
    center = img[int(h * 0.15):int(h * 0.85),
                 int(w * 0.05):int(w * 0.95)]
    pixels = center.reshape(-1, 3)
    total_pixels = len(pixels)
    quantized = (pixels // COLOR_QUANT) * COLOR_QUANT
    counts = Counter(map(tuple, quantized.tolist()))
    bg_arr = np.array(bg)

    for color_q, freq in counts.most_common(30):
        if np.max(np.abs(np.array(color_q) - bg_arr)) >= BG_DIFF_THRESH:
            # 回算真实均值
            match_mask = np.all(
                np.abs(pixels.astype(int) - np.array(color_q)) <= COLOR_MATCH,
                axis=1,
            )
            matched_count = int(match_mask.sum())
            if matched_count > 0:
                avg = np.round(pixels[match_mask].mean(axis=0)).astype(int)
                color = tuple(int(c) for c in avg)
            else:
                color = tuple(int(c) for c in color_q)
                matched_count = freq

            area_ratio = round(matched_count / total_pixels, 4)
            diff = int(np.max(np.abs(np.array(color) - bg_arr)))
            if area_ratio > 0.15 and diff > 30:
                confidence = "high"
            elif area_ratio > 0.05 and diff > 15:
                confidence = "medium"
            else:
                confidence = "low"

            return {
                "color": color,
                "color_hex": rgb_to_hex(color),
                "area_ratio": area_ratio,
                "confidence": confidence,
            }

    # 所有高频色都接近背景 → 回退
    fallback = _most_frequent_color(pixels)
    return {
        "color": fallback,
        "color_hex": rgb_to_hex(fallback),
        "area_ratio": None,
        "confidence": "low",
    }


def rgb_to_hex(rgb: tuple) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


# ══════════════════════════════════════════════════════════
#  间距测量（带坐标输出）
# ══════════════════════════════════════════════════════════

def _build_content_mask(img: np.ndarray, bg: tuple,
                        scale: int) -> tuple:
    """生成二值内容掩码（1 = 非背景像素）。

    步骤:
      1. 逐像素取各通道与 bg 的最大绝对差 → diff 矩阵
      2. diff > 阈值 → 原始掩码
      3. 水平形态学闭运算（宽核 ~20pt × 1pt）：
         - 横向合并卡片内散落的文字/图标 → 得到整块卡片区域
         - 竖向保守，不会桥接卡片间的垂直缝隙
      核大小随 scale 动态调整，确保跨设备一致的 pt 级行为。

    返回: (mask, kernel_params)
      mask          — np.ndarray, 二值掩码
      kernel_params — dict, {"kernel_w_px": int, "kernel_h_px": int}
    """
    diff = np.max(
        np.abs(img.astype(np.int16) - np.array(bg, dtype=np.int16)),
        axis=2,
    )
    raw = (diff > BG_DIFF_THRESH).astype(np.uint8)

    # 目标 ~20pt 宽、~1pt 高，按 scale 换算为 px 并确保奇数
    kernel_w = max(3, int(round(20 * scale))) | 1
    kernel_h = max(1, int(round(1 * scale))) | 1
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT,
                                       (kernel_w, kernel_h))
    closed = cv2.morphologyEx(raw, cv2.MORPH_CLOSE, kernel)

    kernel_params = {"kernel_w_px": kernel_w, "kernel_h_px": kernel_h}
    return closed, kernel_params


def measure_horizontal_margin(mask: np.ndarray, scale: int) -> dict:
    """逐行扫描取最左/最右内容像素，众数即卡片边缘 → 屏幕外边距。

    只分析垂直中部 70%（跳过状态栏、导航栏、TabBar 区域）。
    以 scale px (1 pt) 为桶做众数，消除亚像素抖动。

    返回:
      {"margin_pt": float, "left_edge_px": int, "right_edge_px": int}
    """
    h, w = mask.shape
    y0, y1 = int(h * 0.15), int(h * 0.85)

    lefts, rights = [], []
    for r in range(y0, y1):
        cols = np.nonzero(mask[r])[0]
        if len(cols) < w * 0.15:
            continue  # 稀疏行 = 卡片间隙，跳过
        lefts.append(int(cols[0]))
        rights.append(int(w - 1 - cols[-1]))

    if not lefts:
        return {
            "margin_pt": None, "left_edge_px": None,
            "right_edge_px": None,
            "failure_reason": "no_content_rows_detected",
        }

    def _mode_binned(vals: list) -> int:
        """以 scale px 为桶取众数。"""
        binned = [(v // scale) * scale for v in vals]
        return Counter(binned).most_common(1)[0][0]

    left_px = _mode_binned(lefts)
    right_px = _mode_binned(rights)
    avg_px = (left_px + right_px) / 2.0

    return {
        "margin_pt": round(avg_px / scale, 1),
        "left_edge_px": left_px,
        "right_edge_px": w - 1 - right_px,   # 转为右侧边缘 x 坐标
    }


def measure_card_vertical_gap(mask: np.ndarray, scale: int) -> dict:
    """利用行投影检测卡片间垂直缝隙，同时输出卡片与间隙的 Y 坐标。

    返回:
      {
        "gap_pt": float,              # 最常见间距 (pt)
        "card_bounds_px": [...],      # 每个卡片 {"y_start": int, "y_end": int}
        "gap_ranges_px": [...]        # 每个间隙 {"y_start": int, "y_end": int, "height_px": int}
      }
    """
    h, w = mask.shape
    row_sum = mask.sum(axis=1)
    is_gap = row_sum < w * 0.03

    y0, y1 = int(h * 0.12), int(h * 0.88)

    # ── 状态机：交替收集 content 段和 gap 段 ────────────
    segments = []       # (type, start, end)  type = "card" | "gap"
    current_type = "gap" if is_gap[y0] else "card"
    seg_start = y0

    for r in range(y0 + 1, y1):
        row_type = "gap" if is_gap[r] else "card"
        if row_type != current_type:
            segments.append((current_type, seg_start, r))
            current_type = row_type
            seg_start = r
    segments.append((current_type, seg_start, y1))

    # ── 过滤 ─────────────────────────────────────────────
    card_bounds = []
    gap_ranges = []
    gap_heights = []

    for seg_type, s, e in segments:
        height = e - s
        if seg_type == "card" and height >= MIN_GAP_PX:
            card_bounds.append({"y_start": int(s), "y_end": int(e)})
        elif seg_type == "gap" and height >= MIN_GAP_PX:
            gap_ranges.append({
                "y_start": int(s),
                "y_end": int(e),
                "height_px": int(height),
            })
            gap_heights.append(height)

    if not gap_heights:
        return {
            "gap_pt": None,
            "card_bounds_px": card_bounds,
            "gap_ranges_px": [],
            "failure_reason": "no_gaps_detected",
        }

    binned = [(g // scale) * scale for g in gap_heights]
    mode_px = Counter(binned).most_common(1)[0][0]

    return {
        "gap_pt": round(mode_px / scale, 1),
        "card_bounds_px": card_bounds,
        "gap_ranges_px": gap_ranges,
    }


def estimate_card_corner_radius(img: np.ndarray, bg: tuple, card_bounds: list,
                                margin_info: dict, scale: float) -> dict:
    """双轨圆角识别引擎：同时提取传统正圆角（工程标称值）与超椭圆连续曲率（曲线方程与指数）。"""
    empty_res = {
        "traditional_circle": {"radius_pt": None, "compensated_radius_pt": None},
        "superellipse": {"shape_exponent_n": None, "radius_a_pt": None, "radius_b_pt": None,
                         "curve_style": None, "exact_formula": None, "figma_corner_smoothing": None},
        "is_subtle_tint": False,
        "confidence": "none"
    }
    if not card_bounds or margin_info.get("left_edge_px") is None:
        return empty_res

    left_x = int(margin_info["left_edge_px"])
    right_x = int(margin_info["right_edge_px"])
    target_card = None
    for b in card_bounds:
        if b["y_end"] - b["y_start"] >= 40 * scale:
            target_card = b
            break
    if not target_card:
        return empty_res

    y0, y1 = target_card["y_start"], target_card["y_end"]
    roi_size = int(round(40 * scale))
    if y0 + roi_size > img.shape[0] or left_x + roi_size > img.shape[1]:
        return empty_res

    # 对比度分析：检查卡片中心与背景的颜色差异
    center_y = (y0 + y1) // 2
    center_x = (left_x + right_x) // 2
    card_center_color = img[center_y, center_x]
    color_diff = float(np.max(np.abs(card_center_color.astype(np.int16) - np.array(bg, dtype=np.int16))))
    is_subtle_tint = color_diff < 35  # 低对比度微光表面 (灰阶差 < 35)

    roi = img[max(0, y0 - 5) : y0 + roi_size, max(0, left_x - 5) : left_x + roi_size]
    gray = cv2.cvtColor(roi, cv2.COLOR_RGB2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)

    thresh_low = max(3, int(color_diff * 0.15))
    thresh_high = max(8, int(color_diff * 0.5))
    edges = cv2.Canny(blurred, thresh_low, thresh_high)

    pts = np.argwhere(edges > 0)
    if len(pts) < 12:
        empty_res["is_subtle_tint"] = is_subtle_tint
        empty_res["confidence"] = "low_points"
        return empty_res

    # ── 亚像素边缘提取 (借鉴 Devernay 二次峰值插值算法) ───────────
    # 利用 Sobel 计算局部梯度与主方向，将整数边缘坐标平滑至浮点亚像素 (精度 ~0.1px)
    gx = cv2.Sobel(blurred, cv2.CV_64F, 1, 0, ksize=3)
    gy = cv2.Sobel(blurred, cv2.CV_64F, 0, 1, ksize=3)
    modG = np.sqrt(gx**2 + gy**2)

    sub_xs = []
    sub_ys = []
    h_roi, w_roi = blurred.shape
    for py, px in pts:
        if 1 <= px < w_roi - 1 and 1 <= py < h_roi - 1:
            g_abs_x = abs(gx[py, px])
            g_abs_y = abs(gy[py, px])
            if g_abs_x >= g_abs_y:
                # 水平为主方向
                a = modG[py, px - 1]
                b = modG[py, px]
                c = modG[py, px + 1]
                denom = a - 2.0 * b + c
                offset = 0.5 * (a - c) / denom if abs(denom) > 1e-5 else 0.0
                offset = np.clip(offset, -0.6, 0.6)
                sub_xs.append(px + offset - 5)
                sub_ys.append(py - 5)
            else:
                # 垂直为主方向
                a = modG[py - 1, px]
                b = modG[py, px]
                c = modG[py + 1, px]
                denom = a - 2.0 * b + c
                offset = 0.5 * (a - c) / denom if abs(denom) > 1e-5 else 0.0
                offset = np.clip(offset, -0.6, 0.6)
                sub_xs.append(px - 5)
                sub_ys.append(py + offset - 5)
        else:
            sub_xs.append(px - 5)
            sub_ys.append(py - 5)

    sub_xs = np.array(sub_xs, dtype=float)
    sub_ys = np.array(sub_ys, dtype=float)
    corner_mask = (sub_xs >= 0) & (sub_ys >= 0) & (sub_xs < roi_size * 0.8) & (sub_ys < roi_size * 0.8)
    c_xs = sub_xs[corner_mask]
    c_ys = sub_ys[corner_mask]

    if len(c_xs) < 10:
        empty_res["is_subtle_tint"] = is_subtle_tint
        return empty_res

    # ── 1. 传统圆拟合 (Circle Fitting, G1 标称半径) ─────────────
    trad_pt = None
    comp_pt = None
    try:
        A = np.column_stack([c_xs, c_ys, np.ones(len(c_xs))])
        B = -(c_xs**2 + c_ys**2)
        res_c, _, _, _ = np.linalg.lstsq(A, B, rcond=None)
        D, E, F = res_c
        r_sq = D**2/4 + E**2/4 - F
        if r_sq > 0:
            fit_r_px = np.sqrt(r_sq)
            trad_pt = round(fit_r_px / scale, 1)
            comp_pt = round(trad_pt * 1.18, 1) if is_subtle_tint else trad_pt
    except Exception:
        pass

    # ── 2. 超椭圆连续曲率拟合 (Superellipse Fitting, G2/G3 方程与指数) ──
    # 结合智驾鲁棒损失 (Soft L1 Loss) 抑制微光边缘噪声
    superellipse_data = {
        "shape_exponent_n": None,
        "radius_a_pt": None,
        "radius_b_pt": None,
        "curve_style": None,
        "exact_formula": None,
        "figma_corner_smoothing": None
    }
    if trad_pt is not None:
        try:
            init_r = trad_pt * scale
            def loss_superellipse(params):
                cx, cy, a, b, n = params
                dx = np.abs((cx - c_xs) / a)
                dy = np.abs((cy - c_ys) / b)
                return (dx**n + dy**n) - 1.0

            p0 = [init_r, init_r, init_r, init_r, 2.0]
            bounds = ([init_r*0.5, init_r*0.5, init_r*0.5, init_r*0.5, 1.8],
                      [init_r*1.8, init_r*1.8, init_r*1.8, init_r*1.8, 6.0])

            # 采用 soft_l1 鲁棒核函数（Huber 平滑近似），自动下调离群点权重
            res_s = least_squares(loss_superellipse, p0, bounds=bounds, loss='soft_l1', f_scale=0.1)
            _, _, a, b, n = res_s.x
            a_pt = round(a / scale, 1)
            b_pt = round(b / scale, 1)
            n_val = round(float(n), 2)

            if abs(n_val - 2.0) <= 0.25:
                style = "circular_standard"
                smoothing = 0.0
            elif 2.25 < n_val <= 3.3:
                style = "superellipse_hyperos"
                smoothing = 0.4
            else:
                style = "continuous_apple_squircle"
                smoothing = 0.6

            superellipse_data = {
                "shape_exponent_n": n_val,
                "radius_a_pt": a_pt,
                "radius_b_pt": b_pt,
                "curve_style": style,
                "exact_formula": f"|x / {a_pt}|^{n_val} + |y / {b_pt}|^{n_val} = 1",
                "figma_corner_smoothing": smoothing
            }
        except Exception:
            pass

    return {
        "traditional_circle": {
            "radius_pt": trad_pt,
            "compensated_radius_pt": comp_pt if is_subtle_tint else None
        },
        "superellipse": superellipse_data,
        "is_subtle_tint": is_subtle_tint,
        "confidence": "high" if (trad_pt and superellipse_data["shape_exponent_n"]) else "medium"
    }


def generate_diagnostic_color_maps(img: np.ndarray, folder: Path, mode: str) -> dict:
    """根据智能驾驶与计算机视觉算法，生成辅助调试与多模态视觉审视的预处理染色图：
    1. {mode}_gradient_rainbow.png: 梯度法向 HSV 彩虹伪彩染色图
    2. {mode}_enhanced_clahe.png: CLAHE 自适应局部对比度增强图 (将 0.06 微光反差放大)
    """
    res = {}
    try:
        # 1. 梯度方向彩虹伪彩染色图
        gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        gx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize=3)
        mag, angle = cv2.cartToPolar(gx, gy, angleInDegrees=True)

        # 映射到 HSV：色相 Hue 0~180 (角度/2), 饱和度 Saturation 255, 亮度 Value 增强梯度幅值
        h = (angle / 2.0).astype(np.uint8)
        v = cv2.normalize(mag, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        s = np.full_like(h, 255)
        # 背景平坦无边缘区域压暗
        s[v < 18] = 0
        v[v < 18] = 15

        hsv = cv2.merge([h, s, v])
        rainbow_bgr = cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)
        rainbow_path = folder / f"{mode}_gradient_rainbow.png"
        cv2.imwrite(str(rainbow_path), rainbow_bgr)
        res["rainbow"] = str(rainbow_path)

        # 2. CLAHE 局部自适应对比度增强图 (强化 Alpha 0.06 微光卡片边界)
        lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        enhanced_lab = cv2.merge((cl, a, b))
        enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        clahe_path = folder / f"{mode}_enhanced_clahe.png"
        cv2.imwrite(str(clahe_path), enhanced_bgr)
        res["clahe"] = str(clahe_path)
    except Exception as e:
        pass
    return res


# ══════════════════════════════════════════════════════════
#  主流程
# ══════════════════════════════════════════════════════════

def analyze_single(path: Path, scale: float):
    """分析单张截图。

    返回: (bg_hex, candidate_surface_dict, content_mask, kernel_params, image_shape_hw, raw_img)
    """
    img = np.array(Image.open(path).convert("RGB"))
    bg = sample_background(img)
    candidate = find_candidate_surface_color(img, bg)
    mask, kernel_params = _build_content_mask(img, bg, scale)
    return rgb_to_hex(bg), candidate, mask, kernel_params, img.shape[:2], img, bg


IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".heic")

def find_image(folder: Path, mode: str) -> Path:
    """按规范查找截图：{folder_name}_{mode}.<ext> (支持 png, jpg, jpeg, webp, heic 等任意格式)"""
    prefix = f"{folder.name}_{mode}".lower()
    for f in folder.iterdir():
        if f.is_file() and f.stem.lower() == prefix and f.suffix.lower() in IMAGE_EXTENSIONS:
            return f
    print(f"❌ 错误: 未在 '{folder.name}' 找到符合规范的截图 '{folder.name}_{mode}.<ext>'")
    print(f"   规范格式: {{文件夹名}}_{mode}.png / jpg / jpeg / webp")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="iOS 截图尺寸与色彩测量辅助工具（数字游标卡尺 & 吸色管）",
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
        print(f"错误: 目录不存在: {folder}")
        sys.exit(1)

    light_path = find_image(folder, "light")
    dark_path = find_image(folder, "dark")

    # ── 尺寸与机型一致性硬校验 ────────────────────────────
    probe_l = Image.open(light_path)
    probe_d = Image.open(dark_path)
    if probe_l.size != probe_d.size:
        print(f"❌ 错误: 浅色与深色截图物理分辨率不一致！")
        print(f"   浅色 ({light_path.name}): {probe_l.size[0]}×{probe_l.size[1]} px")
        print(f"   深色 ({dark_path.name}): {probe_d.size[0]}×{probe_d.size[1]} px")
        print(f"   成对截图必须来自同一设备并在同一缩放状态下截取。")
        probe_l.close()
        probe_d.close()
        sys.exit(1)

    img_w, img_h = probe_l.size
    probe_l.close()
    probe_d.close()

    device = detect_device(img_w, img_h, args.scale)
    scale = device["scale"]

    if scale is None:
        print(f"❌ 无法识别设备 ({img_w}×{img_h} px)，且未指定 --scale。")
        print(f"   请使用 --scale 2 或 --scale 3 手动指定倍率。")
        sys.exit(1)

    pt_info = device["logical_size_pt"]
    print(f"📐 正在分析 {folder.resolve()}")
    print(f"   截图文件: {light_path.name} & {dark_path.name}")
    print(f"   匹配设备: {device['model']}  |  "
          f"{img_w}×{img_h} px  @{scale}x  →  "
          f"{pt_info['w']}×{pt_info['h']} pt")
    print(f"   倍率来源: {device['scale_source']}\n")

    # ── 浅色模式 ─────────────────────────────────────────
    l_bg, l_cand, l_mask, l_kparams, _, l_img, l_raw_bg = analyze_single(light_path, scale)
    print(f"  [Light] 背景 {l_bg}  候选表面色 {l_cand['color_hex']}"
          f" (面积 {l_cand['area_ratio']}, 置信度 {l_cand['confidence']})")

    # ── 深色模式 ─────────────────────────────────────────
    d_bg, d_cand, d_mask, d_kparams, _, d_img, d_raw_bg = analyze_single(dark_path, scale)
    print(f"  [Dark]  背景 {d_bg}  候选表面色 {d_cand['color_hex']}"
          f" (面积 {d_cand['area_ratio']}, 置信度 {d_cand['confidence']})")

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
    margin_d = measure_horizontal_margin(d_mask, scale)

    # 只在两端均测量成功且差异可控时给出共识值
    ml, md = margin_l["margin_pt"], margin_d["margin_pt"]
    if ml is not None and md is not None:
        if abs(ml - md) <= max(ml, md, 1) * 0.3:   # 差异 ≤ 30%
            margin_pt = round((ml + md) / 2, 1)
        else:
            margin_pt = None   # 差异过大，不可靠
    elif ml is not None:
        margin_pt = ml
    elif md is not None:
        margin_pt = md
    else:
        margin_pt = None

    gap_l = measure_card_vertical_gap(l_mask, scale)
    gap_d = measure_card_vertical_gap(d_mask, scale)

    gl, gd = gap_l["gap_pt"], gap_d["gap_pt"]
    if gl is not None and gd is not None:
        if abs(gl - gd) <= max(gl, gd, 1) * 0.3:
            gap_pt = round((gl + gd) / 2, 1)
        else:
            gap_pt = None
    elif gl is not None:
        gap_pt = gl
    elif gd is not None:
        gap_pt = gd
    else:
        gap_pt = None

    # ── 卡片圆角半径拟合 ──────────────────────────────────
    radius_l = estimate_card_corner_radius(l_img, l_raw_bg, gap_l["card_bounds_px"], margin_l, scale)
    radius_d = estimate_card_corner_radius(d_img, d_raw_bg, gap_d["card_bounds_px"], margin_d, scale)

    trad_r_l = radius_l["traditional_circle"]["radius_pt"]
    comp_r_l = radius_l["traditional_circle"]["compensated_radius_pt"]
    se_l = radius_l["superellipse"]

    print(f"\n  水平外边距 ≈ {margin_pt} pt  "
          f"(Light {ml} / Dark {md})")
    print(f"  卡片垂直间距 ≈ {gap_pt} pt  "
          f"(Light {gl} / Dark {gd})")
    if trad_r_l is not None:
        comp_str = f" (微光补偿建议: ~{comp_r_l} pt)" if comp_r_l else ""
        print(f"  传统圆角拟合 ≈ {trad_r_l} pt{comp_str}")
    if se_l.get("shape_exponent_n") is not None:
        print(f"  超椭圆曲率拟合 ≈ 指数 n={se_l['shape_exponent_n']} ({se_l['curve_style']})")
        print(f"  推导数学方程 ≈ {se_l['exact_formula']}")
    print(f"  检测到卡片: Light {len(gap_l['card_bounds_px'])} 个  "
          f"Dark {len(gap_d['card_bounds_px'])} 个")

    # ── 输出 JSON ────────────────────────────────────────
    result = {
        "device_info": device,
        "analysis_params": {
            "color_quant": COLOR_QUANT,
            "color_match": COLOR_MATCH,
            "bg_diff_thresh": BG_DIFF_THRESH,
            "min_gap_px": MIN_GAP_PX,
            "kernel_params_light": l_kparams,
            "kernel_params_dark": d_kparams,
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
            "traditional_card_radius_pt": trad_r_l,
            "compensated_card_radius_pt": comp_r_l,
            "superellipse_curvature": se_l,
            "margin_consensus": "valid" if margin_pt is not None else "missing_or_inconsistent",
            "gap_consensus": "valid" if gap_pt is not None else "missing_or_inconsistent",
        },
        "per_mode_details": {
            "light": {
                "margin": margin_l,
                "gap": gap_l,
                "radius": radius_l,
            },
            "dark": {
                "margin": margin_d,
                "gap": gap_d,
                "radius": radius_d,
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
